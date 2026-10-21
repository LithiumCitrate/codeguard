"""External evaluation harness: metrics must be computed, not asserted by hand."""

import json
import os
import shutil
import unittest

from codeguard.evaluate import (clopper_pearson_upper, load_manifest,
                                run_eval, to_markdown, write_eval)

import helpers
from helpers import build_index, make_corpus, read_negative, tempdir

NAMES = ["ring_cache.py", "roman_form.py", "slug_maker.py"]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.corpus = os.path.join(self.tmp, "corpus")
        docs, texts = make_corpus(NAMES, self.corpus)
        self.index = build_index(self.corpus, docs, texts)

    def manifest(self):
        path = os.path.join(self.tmp, "manifest.jsonl")
        copied = os.path.join(helpers.NEGATIVE_DIR, "ring_cache.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "clean-1", "label": "clean",
                                 "code": read_negative("attempt_loop.py")},
                                ensure_ascii=False) + "\n")
            fh.write(json.dumps({"id": "copy-1", "label": "copied",
                                 "path": copied, "source_package": "fixture",
                                 "source_path": "ring_cache.py",
                                 "license": "LicenseRef-Proprietary"},
                                ensure_ascii=False) + "\n")
        return path

    def test_clean_and_copied_samples_are_scored_separately(self):
        payload = run_eval(self.index, None, load_manifest(self.manifest()),
                           fail_on=("S1", "S2", "S3", "S4"))
        summary = payload["summary"]
        self.assertEqual(summary["clean"], 1)
        self.assertEqual(summary["copied"], 1)
        self.assertEqual(summary["clean_blocking"], 0)
        self.assertEqual(summary["clean_any_finding"], 0)
        self.assertEqual(summary["copied_attributed"], 1)
        self.assertEqual(summary["copied_detected"], 1)
        self.assertEqual(summary["copied_top1"], 1)
        self.assertGreaterEqual(summary["risk_counts"]["S1"], 1)
        self.assertEqual(payload["samples"][1]["label"], "copied")
        self.assertTrue(payload["samples"][1]["attributed"])

    def test_markdown_and_json_are_written(self):
        payload = run_eval(self.index, None, load_manifest(self.manifest()),
                           fail_on=("S1", "S2", "S3", "S4"))
        out = os.path.join(self.tmp, "eval")
        paths = write_eval(payload, out, "fixture eval")
        self.assertEqual(len(paths), 2)
        with open(paths[0], encoding="utf-8") as fh:
            again = json.load(fh)
        self.assertEqual(again["schema"], "codeguard.eval/v1")
        with open(paths[1], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("干净样本", text)
        self.assertIn("未通过样本", text)

    def test_dataset_line_is_rendered_when_present(self):
        payload = run_eval(self.index, None, load_manifest(self.manifest()),
                           fail_on=("S1", "S2", "S3", "S4"))
        payload["dataset"] = {"name": "ExampleSet", "version": "v1",
                              "license": "MIT", "sha256": "abc",
                              "url": "https://example.invalid/data"}
        self.assertIn("ExampleSet v1", to_markdown(payload))

    def test_invalid_label_is_rejected(self):
        path = os.path.join(self.tmp, "bad.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"id":"x","label":"maybe","code":"x=1"}\n')
        with self.assertRaises(ValueError):
            load_manifest(path)


class UpperBoundTests(unittest.TestCase):
    def test_zero_events_uses_the_exact_closed_form(self):
        self.assertAlmostEqual(clopper_pearson_upper(0, 10), 1 - 0.05 ** 0.1, places=9)
        self.assertAlmostEqual(clopper_pearson_upper(0, 164), 0.0181, places=4)
        self.assertEqual(clopper_pearson_upper(0, 0), 1.0)
        self.assertEqual(clopper_pearson_upper(10, 10), 1.0)

    def test_nonzero_events_are_between_the_point_estimate_and_one(self):
        upper = clopper_pearson_upper(1, 10)
        self.assertGreater(upper, 0.1)
        self.assertLess(upper, 1.0)


if __name__ == "__main__":
    unittest.main()
