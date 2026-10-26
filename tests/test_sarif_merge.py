"""Offline tests for folding per-file SARIF reports into a single run."""

import copy

import pytest

from codeguard.report import SARIF_RULES, merge_sarif


def doc(target: str, results=None, rules=None, **props) -> dict:
    driver = {"name": "CodeGuard", "version": "0.5.1",
              "informationUri": "https://example.invalid",
              "rules": copy.deepcopy(SARIF_RULES if rules is None else rules)}
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": driver},
            "columnKind": "utf16CodeUnits",
            "results": results if results is not None else [result(target, "CG004", 3)],
            "properties": dict({"target": target, "targetLicense": "Apache-2.0",
                                "usage": "distribution", "indexFingerprint": "abc",
                                "disclaimer": "工程性风险提示，不构成法律意见。"}, **props),
        }],
    }


def result(uri: str, rule_id: str, rule_index: int, line: int = 1) -> dict:
    return {
        "ruleId": rule_id,
        "ruleIndex": rule_index,
        "level": "note",
        "message": {"text": "message"},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": uri},
            "region": {"startLine": line, "endLine": line}}}]}


def test_single_run_and_rule_table_is_preserved():
    merged = merge_sarif([doc("src/a.py"), doc("src/b.py")])
    assert len(merged["runs"]) == 1
    run = merged["runs"][0]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == [r["id"] for r in SARIF_RULES]
    assert len(run["results"]) == 2
    assert run["properties"]["mergedDocuments"] == 2
    assert run["properties"]["scannedTargets"] == ["src/a.py", "src/b.py"]
    assert "target" not in run["properties"]


def test_results_are_sorted_by_location():
    docs = [doc("z.py"), doc("a.py", [result("a.py", "CG001", 0, line=7)]),
            doc("m.py")]
    merged = merge_sarif(docs)
    uris = [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in merged["runs"][0]["results"]]
    assert uris == sorted(uris)


def test_duplicate_result_is_deduplicated():
    same = result("src/a.py", "CG002", 1, line=12)
    merged = merge_sarif([doc("src/a.py", [same]), doc("src/a.py", [copy.deepcopy(same)])])
    assert len(merged["runs"][0]["results"]) == 1


def test_rule_index_is_remapped_to_merged_order():
    trimmed = [{"id": "CG004", "name": "ProvenanceObservation"},
               {"id": "CG001", "name": "BlockingLicenseConflict"}]
    merged = merge_sarif([
        doc("src/a.py", [result("src/a.py", "CG001", 1)], rules=trimmed),
        doc("src/b.py", [result("src/b.py", "CG004", 0)], rules=trimmed),
    ])
    rules = merged["runs"][0]["tool"]["driver"]["rules"]
    ids = [r["id"] for r in rules]
    for res in merged["runs"][0]["results"]:
        assert rules[res["ruleIndex"]]["id"] == res["ruleId"]
    assert set(ids) == {"CG001", "CG004"}


def test_conflicting_rule_definitions_are_refused():
    other = copy.deepcopy(SARIF_RULES)
    other[0]["shortDescription"]["text"] = "被改写的定义"
    with pytest.raises(ValueError, match="CG001"):
        merge_sarif([doc("src/a.py"), doc("src/b.py", rules=other)])


def test_missing_target_license_mismatch_is_refused():
    with pytest.raises(ValueError, match="targetLicense"):
        merge_sarif([doc("src/a.py"), doc("src/b.py", targetLicense="MIT")])


def test_empty_input_is_refused():
    with pytest.raises(ValueError):
        merge_sarif([])


def test_document_without_run_is_refused():
    bad = {"version": "2.1.0", "runs": []}
    with pytest.raises(ValueError, match="run"):
        merge_sarif([bad])
