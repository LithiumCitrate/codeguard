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

    def test_write_outputs_avoids_filename_collisions_for_nested_paths(self):
        plain = self.scanner().scan_text(read_negative("ring_cache.py"),
                                          target="feature_flags.py")
        out = os.path.join(self.tmp, "collision-reports")
        plain_written = write_outputs(plain, self.load(), out, None, ("json",))
        self.assertEqual([os.path.basename(p) for p in plain_written],
                         ["feature_flags.provenance.json"])

        scan_a = self.scanner().scan_text(read_negative("ring_cache.py"),
                                           target="pkg_a/__init__.py")
        scan_b = self.scanner().scan_text(read_negative("roman_form.py"),
                                           target="pkg_b/__init__.py")
        written_a = write_outputs(scan_a, self.load(), out, None,
                                  ("json", "cdx", "html", "sarif"))
        written_b = write_outputs(scan_b, self.load(), out, None,
                                  ("json", "cdx", "html", "sarif"))
        names_a = {os.path.basename(p) for p in written_a}
        names_b = {os.path.basename(p) for p in written_b}
        self.assertEqual(len(names_a), 4)
        self.assertEqual(len(names_b), 4)
        self.assertFalse(names_a & names_b, "nested targets must not collide")

        hash_a = hashlib.sha256(b"pkg_a/__init__.py").hexdigest()[:6]
        self.assertIn(f"__init__-{hash_a}.provenance.json", names_a)
        with open(os.path.join(out, f"__init__-{hash_a}.provenance.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["subject"]["target"], "pkg_a/__init__.py")

        # Backslashes normalize identically to forward slashes.
        out_win = os.path.join(self.tmp, "win-reports")
        scan_win = self.scanner().scan_text(read_negative("ring_cache.py"),
                                             target="pkg_a\\__init__.py")
        written_win = write_outputs(scan_win, self.load(), out_win, None, ("json",))
        self.assertEqual([os.path.basename(p) for p in written_win],
                         [f"__init__-{hash_a}.provenance.json"])

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
        self.assertTrue(corroborates(1, 0.12, 25, 0.40))     # long verbatim over real coverage
        self.assertTrue(corroborates(3, 0.02, 11, 0.80))     # confident judge + verbatim floor

    def test_single_weak_span_does_not(self):
        # the shape a false positive has: one span, no verbatim run, diluted score
        self.assertFalse(corroborates(1, 0.07, 9, 0.59))
        self.assertFalse(corroborates(1, 0.02, 3, 0.50))

    def test_generic_cli_boilerplate_is_not_a_block(self):
        # Real-world regression: setuptools' vendored wheel CLI matched a GPL
        # mercurial CLI on six argparse spans, 22% coverage, only five verbatim
        # tokens and confidence 0.671. That must remain an S2 review item.
        self.assertFalse(corroborates(6, 0.222, 5, 0.671))

    def test_realworld_20261024_false_blocks_stay_reviews(self):
        # Eleven false blocks from the 25-project sweep (v0.5.0 index); every
        # one rode a corroboration channel without a 10-token verbatim floor.
        # (spans, coverage, verbatim_run, confidence) - recorded per finding.
        cases = [
            (1, 0.25, 2, 0.873),    # pip/_vendor distro import list -> tqdm
            (8, 0.296, 5, 0.845),   # wheel CLI argparse chain -> mercurial cli.py
            (155, 0.502, 5, 0.989),  # sqlmap argparse chain -> glances main
            (1, 0.5, 1, 0.760),     # WBXML hex constants -> paramiko _winapi stub
            (2, 1.0, 2, 0.834),     # ansible facts subclass -> paramiko rsakey
            (4, 0.444, 3, 0.829),   # localstack sync header -> paramiko pkey
            (3, 0.3, 3, 0.872),     # localstack parargs -> paramiko pkey
            (4, 0.21, 3, 0.754),    # localstack hash_func -> paramiko pkey
            (1, 0.031, 26, 0.408),  # defaultdict mixin idiom -> glances curses
            (1, 0.167, 3, 0.756),   # freqtrade import list -> paramiko ecdsakey
            (3, 0.429, 1, 0.998),   # pandas api re-export -> zstandard backend
        ]
        for spans, coverage, verbatim, confidence in cases:
            self.assertFalse(corroborates(spans, coverage, verbatim, confidence),
                             f'({spans}, {coverage}, {verbatim}, {confidence}) must not block')

    def test_real_copies_still_block(self):
        # renamed/commented copies keep 40+ token verbatim runs; the partial
        # case (the only sub-100% mutation class) still clears the floor.
        self.assertTrue(corroborates(12, 0.5, 40, 0.2))
        self.assertTrue(corroborates(2, 0.2, 10, 0.1))
        self.assertTrue(corroborates(1, 0.15, 20, 0.3))


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
        reports = [f for f in os.listdir(out)
                   if f.startswith("copied-") and f.endswith(".provenance.json")]
        self.assertEqual(len(reports), 1, os.listdir(out))
        with open(os.path.join(out, reports[0]), encoding="utf-8") as fh:
            receipt = json.load(fh)
        self.assertTrue(any("语料原文不完整" in n for n in receipt["notes"]), receipt["notes"])

    def test_scan_defaults_to_multilang_extensions_and_respects_ext_flag(self):
        c_src = "\n".join(
            "int sum_step_%d(int acc, int v) { return acc + v * %d; }" % (i, i + 1)
            for i in range(1, 9)
        ) + "\n"
        go_src = "package mathutil\n\n" + "\n".join(
            "func AddStep%d(acc int, v int) int { return acc + v*%d }" % (i, i + 1)
            for i in range(1, 9)
        ) + "\n"
        js_src = "\n".join(
            "export function stepCalc%d(acc, v) { return acc + v * %d; }" % (i, i + 1)
            for i in range(1, 9)
        ) + "\n"
        rs_src = "\n".join(
            "pub fn step_calc_%d(acc: i32, v: i32) -> i32 { acc + v * %d }" % (i, i + 1)
            for i in range(1, 9)
        ) + "\n"

        ml_root = os.path.join(self.tmp, "ml")
        ml_corpus = os.path.join(ml_root, "corpus")
        ml_ws = os.path.join(ml_root, "workspace")
        os.makedirs(ml_ws)
        samples = [
            ("c_pkg", "1.0", "c_pkg/calc.c", "c", c_src),
            ("go_pkg", "1.0", "go_pkg/calc.go", "go", go_src),
            ("js_pkg", "1.0", "js_pkg/calc.js", "javascript", js_src),
            ("rs_pkg", "1.0", "rs_pkg/calc.rs", "rust", rs_src),
        ]
        docs, texts = [], []
        for idx, (pkg, ver, rel, lang, code) in enumerate(samples):
            p = os.path.join(ml_corpus, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(code)
            docs.append(DocRecord(
                idx, pkg, ver, rel, "GPL-3.0-only", "test", lang,
                code.count("\n") + 1, len(tokenize_source(code, lang)),
                hashlib.sha256(code.encode("utf-8")).hexdigest(), len(code),
            ))
            texts.append(code)
        index = FingerprintIndex(Params())
        index.corpus_root = ml_corpus
        for doc, code in zip(docs, texts):
            index.add_document(doc, code, language=doc.language)
        index.finalize()
        index.save(os.path.join(ml_ws, "index.bin"))

        src_dir = os.path.join(self.tmp, "mixed_repo")
        os.makedirs(src_dir)
        files = {
            "app.py": read_negative("attempt_loop.py"),
            "calc.c": c_src,
            "defs.h": "int header_helper(int a, int b);\n",
            "calc.go": go_src,
            "calc.js": js_src,
            "mod.mjs": "export const versionTag = 1;\n",
            "view.jsx": "export function Badge() { return null; }\n",
            "calc.rs": rs_src,
            "notes.txt": "plain text should not be picked up by default\n",
        }
        for name, content in files.items():
            with open(os.path.join(src_dir, name), "w", encoding="utf-8") as fh:
                fh.write(content)

        out_default = os.path.join(self.tmp, "out-ml-default")
        with _capture():
            code = main(["--workspace", ml_ws, "scan", src_dir,
                         "--out", out_default, "--format", "json"])
        self.assertEqual(code, 0)
        emitted = sorted(os.listdir(out_default))
        self.assertEqual(len(emitted), 8, emitted)
        receipts = {}
        for fname in emitted:
            with open(os.path.join(out_default, fname), encoding="utf-8") as fh:
                rec = json.load(fh)
            receipts[os.path.basename(rec["subject"]["target"])] = rec
        self.assertEqual(set(receipts), {
            "app.py", "calc.c", "defs.h", "calc.go",
            "calc.js", "mod.mjs", "view.jsx", "calc.rs",
        })
        for matched_name, expected_pkg in [
            ("calc.c", "c_pkg"), ("calc.go", "go_pkg"),
            ("calc.js", "js_pkg"), ("calc.rs", "rs_pkg"),
        ]:
            pkgs = [f["source"]["package"] for f in receipts[matched_name]["findings"]]
            self.assertIn(expected_pkg, pkgs, receipts[matched_name])

        # Explicit --ext py still narrows directory scans to .py only.
        out_py = os.path.join(self.tmp, "out-ml-py")
        with _capture():
            code = main(["--workspace", ml_ws, "scan", src_dir,
                         "--ext", "py", "--out", out_py, "--format", "json"])
        self.assertEqual(code, 0)
        emitted_py = os.listdir(out_py)
        self.assertEqual(len(emitted_py), 1, emitted_py)
        self.assertTrue(emitted_py[0].startswith("app-"), emitted_py)

        # Explicit single non-py file path scans seamlessly.
        out_single = os.path.join(self.tmp, "out-ml-single")
        with _capture():
            code = main(["--workspace", ml_ws, "scan", os.path.join(src_dir, "calc.rs"),
                         "--out", out_single, "--format", "json"])
        self.assertEqual(code, 0)
        emitted_single = os.listdir(out_single)
        self.assertEqual(len(emitted_single), 1, emitted_single)
        self.assertTrue(emitted_single[0].startswith("calc-"), emitted_single)

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


class Round2AccuracyTests(unittest.TestCase):
    def test_cross_language_candidates_are_filtered_for_known_languages(self):
        tmp = tempdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corpus = os.path.join(tmp, "corpus")
        os.makedirs(os.path.join(corpus, "radare2"), exist_ok=True)
        # C struct pointer assignment that tokenizes very similarly to JS property assignment
        c_code = "\n".join(
            "ac->field_%d = cfg->field_%d;" % (i, i) for i in range(18)
        ) + "\n"
        c_path = os.path.join(corpus, "radare2", "arch_config.c")
        with open(c_path, "w", encoding="utf-8") as fh:
            fh.write(c_code)
        doc_c = DocRecord(
            0, "radare2", "5.9", "radare2/arch_config.c", "LGPL-3.0-only",
            "test", "c", 18, len(tokenize_source(c_code, "c")),
            hashlib.sha256(c_code.encode()).hexdigest(), len(c_code),
        )
        index = FingerprintIndex(Params())
        index.corpus_root = corpus
        index.add_document(doc_c, c_code, language="c")
        index.finalize()

        js_code = "\n".join(
            "g.field_%d = s.field_%d;" % (i, i) for i in range(18)
        ) + "\n"
        scanner = Scanner(index, model=None, min_span_prob=0.35, usage="distribution")
        # Scanning as javascript must filter out C corpus doc
        js_scan = scanner.scan_text(js_code, target="game.js", language="javascript")
        self.assertEqual(js_scan.findings, [])
        # Scanning same tokens as generic (or matching language) still works
        gen_scan = scanner.scan_text(c_code, target="arch_config.c", language="c")
        self.assertTrue(gen_scan.findings)

    def test_c_pure_preprocessor_macro_tables_are_skipped(self):
        tmp = tempdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corpus = os.path.join(tmp, "corpus")
        os.makedirs(os.path.join(corpus, "tcc"), exist_ok=True)
        macro_table = "\n".join(
            "#define REG_VAL_%02d 0x%04X /* macro entry */" % (i, i * 16)
            for i in range(28)
        ) + "\n"
        c_path = os.path.join(corpus, "tcc", "tcc.h")
        with open(c_path, "w", encoding="utf-8") as fh:
            fh.write(macro_table)
        doc = DocRecord(
            0, "tcc", "1.0", "tcc/tcc.h", "LGPL-3.0-only", "test", "c",
            28, len(tokenize_source(macro_table, "c")),
            hashlib.sha256(macro_table.encode()).hexdigest(), len(macro_table),
        )
        index = FingerprintIndex(Params())
        index.corpus_root = corpus
        index.add_document(doc, macro_table, language="c")
        index.finalize()

        query_macros = "\n".join(
            "#define PMU_EVT_%02d 0x%04X /* event */" % (i, i * 16)
            for i in range(28)
        ) + "\n"
        scanner = Scanner(index, model=None, min_span_prob=0.35, usage="distribution")
        scan = scanner.scan_text(query_macros, target="pmu.h", language="c")
        self.assertEqual(scan.findings, [])

        # Non-preprocessor C code inside #ifdef still matches normally
        func_code = "#ifdef USE_IMPL\n" + "\n".join(
            "int val_%d = compute_item(buf, %d);" % (i, i) for i in range(16)
        ) + "\n#endif\n"
        os.makedirs(os.path.join(corpus, "lib"), exist_ok=True)
        func_path = os.path.join(corpus, "lib", "impl.c")
        with open(func_path, "w", encoding="utf-8") as fh:
            fh.write(func_code)
        doc2 = DocRecord(
            0, "lib", "1.0", "lib/impl.c", "GPL-3.0-only", "test", "c",
            18, len(tokenize_source(func_code, "c")),
            hashlib.sha256(func_code.encode()).hexdigest(), len(func_code),
        )
        index2 = FingerprintIndex(Params())
        index2.corpus_root = corpus
        index2.add_document(doc2, func_code, language="c")
        index2.finalize()
        func_scan = Scanner(index2, model=None, min_span_prob=0.35, usage="distribution").scan_text(
            func_code, target="copy.c", language="c")
        self.assertTrue(func_scan.findings)

    def test_ultra_weak_single_span_coincidence_downgraded_to_s0(self):
        tmp = tempdir()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corpus = os.path.join(tmp, "corpus")
        os.makedirs(os.path.join(corpus, "glances"), exist_ok=True)
        # Shared 1-span boilerplate with short verbatim run (<6) inside a much larger file
        boilerplate = (
            "def configure_cli(parser, cfg):\n"
            "    parser.add_argument('--host', default='127.0.0.1')\n"
            "    parser.add_argument('--port', dest='port', default=8080)\n"
            "    parser.add_argument('--mode', choices=cfg, default='fast')\n"
            "    return parser.parse_args()\n"
        )
        src_path = os.path.join(corpus, "glances", "main.py")
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(boilerplate)
        doc = DocRecord(
            0, "glances", "4.5", "glances/main.py", "LGPL-3.0-only", "test",
            "python", 5, len(tokenize_source(boilerplate, "python")),
            hashlib.sha256(boilerplate.encode()).hexdigest(), len(boilerplate),
        )
        index = FingerprintIndex(Params())
        index.corpus_root = corpus
        index.add_document(doc, boilerplate, language="python")
        index.finalize()

        # Renamed variables give verbatim_run < 6, and 10+ unrelated functions keep coverage < 0.15
        renamed_head = (
            "def setup_options(cli_op, opt):\n"
            "    cli_op.add_argument('--bind', default='127.0.0.2')\n"
            "    cli_op.add_argument('--nums', dest='nums', default=9090)\n"
            "    cli_op.add_argument('--kind', choices=opt, default='slow')\n"
            "    return cli_op.parse_args()\n"
        )
        filler = "\n".join(
            "def unrelated_%d(x_%d, y_%d):\n    z_%d = x_%d * %d + y_%d\n    return z_%d - %d\n"
            % (i, i, i, i, i, i + 3, i, i, i + 1)
            for i in range(18)
        )
        scanner = Scanner(index, model=None, min_span_prob=0.45, usage="distribution")
        scan = scanner.scan_text(renamed_head + "\n" + filler,
                                 target="cli.py", target_license="MIT", language="python")
        self.assertEqual(len(scan.findings), 1)
        f = scan.findings[0]
        self.assertFalse(f.corroborated)
        self.assertEqual(len(f.spans), 1)
        self.assertLess(f.coverage, 0.15)
        self.assertLess(f.max_verbatim_run, 6)
        self.assertEqual(f.risk, "S0")
        self.assertFalse(scan.blocking)


if __name__ == "__main__":
    unittest.main()
