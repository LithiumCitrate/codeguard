"""External, labelled evaluation of the gate.

The mutation benchmark answers "does the detector survive rewrites of code we
already indexed?".  It cannot answer "how often does the gate fire on code that
was written independently?".  This module consumes a JSONL manifest of labelled
samples (``clean`` or ``copied``) and reports both directions:

* clean samples: false blocks, advisory findings and a one-sided Clopper-Pearson
  upper bound for the false-block rate;
* copied samples: attribution rate, blocking rate and top-1 source accuracy.

Manifests can inline code or point at files.  The harness itself is dependency
free and never writes the submitted code into the report, only findings and
metrics.  That keeps third-party evaluation sets out of the repository.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field

from .adjudicate import Scanner
from .license_intel import RISK_LABELS

RISK_ORDER = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "S4": 4}
LABELS = ("clean", "copied")


@dataclass
class EvalSample:
    id: str
    label: str
    code: str
    language: str = "python"
    license: str = "LicenseRef-Proprietary"
    usage: str = "distribution"
    source_package: str = ""
    source_path: str = ""
    note: str = ""


@dataclass
class EvalResult:
    sample: EvalSample
    total_spans: int
    matched_spans: int
    findings: list
    elapsed_ms: float
    max_risk: str = ""
    blocking: bool = False
    attributed: bool = False
    detected: bool = False
    top1: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.sample.id,
            "label": self.sample.label,
            "language": self.sample.language,
            "usage": self.sample.usage,
            "total_spans": self.total_spans,
            "matched_spans": self.matched_spans,
            "finding_count": len(self.findings),
            "max_risk": self.max_risk,
            "blocking": self.blocking,
            "attributed": self.attributed,
            "detected": self.detected,
            "top1": self.top1,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "findings": self.findings[:10],
        }


def _read_code(obj: dict, base_dir: str) -> str:
    code = obj.get("code")
    if isinstance(code, str):
        return code
    path = obj.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("manifest entry needs either 'code' or 'path'")
    resolved = path if os.path.isabs(path) else os.path.join(base_dir, path)
    with open(resolved, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def load_manifest(path: str) -> list:
    """Load a JSONL manifest; relative paths resolve next to the manifest."""
    base_dir = os.path.dirname(os.path.abspath(path))
    samples = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("manifest line %d is not JSON: %s" % (lineno, exc))
            if not isinstance(obj, dict):
                raise ValueError("manifest line %d is not an object" % lineno)
            label = obj.get("label", "clean")
            if label not in LABELS:
                raise ValueError("manifest line %d: label must be clean or copied" % lineno)
            sample_id = str(obj.get("id") or "sample-%d" % lineno)
            samples.append(EvalSample(
                id=sample_id,
                label=label,
                code=_read_code(obj, base_dir),
                language=str(obj.get("language", "python")),
                license=str(obj.get("license", "LicenseRef-Proprietary")),
                usage=str(obj.get("usage", "distribution")),
                source_package=str(obj.get("source_package", "")),
                source_path=str(obj.get("source_path", "")),
                note=str(obj.get("note", "")),
            ))
    return samples


def _finding_summary(finding) -> dict:
    return {
        "package": finding.package,
        "version": finding.version,
        "path": finding.path,
        "license": finding.license_spdx,
        "risk": finding.risk,
        "risk_label": RISK_LABELS[finding.risk],
        "confidence": round(finding.confidence, 4),
        "coverage": round(finding.coverage, 4),
        "matched_spans": len(finding.spans),
        "verbatim_run": finding.max_verbatim_run,
        "verdict": finding.verdict.status if finding.verdict else "",
        "corroborated": finding.corroborated,
    }


def _matches_expected(finding, sample: EvalSample) -> bool:
    if not sample.source_package:
        return True
    if finding.package != sample.source_package:
        return False
    if sample.source_path and sample.source_path not in finding.path:
        return False
    return True


def _highest_risk(findings) -> str:
    if not findings:
        return ""
    return max((f.risk for f in findings), key=lambda r: RISK_ORDER.get(r, -1))


def _percentile(values, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    pos = (len(ordered) - 1) * q
    lower = int(math.floor(pos))
    upper = min(lower + 1, len(ordered) - 1)
    weight = pos - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0 if k < n else 1.0
    return sum(math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
               for i in range(k + 1))


def clopper_pearson_upper(successes: int, n: int, confidence: float = 0.95) -> float:
    """One-sided exact upper bound for a binomial rate.

    ``0/164`` must not be reported as "zero false positives"; the honest claim is
    "0 observed, upper bound <= x% at 95% confidence".  For zero events the
    closed form is ``1 - (1-confidence)**(1/n)``; the general case is a binary
    search on the binomial CDF.
    """
    if n <= 0:
        return 1.0
    if successes <= 0:
        return 1.0 - (1.0 - confidence) ** (1.0 / n)
    if successes >= n:
        return 1.0
    alpha = 1.0 - confidence
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _binom_cdf(successes, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def run_eval(index, model, samples, fail_on=("S3", "S4"),
             min_span_prob: float = 0.55, top_verify: int = 4,
             corroborate_coverage: float = 0.15,
             corroborate_verbatim: int = 20,
             corroborate_confidence: float = 0.75,
             use_idf: bool = True, metadata: dict | None = None) -> dict:
    if not samples:
        raise ValueError("evaluation manifest is empty")
    scanners = {}

    def scanner_for(usage):
        if usage not in scanners:
            scanners[usage] = Scanner(
                index, model=model, usage=usage, min_span_prob=min_span_prob,
                top_verify=top_verify, corroborate_coverage=corroborate_coverage,
                corroborate_verbatim=corroborate_verbatim,
                corroborate_confidence=corroborate_confidence, use_idf=use_idf)
        return scanners[usage]

    results = []
    for sample in samples:
        started = time.perf_counter()
        scan = scanner_for(sample.usage).scan_text(
            sample.code, target=sample.id, target_license=sample.license,
            package_hint="__eval__", language=sample.language)
        elapsed = (time.perf_counter() - started) * 1000.0
        findings = [_finding_summary(f) for f in scan.findings]
        raw = scan.findings
        blocking = any(f.risk in fail_on for f in raw)
        expected = [f for f in raw if _matches_expected(f, sample)] \
            if sample.label == "copied" else []
        attributed = bool(expected) if sample.source_package else bool(raw)
        detected = any(f.risk in fail_on for f in expected) \
            if sample.label == "copied" else blocking
        top1 = bool(raw and sample.source_package and _matches_expected(raw[0], sample))
        results.append(EvalResult(sample, scan.total_spans, scan.matched_spans,
                                  findings, elapsed, _highest_risk(raw),
                                  blocking, attributed, detected, top1))

    clean = [r for r in results if r.sample.label == "clean"]
    copied = [r for r in results if r.sample.label == "copied"]
    clean_blocks = sum(1 for r in clean if r.blocking)
    clean_any = sum(1 for r in clean if r.findings)
    clean_s2 = sum(1 for r in clean if r.max_risk in ("S2", "S3", "S4"))
    copied_attr = sum(1 for r in copied if r.attributed)
    copied_det = sum(1 for r in copied if r.detected)
    copied_top1 = sum(1 for r in copied if r.top1)
    risk_counts = {risk: 0 for risk in RISK_ORDER}
    for result in results:
        for finding in result.findings:
            risk_counts[finding["risk"]] = risk_counts.get(finding["risk"], 0) + 1
    latencies = [r.elapsed_ms for r in results]
    summary = {
        "samples": len(results),
        "clean": len(clean),
        "copied": len(copied),
        "clean_blocking": clean_blocks,
        "clean_blocking_rate": round(clean_blocks / len(clean), 4) if clean else None,
        "clean_blocking_upper95": round(clopper_pearson_upper(clean_blocks, len(clean)), 4) if clean else None,
        "clean_any_finding": clean_any,
        "clean_s2_or_higher": clean_s2,
        "copied_attributed": copied_attr,
        "copied_attribution_rate": round(copied_attr / len(copied), 4) if copied else None,
        "copied_detected": copied_det,
        "copied_detection_rate": round(copied_det / len(copied), 4) if copied else None,
        "copied_top1": copied_top1,
        "copied_top1_rate": round(copied_top1 / len(copied), 4) if copied else None,
        "risk_counts": risk_counts,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 2) if latencies else 0.0,
            "mean": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        },
        "total_spans": sum(r.total_spans for r in results),
        "matched_spans": sum(r.matched_spans for r in results),
    }
    notes = ["本评测只覆盖清单中的样本与当前语料；未出现的语言、项目或生成方式不受此结果保证。"]
    if clean:
        notes.append(
            "干净样本 %d/%d 出现阻断级误报；单侧 95%% Clopper-Pearson 上限 %.2f%%。"
            % (clean_blocks, len(clean), 100.0 * (summary["clean_blocking_upper95"] or 0.0)))
    if copied:
        notes.append("复制样本按预期来源计算归因；未指定 source_package 的样本只统计阻断。")
    return {
        "schema": "codeguard.eval/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metadata": dict(metadata or {}),
        "settings": {
            "fail_on": list(fail_on),
            "min_span_prob": min_span_prob,
            "top_verify": top_verify,
            "corroborate_coverage": corroborate_coverage,
            "corroborate_verbatim": corroborate_verbatim,
            "corroborate_confidence": corroborate_confidence,
            "use_idf": use_idf,
        },
        "summary": summary,
        "samples": [r.as_dict() for r in results],
        "notes": notes,
    }


def _md_cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def to_markdown(payload: dict, title: str = "CodeGuard 外部评测") -> str:
    s = payload["summary"]
    lines = ["# " + title, "",
             "- 样本：%d（clean %d / copied %d）" % (s["samples"], s["clean"], s["copied"]),
             "- 生成时间：%s" % payload["generated_at"],
             "- 判定阈值：fail_on=%s，min_span_prob=%.2f" % (
                 ",".join(payload["settings"]["fail_on"]),
                 payload["settings"]["min_span_prob"])]
    dataset = payload.get("dataset")
    if dataset:
        lines.append("- 数据集：%s %s（%s；SHA-256 `%s`）" % (
            dataset.get("name", ""), dataset.get("version", ""),
            dataset.get("license", ""), dataset.get("sha256", "")))
        lines.append("- 来源：%s" % dataset.get("url", ""))
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    if s["clean"]:
        lines.append("| 干净样本阻断级误报 | %d / %d（%.2f%%） |" % (
            s["clean_blocking"], s["clean"], 100.0 * s["clean_blocking_rate"]))
        lines.append("| 干净样本误阻断率 95%% 单侧上限 | %.2f%% |" % (
            100.0 * s["clean_blocking_upper95"]))
        lines.append("| 干净样本出现任意命中 | %d / %d |" % (
            s["clean_any_finding"], s["clean"]))
        lines.append("| 干净样本出现 S2 及以上 | %d / %d |" % (
            s["clean_s2_or_higher"], s["clean"]))
    if s["copied"]:
        lines.append("| 复制样本归因到预期来源 | %d / %d（%.2f%%） |" % (
            s["copied_attributed"], s["copied"],
            100.0 * (s["copied_attribution_rate"] or 0.0)))
        lines.append("| 复制样本达到阻断阈值 | %d / %d（%.2f%%） |" % (
            s["copied_detected"], s["copied"],
            100.0 * (s["copied_detection_rate"] or 0.0)))
        lines.append("| 复制样本 top-1 来源正确 | %d / %d（%.2f%%） |" % (
            s["copied_top1"], s["copied"],
            100.0 * (s["copied_top1_rate"] or 0.0)))
    lines.append("| 片段总数 / 命中片段 | %d / %d |" % (s["total_spans"], s["matched_spans"]))
    lines.append("| 单样本耗时 p50 / p95 / max | %.1f / %.1f / %.1f ms |" % (
        s["latency_ms"]["p50"], s["latency_ms"]["p95"], s["latency_ms"]["max"]))
    lines.append("")
    lines.append("## 风险分布（命中条数）")
    lines.append("")
    lines.append("| " + " | ".join(RISK_ORDER) + " |")
    lines.append("|" + "---|" * len(RISK_ORDER))
    lines.append("| " + " | ".join(str(s["risk_counts"].get(r, 0)) for r in RISK_ORDER) + " |")
    lines.append("")
    failures = [x for x in payload["samples"]
                if (x["label"] == "clean" and x["blocking"])
                or (x["label"] == "copied" and not x["detected"])]
    lines.append("## 未通过样本")
    lines.append("")
    if failures:
        lines.append("| 样本 | 标签 | 最高风险 | 说明 |")
        lines.append("|---|---|---|---|")
        for x in failures[:30]:
            top = ", ".join("%s@%s:%s" % (f["package"], f["version"], f["path"])
                            for f in x["findings"][:2])
            lines.append("| %s | %s | %s | %s |" % (
                _md_cell(x["id"]), x["label"], x["max_risk"] or "-",
                _md_cell(top or "无命中")))
    else:
        lines.append("无。")
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    for note in payload.get("notes", []):
        lines.append("- " + note)
    return "\n".join(lines) + "\n"


def write_eval(payload: dict, out_dir: str, title: str = "CodeGuard 外部评测") -> list:
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "eval.json")
    md_path = os.path.join(out_dir, "eval.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(payload, title))
    return [json_path, md_path]
