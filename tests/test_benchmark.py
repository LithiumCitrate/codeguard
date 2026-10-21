"""The measurement machinery is itself a claim, so it is tested like one.

`run_benchmark` is executed end-to-end on CodeGuard's own clean-room fixtures:
tiny, offline, and it proves the ablation table, the ground-truth bookkeeping and
the threshold-sensitivity numbers are produced by working code, not pasted.
"""

import hashlib
import json
import os
import shutil
import unittest

from codeguard.benchmark import (Case, Trace, run_benchmark,
                                 threshold_sensitivity)
from codeguard.corpus import CorpusEntry, write_manifest
from codeguard.normalize import tokenize_source
from codeguard.score import FEATURE_NAMES

import helpers
from helpers import NEGATIVE_DIR, tempdir

NAMES = ["ring_cache.py", "roman_form.py", "attempt_loop.py", "word_tally.py"]


def feat(**over):
    row = {n: 0.0 for n in FEATURE_NAMES}
    row["verbatim_run"] = 0
    row["len_ratio"] = 1.0
    row.update(over)
    return row


def case(cid, origin, mutation="rename", spans=2):
    return Case(cid, origin, "pkg/f.py", "pkg", "MIT", mutation, "", True,
                (), frozenset(), [(1, 5)] * spans)


class ThresholdSensitivityTests(unittest.TestCase):
    def test_counts_split_true_and_false_pairs_by_threshold(self):
        cases = [case(0, 7), case(1, -1)]          # one mutant, one negative control
        # IDF down-weights common shingles, so the *same* pair scores lower with
        # IDF: wc 0.9 (unweighted containment) -> 0.1 (weighted)
        traces = {
            0: [Trace(0, 0, 7, feat(wc=0.1, j_role=0.9, max_sim=0.9),
                      feat(wc=0.9, j_role=0.9, max_sim=0.9), {"role": 30}),
                Trace(1, 1, 3, feat(wc=0.05, j_role=0.05),
                      feat(wc=0.05, j_role=0.05), {"role": 1})],
            1: [Trace(0, 0, 4, feat(wc=0.05, j_role=0.05, max_sim=0.05),
                      feat(wc=0.9, j_role=0.9, max_sim=0.9), {"role": 30})],
        }
        rows = threshold_sensitivity(cases, traces, None, thresholds=(0.5,))
        row = rows[0]
        self.assertEqual(row["plain"]["true_pairs"], 1)
        self.assertEqual(row["idf"]["true_pairs"], 0)
        self.assertEqual(row["plain"]["false_pairs"], 1)
        self.assertEqual(row["idf"]["false_pairs"], 0)
        self.assertEqual(row["false_pair_reduction"], 1.0)

    def test_reduction_is_zero_when_there_is_nothing_to_suppress(self):
        rows = threshold_sensitivity([case(0, 7)], {0: []}, None, thresholds=(0.5,))
        self.assertEqual(rows[0]["false_pair_reduction"], 0.0)


class BenchmarkRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.corpus = os.path.join(self.tmp, "corpus")
        entries = []
        for doc_id, name in enumerate(NAMES):
            text = helpers.read_negative(name)
            target = os.path.join(self.corpus, "fixture-0.1.0", name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(os.path.join(NEGATIVE_DIR, name), target)
            entries.append(CorpusEntry(
                package="fixture", version="0.1.0",
                path="fixture-0.1.0/%s" % name, abs_path=target,
                license_spdx="Apache-2.0", license_source="self-authored",
                license_raw="Apache-2.0 (fixture)", language="python",
                lines=text.count("\n") + 1, tokens=len(tokenize_source(text)),
                sha256=hashlib.sha256(text.encode()).hexdigest(), size=len(text),
                sdist_sha256=""))
        write_manifest(entries, os.path.join(self.corpus, "corpus.json"),
                       {"packages": ["fixture"], "max_files_per_package": 10})

    def test_run_benchmark_produces_the_published_artifacts(self):
        out = os.path.join(self.tmp, "bench")
        payload = run_benchmark(self.tmp, out=out, train=False, per_package=10,
                                files=4, chars=4000, min_chars=300, fp_sample=0,
                                log=lambda *a: None)
        self.assertEqual(payload["schema"], "codeguard.benchmark/v1")
        self.assertEqual(payload["corpus"]["files"], 4)
        self.assertGreaterEqual(len(payload["results"]), 8)
        for row in payload["results"].values():
            self.assertGreaterEqual(row["overall_detect_rate"], 0.0)
            self.assertLessEqual(row["overall_detect_rate"], 1.0)
            self.assertEqual(row["false_positives"], 0,
                             "clean-room fixtures must not attribute to each other")
        # ground truth is the mutation log itself
        self.assertIn("multi_idf", payload["results"])
        self.assertIn("sha_exact", payload["results"])
        self.assertEqual(len(payload["threshold_sensitivity"]), 4)
        for path in ("benchmark.json", "benchmark.md"):
            self.assertGreater(os.path.getsize(os.path.join(out, path)), 200, path)
        with open(os.path.join(out, "benchmark.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("阈值敏感性", md)
        self.assertIn("检出率与消融", md)


if __name__ == "__main__":
    unittest.main()
