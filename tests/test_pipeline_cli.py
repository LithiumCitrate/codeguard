"""End-to-end pipeline and CLI contract: detection, risk grading, exit codes.

Everything runs against a two-file index built from CodeGuard's own clean-room
fixtures, so the suite needs no network, no corpus download and no model.
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import unittest

from codeguard.adjudicate import Scanner, corroborates
from codeguard.cli import main, strip_diff_markers
from codeguard.index import DocRecord, FingerprintIndex, Params
from codeguard.mutations import apply_mutation
from codeguard.normalize import tokenize_source
from codeguard.report import provenance_receipt, to_html, to_sarif, write_outputs

from helpers import build_index, make_corpus, read_negative, tempdir

NAMES = ["ring_cache.py", "roman_form.py", "slug_maker.py"]


@contextlib.contextmanager
def _capture():
    """stdout of the CLI is part of its contract (CI logs), so tests read it."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


class PipelineTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.corpus = os.path.join(self.tmp, "corpus")
        self.workspace = os.path.join(self.tmp, "workspace")
        os.makedirs(self.workspace)
        docs, texts = make_corpus(NAMES, self.corpus)
        index = build_index(self.corpus, docs, texts)
        index.save(os.path.join(self.workspace, "index.bin"))
        self.index_path = os.path.join(self.workspace, "index.bin")

    def load(self):
        from codeguard.index import FingerprintIndex
        return FingerprintIndex.load(self.index_path)

    def scanner(self, **kw):
        return Scanner(self.load(), **kw)


class DetectionTests(PipelineTestBase):
    def test_an_exact_copy_is_attributed_to_its_source_file(self):
        scan = self.scanner().scan_text(read_negative("ring_cache.py"),
                                        target="copied.py", target_license="MIT")
        self.assertGreater(scan.total_spans, 3)
        self.assertEqual([f.path for f in scan.findings],
                         [os.path.join("fixture-0.1.0", "ring_cache.py").replace(os.sep, "/")])
        self.assertGreater(scan.findings[0].confidence, 0.9)
        self.assertEqual(scan.findings[0].risk, "S1")

    def test_a_clean_room_reimplementation_is_not_flagged(self):
        scan = self.scanner().scan_text(read_negative("attempt_loop.py"),
                                        target="mine.py", target_license="MIT")
        self.assertEqual(scan.findings, [], "independent code must not be attributed")
        self.assertGreater(scan.total_spans, 0)

    def test_a_rewritten_copy_is_still_attributed(self):
        mutant = apply_mutation(read_negative("ring_cache.py"), "compound", 2026)
        scan = self.scanner().scan_text(mutant, target="ai_generated.py",
                                        target_license="MIT")
        self.assertTrue(scan.findings, "renamed+reformatted+commented copy escaped")
        self.assertTrue(scan.findings[0].spans)
        self.assertGreater(scan.findings[0].confidence, 0.0)

    def test_scanning_a_file_never_returns_another_files_source(self):
        scan = self.scanner().scan_text(read_negative("roman_form.py"),
                                        target="roman.py", target_license="MIT")
        self.assertTrue(all("roman_form" in f.path for f in scan.findings))

    def test_timings_and_pair_counts_are_reported(self):
        scan = self.scanner(top_verify=2).scan_text(read_negative("ring_cache.py"))
        self.assertIn("probe_ms", scan.timings)
        self.assertGreater(scan.timings["pairs_verified"], 0)

    def test_a_foreign_language_file_is_scanned_without_crashing(self):
        # the gate must not fall over when a repo contains JS/Go: the generic
        # lexer still produces spans, and a Python corpus must not attribute them
        js = ("function debounce(fn, wait) {\n"
              "  let timer = null;\n"
              "  return function () {\n"
              "    clearTimeout(timer);\n"
              "    timer = setTimeout(() => { fn.apply(this, arguments); }, wait);\n"
              "  };\n}\nmodule.exports = debounce;\n")
        scan = self.scanner().scan_text(js, target="debounce.js", language="generic")
        self.assertGreaterEqual(scan.total_spans, 1)
        self.assertEqual(scan.findings, [])


class QueryLineMappingTests(PipelineTestBase):
    def test_reported_query_lines_stay_inside_the_query(self):
        """The finding's query range must not be the upstream source range."""
        filler = "\n".join("VALUE_%d = %d" % (i, i) for i in range(300)) + "\n"
        source_text = filler + read_negative("ring_cache.py")
        rel = "fixture-0.1.0/long_source.py"
        path = os.path.join(self.corpus, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source_text)
        doc = DocRecord(0, "fixture", "0.1.0", rel, "GPL-2.0-only", "test",
                        "python", source_text.count("\n") + 1,
                        len(tokenize_source(source_text)),
                        hashlib.sha256(source_text.encode()).hexdigest(),
                        len(source_text))
        index = FingerprintIndex(Params())
        index.corpus_root = self.corpus
        index.add_document(doc, source_text)
        index.finalize()
        query = read_negative("ring_cache.py")
        scan = Scanner(index, model=None, usage="distribution").scan_text(
            query, target="copied.py", target_license="LicenseRef-Proprietary",
            package_hint="target")
        self.assertTrue(scan.findings)
        query_lines = query.count("\n") + 1
        for finding in scan.findings:
            self.assertLessEqual(finding.matched_query_lines[1], query_lines,
                                 finding.matched_query_lines)
            self.assertGreater(finding.spans[0].pair.line_start, query_lines)


class RiskGradingTests(PipelineTestBase):
    def relabel(self, spdx):
        index = self.load()
        for doc in index.docs:
            doc.license_spdx = spdx
        index.save(self.index_path)

    def test_copyleft_source_into_proprietary_target_blocks(self):
        self.relabel("GPL-2.0-only")
        scan = self.scanner(usage="distribution").scan_text(
            read_negative("ring_cache.py"), target="app.py",
            target_license="LicenseRef-Proprietary")
        self.assertTrue(scan.findings)
        self.assertEqual(scan.findings[0].risk, "S4")
        self.assertTrue(scan.blocking)
        self.assertTrue(scan.findings[0].verdict.conflicts)

    def test_blocking_requires_corroborating_spans(self):
        self.relabel("GPL-2.0-only")
        text = read_negative("ring_cache.py")
        strict = self.scanner(usage="distribution", corroborate_coverage=1.01,
                              corroborate_verbatim=10000, corroborate_confidence=1.01)
        scan = strict.scan_text(text, target="app.py",
                                target_license="LicenseRef-Proprietary")
        self.assertTrue(scan.findings)
        self.assertEqual(scan.findings[0].risk, "S2")
        self.assertFalse(scan.corroborated) if False else self.assertFalse(scan.blocking)
        self.assertTrue(scan.findings[0].corroborated is False)
        self.assertTrue(any("降级" in n for n in scan.notes), scan.notes)
        loose = self.scanner(usage="distribution")
        again = loose.scan_text(text, target="app.py",
                                target_license="LicenseRef-Proprietary")
        self.assertEqual(again.findings[0].risk, "S4")
        self.assertTrue(again.blocking)

    def test_permissive_source_into_copyleft_target_is_advisory_only(self):
        self.relabel("MIT")
        scan = self.scanner(usage="distribution").scan_text(
            read_negative("ring_cache.py"), target="app.py",
            target_license="GPL-3.0-only")
        self.assertTrue(scan.findings)
        self.assertEqual(scan.findings[0].risk, "S1")
        self.assertFalse(scan.blocking)


class EvidenceTests(PipelineTestBase):
    def test_receipt_carries_line_ranges_and_exact_layer_scores(self):
        scan = self.scanner().scan_text(read_negative("ring_cache.py"),
                                        target="copied.py")
        receipt = provenance_receipt(scan, self.load())
        finding = receipt["findings"][0]
        self.assertEqual(finding["source"]["license_spdx"], "Apache-2.0")
        self.assertTrue(finding["evidence"])
        ev = finding["evidence"][0]
        self.assertEqual(len(ev["query_lines"]), 2)
        self.assertEqual(len(ev["source_lines"]), 2)
        self.assertIn("role", ev["exact_layer_jaccard"])

    def test_html_report_is_self_contained(self):
        scan = self.scanner().scan_text(read_negative("ring_cache.py"),
                                        target="copied.py")
        html = to_html(provenance_receipt(scan, self.load(), {"x": "text"}))
        self.assertIn("<html", html)
        for forbidden in ("http://", "https://", "<link", "<script src"):
            self.assertNotIn(forbidden, html, "report must open offline")

    def test_write_outputs_emits_every_requested_format(self):
        scan = self.scanner().scan_text(read_negative("ring_cache.py"),
                                        target="copied.py")
        out = os.path.join(self.tmp, "reports")
        written = write_outputs(scan, self.load(), out, None,
                                ("json", "cdx", "html", "sarif"))
        self.assertEqual(len(written), 4)
        for path in written:
            self.assertTrue(os.path.exists(path) and os.path.getsize(path) > 0, path)
        with open(os.path.join(out, "copied.cdx.json"), encoding="utf-8") as fh:
            bom = json.load(fh)
        self.assertEqual(bom["bomFormat"], "CycloneDX")
        self.assertEqual(bom["specVersion"], "1.6")
        self.assertTrue(bom["components"][0]["evidence"]["occurrences"])
        with open(os.path.join(out, "copied.sarif"), encoding="utf-8") as fh:
            sarif = json.load(fh)
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["tool"]["driver"]["name"], "CodeGuard")
        self.assertTrue(sarif["runs"][0]["results"])

    def test_sarif_carries_both_sides_of_the_evidence(self):
        scan = self.scanner().scan_text(read_negative("ring_cache.py"),
                                        target="copied.py")
        sarif = to_sarif(scan, self.load())
        result = sarif["runs"][0]["results"][0]
        location = result["locations"][0]["physicalLocation"]
        self.assertEqual(location["artifactLocation"]["uri"], "copied.py")
        self.assertGreaterEqual(location["region"]["startLine"], 1)
        self.assertIn("primaryLocationLineHash", result["partialFingerprints"])
        self.assertTrue(result["relatedLocations"][0]["physicalLocation"]
                        ["artifactLocation"]["uri"].endswith("ring_cache.py"))
        self.assertIn(result["properties"]["risk"], {"S0", "S1", "S2", "S3", "S4"})


class CorroborationTests(unittest.TestCase):
    def test_each_evidence_kind_alone_qualifies(self):
        self.assertTrue(corroborates(4, 0.20, 12, 0.40))     # spread + verbatim
        self.assertTrue(corroborates(1, 0.02, 25, 0.40))     # long verbatim run
        self.assertTrue(corroborates(1, 0.02, 5, 0.80))      # confident judge

    def test_single_weak_span_does_not(self):
        # the shape a false positive has: one span, no verbatim run, diluted score
        self.assertFalse(corroborates(1, 0.07, 9, 0.59))
        self.assertFalse(corroborates(1, 0.02, 3, 0.50))

    def test_generic_cli_boilerplate_is_not_a_block(self):
        # Real-world regression: setuptools' vendored wheel CLI matched a GPL
        # mercurial CLI on six argparse spans, 22% coverage, only five verbatim
        # tokens and confidence 0.671. That must remain an S2 review item.
        self.assertFalse(corroborates(6, 0.222, 5, 0.671))


class DiffTests(unittest.TestCase):
    def test_only_added_lines_are_kept(self):
        diff = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,4 @@\n"
                " import os\n+def copied(a, b):\n+    return a + b\n")
        text = strip_diff_markers(diff)
        self.assertNotIn("import os", text)
        self.assertIn("def copied", text)
        self.assertNotIn("@@", text)

    def test_plain_source_is_returned_unchanged(self):
        self.assertEqual(strip_diff_markers("def f():\n    return 1\n"),
                         "def f():\n    return 1\n")


class CliTests(PipelineTestBase):
    def run_cli(self, argv):
        return main(["--workspace", self.workspace] + argv)

    def test_gate_passes_on_unrelated_code(self):
        path = os.path.join(self.tmp, "clean.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(read_negative("attempt_loop.py"))
        self.assertEqual(self.run_cli(["gate", "--diff", path]), 0)

    def test_gate_blocks_a_copyleft_copy(self):
        index = self.load()
        for doc in index.docs:
            doc.license_spdx = "AGPL-3.0-only"
        index.save(self.index_path)
        self.assertEqual(self.run_cli(["gate", "--diff", self._fixture_copy(),
                                       "--license", "LicenseRef-Proprietary",
                                       "--usage", "network_service"]), 1)

    def _fixture_copy(self):
        path = os.path.join(self.tmp, "copied.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(read_negative("ring_cache.py"))
        return path

    def test_gate_writes_sarif_even_when_it_blocks(self):
        index = self.load()
        for doc in index.docs:
            doc.license_spdx = "AGPL-3.0-only"
        index.save(self.index_path)
        sarif_path = os.path.join(self.tmp, "gate.sarif")
        code = self.run_cli(["gate", "--diff", self._fixture_copy(),
                             "--license", "LicenseRef-Proprietary",
                             "--usage", "network_service", "--sarif", sarif_path])
        self.assertEqual(code, 1)
        with open(sarif_path, encoding="utf-8") as fh:
            sarif = json.load(fh)
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertTrue(any(r["level"] == "error"
                            for r in sarif["runs"][0]["results"]))

    def test_gate_passes_against_an_empty_corpus(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        build_index(empty, [], []).save(os.path.join(empty, "index.bin"))
        self.assertEqual(main(["--workspace", empty, "gate",
                              "--diff", self._fixture_copy()]), 0)

    def test_missing_index_exits_with_code_two(self):
        missing = os.path.join(self.tmp, "nowhere")
        with self.assertRaises(SystemExit) as ctx:
            main(["--workspace", missing, "scan", self._fixture_copy()])
        self.assertEqual(ctx.exception.code, 2)

    def test_a_vanished_corpus_is_never_reported_as_clean(self):
        # exact verification re-reads the original text, so a missing corpus
        # would otherwise turn "could not check" into a silent pass
        shutil.rmtree(self.corpus)
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli(["gate", "--diff", self._fixture_copy()])
        self.assertEqual(ctx.exception.code, 2)

    def test_partial_corpus_caveat_reaches_the_report(self):
        os.remove(os.path.join(self.corpus, "fixture-0.1.0", "ring_cache.py"))
        out = os.path.join(self.tmp, "partial-reports")
        self.assertEqual(self.run_cli(["scan", self._fixture_copy(), "--out", out,
                                       "--allow-partial-corpus"]), 0)
        with open(os.path.join(out, "copied.provenance.json"), encoding="utf-8") as fh:
            receipt = json.load(fh)
        self.assertTrue(any("语料原文不完整" in n for n in receipt["notes"]), receipt["notes"])

    def test_doctor_reports_corpus_health(self):
        os.remove(os.path.join(self.corpus, "fixture-0.1.0", "ring_cache.py"))
        with _capture() as buf:
            self.assertEqual(self.run_cli(["doctor"]), 0)
        self.assertIn("2/3 文档可读", buf.getvalue())

    def test_licenses_command_exit_code_follows_the_verdict(self):
        self.assertEqual(self.run_cli(["licenses", "AGPL-3.0-only",
                                       "LicenseRef-Proprietary",
                                       "--usage", "network_service"]), 1)
        self.assertEqual(self.run_cli(["licenses", "MIT", "GPL-3.0-only",
                                       "--usage", "distribution"]), 0)

    def test_doctor_runs_without_a_model(self):
        self.assertEqual(self.run_cli(["doctor"]), 0)


class CorpusReproducibilityTests(unittest.TestCase):
    """`codeguard corpus` must rebuild the corpus the published evidence used."""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MANIFEST = os.path.join(ROOT, "submission", "evidence", "corpus-manifest.json")

    def test_default_packages_match_the_shipped_corpus(self):
        from codeguard.cli import DEFAULT_PACKAGES
        self.assertEqual(len(DEFAULT_PACKAGES), len(set(DEFAULT_PACKAGES)))
        if not os.path.exists(self.MANIFEST):
            self.skipTest("corpus manifest is not present in this checkout")
        with open(self.MANIFEST, encoding="utf-8") as fh:
            manifest = json.load(fh)
        shipped = {e["package"] for e in manifest["entries"]}
        # mercurial (GPL-2.0-or-later) is the source of the flagship provenance
        # evidence; it was missing from the default list, so a fresh corpus
        # could not reproduce it
        self.assertEqual(set(DEFAULT_PACKAGES), shipped)

    def test_every_default_package_is_version_pinned(self):
        from codeguard.cli import DEFAULT_PACKAGES
        from codeguard.corpus import load_pins
        pins = load_pins()
        self.assertEqual(sorted(pins), sorted(DEFAULT_PACKAGES))
        if not os.path.exists(self.MANIFEST):
            self.skipTest("corpus manifest is not present in this checkout")
        with open(self.MANIFEST, encoding="utf-8") as fh:
            manifest = json.load(fh)
        shipped = {e["package"]: e["version"] for e in manifest["entries"]}
        self.assertEqual(pins, shipped)


if __name__ == "__main__":
    unittest.main()
