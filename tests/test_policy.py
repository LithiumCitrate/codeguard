"""Unit and end-to-end CLI tests for the project-level compliance policy engine."""

import json
import os
import shutil
import unittest

from codeguard.adjudicate import Scanner
from codeguard.cli import main
from codeguard.policy import PolicyError, apply_policy, load_policy
from codeguard.report import provenance_receipt, to_html, to_sarif

from helpers import build_index, make_corpus, read_negative, tempdir


class PolicyUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.corpus = os.path.join(self.tmp, "corpus")
        self.workspace = os.path.join(self.tmp, "workspace")
        os.makedirs(self.workspace)
        docs, texts = make_corpus(["ring_cache.py", "roman_form.py"], self.corpus)
        docs[0].package = "urllib3"
        docs[0].license_spdx = "GPL-3.0-only"
        docs[1].package = "helperpkg"
        docs[1].license_spdx = "BSD-3-Clause"
        index = build_index(self.corpus, docs, texts)
        self.index_path = os.path.join(self.workspace, "index.bin")
        index.save(self.index_path)
        self.index = index

    def _write_policy(self, payload, name=".codeguard.json"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(payload, str):
                fh.write(payload)
            else:
                json.dump(payload, fh, ensure_ascii=False)
        return path

    def test_allow_packages_waives_to_s1_without_deleting_findings(self):
        pol_path = self._write_policy({
            "project_license": "MIT",
            "usage": "distribution",
            "fail_on": ["S3", "S4"],
            "allow_packages": [
                {"package": "urllib3", "reason": "内部已登记合规归档"},
            ],
        })
        policy = load_policy(pol_path)
        scan = Scanner(self.index, usage="distribution").scan_text(
            read_negative("ring_cache.py"), target="app.py",
            target_license="MIT", package_hint="app",
        )
        self.assertTrue(scan.blocking)
        before_count = len(scan.findings)
        audit = apply_policy(scan, policy)

        # Findings must never be silently dropped.
        self.assertEqual(len(scan.findings), before_count)
        self.assertFalse(scan.blocking)
        waived = [f for f in scan.findings if f.package == "urllib3"][0]
        self.assertEqual(waived.risk, "S1")
        self.assertEqual(waived.policy_action, "waived")
        self.assertEqual(waived.policy_reason, "内部已登记合规归档")
        self.assertEqual(waived.as_dict()["policy_action"], "waived")
        self.assertEqual(audit["waived_count"], 1)
        self.assertEqual(audit["denied_count"], 0)
        self.assertTrue(any("策略豁免" in n for n in scan.notes))

        # Provenance receipt, HTML, and SARIF preserve the audit metadata.
        receipt = provenance_receipt(scan, self.index)
        self.assertEqual(receipt["policy_audit"]["waived_count"], 1)
        self.assertEqual(receipt["findings"][0]["policy_action"], "waived")
        html = to_html(receipt)
        self.assertIn("合规策略审计", html)
        self.assertIn("内部已登记合规归档", html)
        sarif = to_sarif(scan, self.index)
        self.assertEqual(sarif["runs"][0]["properties"]["policyAudit"]["waived_count"], 1)

    def test_deny_licenses_promotes_corroborated_finding_to_s4(self):
        pol_path = self._write_policy({
            "project_license": "MIT",
            "usage": "distribution",
            "deny_licenses": ["BSD-3-Clause"],
        })
        policy = load_policy(pol_path)
        scan = Scanner(self.index, usage="distribution").scan_text(
            read_negative("roman_form.py"), target="roman.py",
            target_license="MIT", package_hint="app",
        )
        self.assertTrue(scan.findings)
        self.assertEqual(scan.findings[0].risk, "S1")
        self.assertFalse(scan.blocking)

        audit = apply_policy(scan, policy)
        self.assertEqual(scan.findings[0].risk, "S4")
        self.assertEqual(scan.findings[0].policy_action, "denied")
        self.assertTrue(scan.blocking)
        self.assertEqual(audit["denied_count"], 1)
        self.assertTrue(any("策略阻断" in n for n in scan.notes))

    def test_deny_licenses_does_not_promote_uncorroborated_finding(self):
        pol_path = self._write_policy({"deny_licenses": ["BSD-3-Clause"]})
        policy = load_policy(pol_path)
        scan = Scanner(
            self.index, usage="distribution",
            corroborate_coverage=1.01, corroborate_verbatim=10000,
            corroborate_confidence=1.01,
        ).scan_text(
            read_negative("roman_form.py"), target="roman.py",
            target_license="MIT", package_hint="app",
        )
        self.assertTrue(scan.findings)
        scan.findings[0].corroborated = False
        audit = apply_policy(scan, policy)
        self.assertEqual(audit["denied_count"], 0)
        self.assertNotEqual(scan.findings[0].risk, "S4")

    def test_invalid_policy_files_raise_policy_error(self):
        bad_cases = [
            os.path.join(self.tmp, "missing.json"),
            self._write_policy("{not json", "bad_json.json"),
            self._write_policy([], "not_obj.json"),
            self._write_policy({"unknown_key": 1}, "unknown.json"),
            self._write_policy({"project_license": 123}, "bad_lic.json"),
            self._write_policy({"usage": "saas"}, "bad_usage.json"),
            self._write_policy({"fail_on": "S4"}, "bad_failon_type.json"),
            self._write_policy({"fail_on": ["S9"]}, "bad_failon_val.json"),
            self._write_policy({"allow_packages": [123]}, "bad_allow_item.json"),
            self._write_policy({"allow_packages": [{"reason": "only"}]}, "bad_allow_dict.json"),
            self._write_policy({"deny_licenses": [""]}, "bad_deny.json"),
        ]
        for path in bad_cases:
            with self.assertRaises(PolicyError, msg=path):
                load_policy(path)

    def test_cli_gate_and_scan_with_policy_end_to_end(self):
        copied_ring = os.path.join(self.tmp, "copied_ring.py")
        with open(copied_ring, "w", encoding="utf-8") as fh:
            fh.write(read_negative("ring_cache.py"))
        copied_roman = os.path.join(self.tmp, "copied_roman.py")
        with open(copied_roman, "w", encoding="utf-8") as fh:
            fh.write(read_negative("roman_form.py"))

        # 1) Waived package passes gate with exit code 0 while preserving finding in report
        waive_policy = self._write_policy({
            "project_license": "MIT",
            "usage": "distribution",
            "fail_on": ["S3", "S4"],
            "allow_packages": [{"package": "urllib3", "reason": "内部已登记合规归档"}],
        }, "waive.json")
        out_waive = os.path.join(self.tmp, "out-waive")
        code = main([
            "--workspace", self.workspace, "gate",
            "--diff", copied_ring, "--policy", waive_policy, "--out", out_waive,
        ])
        self.assertEqual(code, 0)
        receipt = json.load(open(os.path.join(out_waive, "diff.provenance.json"), encoding="utf-8"))
        self.assertEqual(len(receipt["findings"]), 1)
        self.assertEqual(receipt["findings"][0]["risk"], "S1")
        self.assertEqual(receipt["findings"][0]["policy_action"], "waived")
        self.assertEqual(receipt["policy_audit"]["waived_count"], 1)

        # 2) Denied license forces blocking S4 and exit code 1
        deny_policy = self._write_policy({
            "project_license": "MIT",
            "usage": "distribution",
            "deny_licenses": ["BSD-3-Clause"],
        }, "deny.json")
        out_deny = os.path.join(self.tmp, "out-deny")
        code = main([
            "--workspace", self.workspace, "gate",
            "--diff", copied_roman, "--policy", deny_policy, "--out", out_deny,
        ])
        self.assertEqual(code, 1)
        receipt2 = json.load(open(os.path.join(out_deny, "diff.provenance.json"), encoding="utf-8"))
        self.assertEqual(receipt2["findings"][0]["risk"], "S4")
        self.assertEqual(receipt2["findings"][0]["policy_action"], "denied")

        # 3) scan command with --policy applies defaults and writes audit into reports
        out_scan = os.path.join(self.tmp, "out-scan")
        code = main([
            "--workspace", self.workspace, "scan", copied_roman,
            "--policy", deny_policy, "--out", out_scan,
        ])
        self.assertEqual(code, 0)
        scan_reports = [f for f in os.listdir(out_scan)
                        if f.startswith("copied_roman-") and f.endswith(".provenance.json")]
        self.assertEqual(len(scan_reports), 1, os.listdir(out_scan))
        with open(os.path.join(out_scan, scan_reports[0]), encoding="utf-8") as fh:
            scan_receipt = json.load(fh)
        self.assertEqual(scan_receipt["subject"]["target_license"], "MIT")
        self.assertEqual(scan_receipt["subject"]["usage_mode"], "distribution")
        self.assertEqual(scan_receipt["findings"][0]["risk"], "S4")
        self.assertEqual(scan_receipt["policy_audit"]["denied_count"], 1)

        # 4) Invalid policy exits with code 2
        bad_pol = self._write_policy({"fail_on": "S4"}, "cli_bad.json")
        with self.assertRaises(SystemExit) as ctx:
            main(["--workspace", self.workspace, "gate",
                  "--diff", copied_ring, "--policy", bad_pol])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
