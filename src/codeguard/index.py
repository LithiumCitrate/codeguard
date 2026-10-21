"""Fingerprint index: compact storage, LSH retrieval, no source text retained.

Two deliberate compression choices keep the artifact small enough to ship and
fast enough to load on a student laptop:

* signatures are stored as b-bit MinHash (low 8 bits per permutation) and the
  estimator is bias-corrected, cutting sketch bytes by 8x;
* band keys are truncated to 32 bits, which adds a negligible number of extra
  candidates but never changes the final verdict.

Exact scoring does not rely on the compressed sketch: verification re-reads the
candidate region from the locally tracked corpus, so the index stores hashes
and locators only, never source text.
"""

from __future__ import annotations

import base64
import json
import math
import os
import struct
import time
import zlib
from dataclasses import asdict, dataclass, field

from .cms import CountMin
from .fingerprint import LAYER_SIZES, build_fingerprint
from .minhash import band_keys, h64
from .normalize import build_spans

INDEX_VERSION = "1.2"
MAGIC = b"CGIDX2"
BAND_PLAN = {"role": 12, "abs": 12, "edge": 6, "lit": 4}
ALL_LAYERS = ("role", "abs", "edge", "lit")
BBIT_MASK = 0xFF
BBIT_FALSE_MATCH = 1.0 / 256.0


@dataclass
class Params:
    window: int = 48
    stride: int = 24
    min_tokens: int = 10
    sketch_sizes: dict = field(default_factory=lambda: dict(LAYER_SIZES))
    active_layers: tuple = ("role", "abs", "edge")

    def key(self) -> int:
        return h64(json.dumps(asdict(self), sort_keys=True))


def _pack_u32(values) -> bytes:
    return struct.pack("<%dI" % len(values), *[v & 0xFFFFFFFF for v in values])


def _unpack_u32(data: bytes):
    return list(struct.unpack("<%dI" % (len(data) // 4), data))


def _pack_bbit(signature) -> bytes:
    return bytes((v & BBIT_MASK) for v in signature)


def correct_bbit(agreement: float) -> float:
    """Undo the 1/256 false-agreement bias of b-bit MinHash."""
    return max(0.0, min(1.0, (agreement - BBIT_FALSE_MATCH) / (1.0 - BBIT_FALSE_MATCH)))


@dataclass
class DocRecord:
    doc_id: int
    package: str
    version: str
    path: str
    license_spdx: str
    license_source: str
    language: str
    lines: int
    tokens: int
    sha256: str
    size: int


@dataclass
class ChunkRecord:
    index: int
    doc_id: int
    line_start: int
    line_end: int
    bands: bytes
    sig8: bytes


class FingerprintIndex:
    def _layers(self):
        return tuple(self.params.active_layers)

    def _sig_bytes(self, layer: str) -> int:
        return self.params.sketch_sizes[layer]

    def __init__(self, params: Params | None = None):
        self.params = params or Params()
        self.docs: list[DocRecord] = []
        self.chunks: list[ChunkRecord] = []
        self.cms = CountMin()
        self.tables: dict = {}
        self.built_at = 0
        self.corpus_root = ""
        self.chunk_meta: dict = {}

    # ------------------------------------------------------------------ build

    def add_document(self, doc: DocRecord, text: str, language: str = "python") -> int:
        spans = build_spans(text, language, self.params.window, self.params.stride)
        self.docs.append(doc)
        for span in spans:
            fp = build_fingerprint(span)
            bands, sig8 = bytearray(), bytearray()
            for layer in self._layers():
                sig = fp.sketches[layer].signature
                bands += _pack_u32(band_keys(sig, BAND_PLAN[layer], "cg:" + layer))
                sig8 += _pack_bbit(sig)
            for layer in ("role", "abs"):
                for h in fp.shingles[layer]:
                    self.cms.add(h)
            idx = len(self.chunks)
            self.chunks.append(ChunkRecord(idx, doc.doc_id, span.start_line,
                                           span.end_line, bytes(bands), bytes(sig8)))
            self.chunk_meta[idx] = {k: len(v) for k, v in fp.shingles.items()}
        return len(spans)

    def finalize(self) -> "FingerprintIndex":
        self.built_at = int(time.time())
        self._build_tables()
        return self

    def _build_tables(self):
        tables = {}
        for layer, band_no, key, chunk_idx in self._band_entries():
            tables.setdefault((layer, band_no, key), []).append(chunk_idx)
        self.tables = tables
        return tables

    def _band_entries(self):
        for chunk in self.chunks:
            pos = 0
            for layer in self._layers():
                count = BAND_PLAN[layer]
                keys = _unpack_u32(chunk.bands[pos:pos + count * 4])
                pos += count * 4
                for band_no, key in enumerate(keys):
                    yield layer, band_no, key, chunk.index

    # ------------------------------------------------------------- persistence

    def save(self, path: str) -> int:
        payload = {
            "index_version": INDEX_VERSION,
            "params": asdict(self.params),
            "built_at": self.built_at,
            "corpus_root": self.corpus_root,
            "docs": [asdict(d) for d in self.docs],
            "chunk_fields": ["index", "doc_id", "line_start", "line_end", "bands", "sig8"],
            "chunks": [base64.b64encode(c.bands + c.sig8).decode("ascii")
                       + "|%d|%d|%d|%d|%d" % (c.index, c.doc_id, c.line_start,
                                              c.line_end, len(c.bands))
                       for c in self.chunks],
            "cms": self.cms.to_base64(),
            "cms_rows": self.cms.rows,
            "cms_width": self.cms.width,
            # without `total` every idf weight collapses to log(2) after a reload,
            # which silently turns IDF-weighted containment back into plain
            # containment - and trains the judge on one feature while inference
            # feeds it another
            "cms_total": self.cms.total,
        }
        blob = zlib.compress(json.dumps(payload).encode("utf-8"), 6)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(MAGIC)
            fh.write(struct.pack("<I", len(blob)))
            fh.write(struct.pack("<I", len(payload["chunks"])))
            fh.write(blob)
        os.replace(tmp, path)
        return len(blob)

    @classmethod
    def load(cls, path: str) -> "FingerprintIndex":
        with open(path, "rb") as fh:
            if fh.read(6) != MAGIC:
                raise ValueError("not a CodeGuard index file: %s" % path)
            blob_size, _n = struct.unpack("<II", fh.read(8))
            payload = json.loads(zlib.decompress(fh.read(blob_size)).decode("utf-8"))
        if payload["index_version"] != INDEX_VERSION:
            raise ValueError("index version %s unsupported" % payload["index_version"])
        params = dict(payload["params"])
        # JSON turns the layer tuple into a list; keep the declared type so
        # Params.key() stays stable across save/load
        params["active_layers"] = tuple(params["active_layers"])
        obj = cls(Params(**params))
        obj.built_at = payload["built_at"]
        obj.corpus_root = payload.get("corpus_root", "")
        obj.docs = [DocRecord(**d) for d in payload["docs"]]
        for entry in payload["chunks"]:
            b64, index, doc_id, ls, le, blen = entry.split("|")
            raw = base64.b64decode(b64)
            obj.chunks.append(ChunkRecord(int(index), int(doc_id), int(ls), int(le),
                                          raw[:int(blen)], raw[int(blen):]))
        obj.cms = CountMin.from_base64(payload["cms"], payload["cms_rows"],
                                       payload["cms_width"])
        obj.cms.total = payload["cms_total"]
        obj._build_tables()
        return obj

    # ---------------------------------------------------------------- retrieval

    def stats(self) -> dict:
        payloads = sum(len(c.bands) + len(c.sig8) for c in self.chunks)
        return {"index_version": INDEX_VERSION, "documents": len(self.docs),
                "chunks": len(self.chunks),
                "packages": len({d.package for d in self.docs}),
                "licenses": sorted({d.license_spdx for d in self.docs}),
                "params": asdict(self.params), "band_plan": BAND_PLAN,
                "sketch_bytes_per_chunk": sum(len(c.sig8) for c in self.chunks) // max(1, len(self.chunks)),
                "payload_bytes": payloads,
                "payload_bytes_per_chunk": payloads // max(1, len(self.chunks)),
                "buckets": len(self.tables), "built_at": self.built_at}

    def corpus_health(self) -> tuple:
        """How many indexed documents can still be re-read from disk.

        Stage two verifies against the *original* corpus text, so a deleted or
        moved corpus does not merely slow the tool down - it silently removes
        every finding. A compliance gate must therefore distinguish "checked and
        clean" from "could not check", and this is the only signal it needs.
        """
        total = len(self.docs)
        readable = sum(1 for doc in self.docs if os.path.exists(self.corpus_file(doc)))
        return total, readable

    def probe(self, text: str, language: str = "python", min_band_hits: int = 1):
        """LSH prefilter; returns [(span_ordinal, span, fingerprint, {chunk: hits})]."""
        spans = build_spans(text, language, self.params.window, self.params.stride)
        results = []
        for ord_no, span in enumerate(spans):
            fp = build_fingerprint(span)
            hits = {}
            for layer in self._layers():
                for band_no, key in enumerate(band_keys(
                        fp.sketches[layer].signature, BAND_PLAN[layer], "cg:" + layer)):
                    for chunk_idx in self.tables.get((layer, band_no, key & 0xFFFFFFFF), ()):
                        hits[chunk_idx] = hits.get(chunk_idx, 0) + 1
            results.append((ord_no, span, fp,
                            {i: n for i, n in hits.items() if n >= min_band_hits}))
        return results

    def sketch_estimate(self, chunk: ChunkRecord, fp, layer: str) -> float:
        size = self.params.sketch_sizes[layer]
        offset = sum(self.params.sketch_sizes[l] for l in self._layers()[:self._layers().index(layer)])
        stored = chunk.sig8[offset:offset + size]
        query = fp.sketches[layer].signature[:size]
        same = sum(1 for a, b in zip(stored, query) if (b & BBIT_MASK) == a)
        return correct_bbit(same / size)

    def doc_for(self, doc_id: int) -> DocRecord:
        return self.docs[doc_id]

    def chunk(self, chunk_index: int) -> ChunkRecord:
        return self.chunks[chunk_index]

    def idf_weight(self, shingle: int) -> float:
        df = self.cms.estimate(shingle) + 1
        return math.log(max(self.cms.total, 2 * df) / df)

    def corpus_file(self, doc: DocRecord) -> str:
        return os.path.join(self.corpus_root, doc.path.replace("/", os.sep))
