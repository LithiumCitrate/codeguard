"""Licence-obligation reasoning: the verdicts a reviewer can check by hand."""

import unittest

from codeguard.license_intel import (PROFILES, analyze, normalize_expression,
                                     profile_for, resolve_spdx, risk_level)

# (source, target, usage, expected status)
VERDICTS = [
    ("MIT", "GPL-3.0-only", "distribution", "compatible"),
    ("BSD-3-Clause", "MIT", "distribution", "compatible"),
    ("Apache-2.0", "GPL-3.0-only", "distribution", "compatible"),
    ("Apache-2.0", "GPL-2.0-only", "distribution", "incompatible"),
    ("GPL-3.0-only", "MIT", "distribution", "incompatible"),
    ("GPL-2.0-only", "LicenseRef-Proprietary", "distribution", "incompatible"),
    ("AGPL-3.0-only", "GPL-3.0-only", "network_service", "conditional"),
    ("AGPL-3.0-only", "AGPL-3.0-only", "network_service", "conditional"),
    ("AGPL-3.0-only", "AGPL-3.0-only", "distribution", "compatible"),
    ("AGPL-3.0-only", "MIT", "network_service", "incompatible"),
    ("AGPL-3.0-only", "LicenseRef-Proprietary", "internal_use", "compatible"),
    ("GPL-3.0-only", "LicenseRef-Proprietary", "internal_use", "compatible"),
    ("LGPL-2.1", "LicenseRef-Proprietary", "dynamic_link", "conditional"),
    ("LGPL-2.1", "LicenseRef-Proprietary", "static_link", "conditional"),
    ("MPL-2.0", "MIT", "distribution", "conditional"),
    ("MulanPSL-2.0", "GPL-3.0-only", "distribution", "compatible"),
    ("GPL-3.0-only", "GPL-3.0-only", "distribution", "compatible"),
    ("CC0-1.0", "GPL-3.0-only", "distribution", "compatible"),
    ("UNKNOWN", "MIT", "distribution", "unknown"),
    ("MIT", "UNKNOWN", "distribution", "unknown"),
]


class VerdictTests(unittest.TestCase):
    def test_expected_matrix(self):
        for src, dst, usage, expected in VERDICTS:
            got = analyze(src, dst, usage).status
            self.assertEqual(got, expected, "%s -> %s (%s)" % (src, dst, usage))

    def test_incompatible_always_explains_why(self):
        v = analyze("GPL-3.0-only", "MIT", "distribution")
        self.assertTrue(v.conflicts, "an incompatible verdict must be argued")
        self.assertTrue(any("源码" in o for o in v.obligations))

    def test_permissive_still_carries_notice_obligation(self):
        v = analyze("BSD-3-Clause", "MIT", "distribution")
        self.assertEqual(v.status, "compatible")
        self.assertTrue(any("声明" in o for o in v.obligations))

    def test_apache_patent_grant_needs_notice(self):
        v = analyze("Apache-2.0", "MIT", "distribution")
        self.assertTrue(any("NOTICE" in o for o in v.obligations))

    def test_unknown_is_never_auto_passed(self):
        v = analyze("Weird-Custom-1.0", "MIT", "distribution")
        self.assertEqual(v.status, "unknown")
        self.assertTrue(v.notes)

    def test_agpl_network_duty_survives_the_same_licence(self):
        v = analyze("AGPL-3.0-only", "AGPL-3.0-only", "network_service")
        self.assertEqual(v.status, "conditional")
        self.assertTrue(any("§13" in o for o in v.obligations), v.obligations)

    def test_upgrading_to_agpl_is_an_obligation_not_only_a_note(self):
        v = analyze("AGPL-3.0-only", "GPL-3.0-only", "network_service")
        self.assertEqual(v.status, "conditional")
        self.assertTrue(any("整体按 AGPL-3.0-only" in o for o in v.obligations),
                        v.obligations)

    def test_risk_grading_blocks_copyleft_pollution(self):
        self.assertEqual(risk_level("incompatible", 0.9, "distribution"), "S4")
        self.assertEqual(risk_level("conditional", 0.9, "distribution"), "S3")
        self.assertEqual(risk_level("compatible", 0.9, "distribution"), "S1")
        self.assertEqual(risk_level("compatible", 0.2, "distribution"), "S0")

    def test_blocking_requires_evidence_not_just_a_conflict(self):
        # a 0.5-probability span is a review item; without this the gate would
        # break builds on structural coincidence between unrelated projects
        self.assertEqual(risk_level("incompatible", 0.54, "distribution"), "S2")
        self.assertEqual(risk_level("incompatible", 0.60, "distribution"), "S3")
        self.assertEqual(risk_level("incompatible", 0.76, "distribution"), "S4")
        self.assertEqual(risk_level("incompatible", 0.76, "inline_copy"), "S3")


class ResolutionTests(unittest.TestCase):
    def test_short_and_free_text_forms(self):
        for text, expected in [("GPL v3", "GPL-3.0-only"),
                               ("gpl3", "GPL-3.0-only"),
                               ("GPL v2 or later", "GPL-2.0-or-later"),
                               ("GPL-2.0", "GPL-2.0-only"),
                               ("Apache 2", "Apache-2.0"),
                               ("LGPL 2.1", "LGPL-2.1"),
                               ("BSD 2-Clause", "BSD-2-Clause"),
                               ("Proprietary", "LicenseRef-Proprietary"),
                               ("木兰宽松许可证 v2", "MulanPSL-2.0"),
                               ("MulanPSL", "MulanPSL-2.0"),
                               ("MIT License", "MIT")]:
            self.assertEqual(normalize_expression(text)[0], expected, text)

    def test_expressions_take_the_stronger_side(self):
        self.assertEqual(normalize_expression("MIT AND GPL-3.0-only")[0],
                         "GPL-3.0-only")
        self.assertEqual(normalize_expression("Apache-2.0 OR MIT")[0], "Apache-2.0")

    def test_unresolvable_stays_unknown(self):
        self.assertEqual(resolve_spdx([("Public Domain", "arg")])[0], "UNKNOWN")
        self.assertEqual(resolve_spdx([("", "arg")])[0], "UNKNOWN")

    def test_first_resolvable_candidate_wins(self):
        spdx, origin = resolve_spdx([("UNKNOWN", "pep639-expression"),
                                     ("MIT", "license-field")])
        self.assertEqual((spdx, origin), ("MIT", "license-field"))

    def test_profiles_cover_the_corpus(self):
        for spdx in ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0",
                     "LGPL-2.1", "LGPL-3.0", "GPL-2.0-only", "GPL-2.0-or-later",
                     "GPL-3.0-only", "AGPL-3.0-only", "PSF-2.0", "MulanPSL-2.0",
                     "LicenseRef-Proprietary", "UNKNOWN"):
            self.assertIn(spdx, PROFILES)
            self.assertNotEqual(profile_for(spdx).family, "missing")


if __name__ == "__main__":
    unittest.main()
