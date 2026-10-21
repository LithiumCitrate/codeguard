"""MinHash, banding, sketch compression and the index container."""

import json
import os
import unittest
import zlib

from codeguard.fingerprint import LAYER_SIZES, build_fingerprint, span_shingles
from codeguard.index import BAND_PLAN, MAGIC, FingerprintIndex, correct_bbit
from codeguard.minhash import Sketch, band_keys, containment, h64, jaccard
from codeguard.normalize import build_spans
from helpers import build_index, make_corpus, negative_names, tempdir


class MinHashTests(unittest.TestCase):
    def test_hash_is_stable(self):
        self.assertEqual(h64("codeguard"), h64("codeguard"))
        self.assertNotEqual(h64("codeguard"), h64("CodeGuard"))
        self.assertEqual(h64("abc"), h64(b"abc"))

    def test_sketch_agreement_tracks_exact_jaccard(self):
        a = {h64("t%d" % i) for i in range(200)}
        b = set(a) | {h64("x%d" % i) for i in range(100)}
        sk_a, sk_b = Sketch("cg:test", 128), Sketch("cg:test", 128)
        sk_a.update(a)
        sk_b.update(b)
        self.assertAlmostEqual(sk_a.agreement(sk_b), jaccard(a, b), delta=0.12)

    def test_band_keys_are_reproducible(self):
        sk = Sketch("cg:role", 64)
        sk.update({h64("a"), h64("b")})
        self.assertEqual(band_keys(sk.signature, BAND_PLAN["role"], "cg:role"),
                         band_keys(sk.signature, BAND_PLAN["role"], "cg:role"))

    def test_bbit_correction_removes_false_agreement(self):
        self.assertAlmostEqual(correct_bbit(1.0 / 256), 0.0, places=6)
        self.assertGreater(correct_bbit(0.5), 0.49)

    def test_containment_is_asymmetric(self):
        small, big = {1, 2, 3}, {1, 2, 3, 4, 5}
        self.assertEqual(containment(small, big), 1.0)
        self.assertLess(containment(big, small), 1.0)


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempdir()
        cls.corpus = os.path.join(cls.root, "corpus")
        os.makedirs(cls.corpus, exist_ok=True)
        cls.names = negative_names()[:4]
        cls.docs, cls.texts = make_corpus(cls.names, cls.corpus)
        cls.index = build_index(cls.corpus, cls.docs, cls.texts)

    def test_probe_finds_the_document_itself(self):
        for doc_id, text in enumerate(self.texts):
            hits = self.index.probe(text[:1500], min_band_hits=1)
            self.assertTrue(hits, "expected candidate spans")
            docs = {self.index.chunk(ci).doc_id for _, _, _, h in hits for ci in h}
            self.assertIn(doc_id, docs)

    def test_save_and_load_round_trip_preserves_retrieval(self):
        path = os.path.join(self.root, "roundtrip.bin")
        self.index.save(path)
        other = FingerprintIndex.load(path)
        self.assertEqual(len(other.chunks), len(self.index.chunks))
        self.assertEqual(other.params.active_layers, self.index.params.active_layers)
        text = self.texts[0][:1200]
        self.assertEqual([sorted(h[3]) for h in self.index.probe(text)],
                         [sorted(h[3]) for h in other.probe(text)])

    def test_idf_weights_survive_a_save_load_cycle(self):
        # a lost cms.total collapses every weight to log(2), silently turning
        # IDF-weighted containment into plain containment in production
        path = os.path.join(self.root, "idf.bin")
        self.index.save(path)
        other = FingerprintIndex.load(path)
        self.assertEqual(other.cms.total, self.index.cms.total)
        self.assertGreater(self.index.cms.total, 0)
        shingles = sorted({h for _, _, fp, _ in self.index.probe(self.texts[0])
                           for h in fp.shingles["role"]})[:50]
        for idx in (self.index, other):
            self.assertGreater(len({round(idx.idf_weight(s), 6) for s in shingles}), 1,
                               "idf weights must discriminate common vs rare shingles")
        self.assertEqual([round(other.idf_weight(s), 9) for s in shingles],
                         [round(self.index.idf_weight(s), 9) for s in shingles])

    def test_index_container_stores_no_source_text(self):
        path = os.path.join(self.root, "peek.bin")
        self.index.save(path)
        blob = open(path, "rb").read()
        self.assertTrue(blob.startswith(MAGIC))
        payload = json.loads(zlib.decompress(blob[len(MAGIC) + 8:]).decode("utf-8"))
        joined = json.dumps(payload)
        for marker in ("def ", "import ", '"""'):
            self.assertNotIn(marker, joined)

    def test_sketch_estimate_is_close_to_exact_jaccard(self):
        span = build_spans(self.texts[0], "python", self.index.params.window,
                           self.index.params.stride)[0]
        chunk = [c for c in self.index.chunks if c.doc_id == 0][0]
        fp = build_fingerprint(span)
        for layer in ("role", "abs"):
            est = self.index.sketch_estimate(chunk, fp, layer)
            exact = jaccard(fp.shingles[layer], span_shingles(span)[layer])
            self.assertLess(abs(est - exact), 0.25,
                            "layer %s: est=%.3f exact=%.3f" % (layer, est, exact))

    def test_payload_is_compact(self):
        st = self.index.stats()
        self.assertLess(st["payload_bytes_per_chunk"], 520)
        self.assertIn("role", LAYER_SIZES)

    def test_idf_weight_prefers_rare_shingles(self):
        span = build_spans(self.texts[0], "python", 48, 24)[0]
        seen = next(iter(span_shingles(span)["role"]))
        unseen = h64("a-shingle-that-never-appears")
        self.assertGreater(self.index.idf_weight(unseen),
                           self.index.idf_weight(seen))

    def test_rejects_a_foreign_container(self):
        path = os.path.join(self.root, "bogus.bin")
        with open(path, "wb") as fh:
            fh.write(b"NOPE!!" + b"\x00" * 64)
        with self.assertRaises(ValueError):
            FingerprintIndex.load(path)


if __name__ == "__main__":
    unittest.main()
