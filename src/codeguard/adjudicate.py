"""Adjudication pipeline: retrieve, verify, score, then reason about licences.

Stage layout matters for the results table as much as for runtime:

1. LSH prefilter (cheap, high recall)
2. exact verification of the few surviving candidates
3. logistic-regression probability per span pair
4. span -> file aggregation (coverage + peak confidence)
5. licence-obligation reasoning and risk grading
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from .evidence import CandidateReader, PairScore, score_pair
from .license_intel import RISK_LABELS, analyze, risk_level

DEFAULT_MIN_SPAN_PROB = 0.55
DEFAULT_TOP_VERIFY = 4
DEFAULT_CORROBORATE_COVERAGE = 0.15
DEFAULT_CORROBORATE_VERBATIM = 20
DEFAULT_CORROBORATE_CONFIDENCE = 0.75
DEFAULT_CORROBORATE_SPAN_VERBATIM = 10


def corroborates(spans: int, coverage: float, verbatim_run: int, confidence: float,
                 coverage_min: float = DEFAULT_CORROBORATE_COVERAGE,
                 verbatim_min: int = DEFAULT_CORROBORATE_VERBATIM,
                 confidence_min: float = DEFAULT_CORROBORATE_CONFIDENCE) -> bool:
    """Is the evidence strong enough to break a build over?

    A licence conflict proven by one isolated span is not a build break. Real
    reuse shows up either structurally (several spans over a sixth of the file
    *and* a non-trivial verbatim run), through a long verbatim run, or
    statistically (the judge is confident about the file as a whole).

    The 10-token floor on the structural branch is not cosmetic: real-world
    scans of setuptools' vendored wheel CLI produced six scattered argparse
    spans, 22% coverage, a five-token verbatim run and confidence 0.671 - enough
    to pass the old OR rule and falsely block a GPL match. Generic CLI
    boilerplate should be reviewable, not build-breaking; renamed/commented/
    dead-code copies in the benchmark retain 40+ token runs and still qualify.
    """
    structural = (spans >= 2 and coverage >= coverage_min
                  and verbatim_run >= DEFAULT_CORROBORATE_SPAN_VERBATIM)
    return (structural or verbatim_run >= verbatim_min
            or confidence >= confidence_min)


@dataclass
class SpanMatch:
    span: int
    lines: list
    probability: float
    pair: PairScore
    alternatives: int = 0

    def as_dict(self) -> dict:
        return {'span': self.span, 'query_lines': list(self.lines),
                'probability': self.probability, 'alternatives': self.alternatives,
                'pair': self.pair.as_dict()}


@dataclass
class Finding:
    package: str
    version: str
    path: str
    license_spdx: str
    license_origin: str
    confidence: float
    coverage: float
    spans: list
    max_verbatim_run: int
    matched_query_lines: list
    verdict: object = None
    risk: str = "S0"
    target: str = ""
    target_license: str = ""
    corroborated: bool = True

    @property
    def key(self) -> str:
        return "%s@%s:%s" % (self.package, self.version, self.path)

    def as_dict(self) -> dict:
        return {"package": self.package, "version": self.version, "path": self.path,
                "license_spdx": self.license_spdx, "license_origin": self.license_origin,
                "confidence": round(self.confidence, 4),
                "coverage": round(self.coverage, 4),
                "matched_spans": len(self.spans),
                "max_verbatim_run": self.max_verbatim_run,
                "corroborated": self.corroborated,
                "query_lines": self.matched_query_lines,
                "target": self.target, "target_license": self.target_license,
                "risk": self.risk, "risk_label": RISK_LABELS[self.risk],
                "verdict": self.verdict.as_dict() if self.verdict else None,
                "evidence": [p.as_dict() for p in self.spans]}


@dataclass
class ScanResult:
    target: str
    target_license: str
    usage: str
    total_spans: int
    matched_spans: int
    findings: list
    scanned_at: float
    timings: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(f.risk in ("S3", "S4") for f in self.findings)

    def as_dict(self) -> dict:
        return {"schema": "codeguard.scan/v1", "target": self.target,
                "target_license": self.target_license, "usage": self.usage,
                "total_spans": self.total_spans, "matched_spans": self.matched_spans,
                "scanned_at": self.scanned_at, "timings": self.timings,
                "notes": self.notes,
                "findings": [f.as_dict() for f in self.findings]}


class Scanner:
    def __init__(self, index, model=None, threshold: float = 0.5,
                 min_span_prob: float = DEFAULT_MIN_SPAN_PROB,
                 top_verify: int = DEFAULT_TOP_VERIFY,
                 usage: str = "inline_copy", exclude_same_package: bool = True,
                 use_idf: bool = True, corroborate_coverage: float = 0.15,
                 corroborate_verbatim: int = 20,
                 corroborate_confidence: float = DEFAULT_CORROBORATE_CONFIDENCE):
        self.index = index
        self.reader = CandidateReader(index)
        self.model = model
        self.threshold = threshold
        self.min_span_prob = min_span_prob
        self.top_verify = top_verify
        self.usage = usage
        self.exclude_same_package = exclude_same_package
        self.use_idf = use_idf
        self.corroborate_coverage = corroborate_coverage
        self.corroborate_verbatim = corroborate_verbatim
        self.corroborate_confidence = corroborate_confidence

    # ------------------------------------------------------------------ scoring

    def probability(self, feats: dict) -> float:
        if self.model is None:
            # rule fallback keeps the tool usable before a benchmark is trained
            s = (0.45 * feats["wc"] + 0.25 * feats["max_sim"]
                 + 0.2 * min(1.0, feats["verbatim_run"] / 40.0)
                 + 0.1 * feats["band_hits_norm"])
            return round(s, 4)
        row = [feats[name] for name in self.model.feature_names]
        return round(self.model.score_row(row), 4)

    def verify_span(self, ord_no, span, fp, hits, self_package: str):
        ranked = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))
        best: PairScore | None = None
        best_prob = 0.0
        considered = 0
        for chunk_index, band_hits in ranked:
            chunk = self.index.chunk(chunk_index)
            doc = self.index.doc_for(chunk.doc_id)
            if self.exclude_same_package and doc.package == self_package:
                continue
            if considered >= self.top_verify and best is not None:
                break
            pair = score_pair(self.index, self.reader, ord_no, span, fp, chunk,
                              band_hits, self.use_idf)
            prob = self.probability(pair.features)
            considered += 1
            if prob > best_prob:
                best, best_prob = pair, prob
            if best_prob > 0.95 and considered >= self.top_verify:
                break
        if best is None or best_prob < self.min_span_prob:
            return None, considered
        best.features = dict(best.features)
        best.features["probability"] = best_prob
        return SpanMatch(ord_no, [span.start_line, span.end_line], best_prob,
                         best, considered), considered

    # --------------------------------------------------------------------- scan

    def scan_text(self, text: str, target: str = "<memory>",
                  target_license: str = "MIT", package_hint: str = "",
                  language: str = "python") -> ScanResult:
        t0 = time.time()
        probe = self.index.probe(text, language=language, min_band_hits=1)
        t1 = time.time()
        per_span = []
        considered = 0
        for ord_no, span, fp, hits in probe:
            if not hits:
                continue
            match, n = self.verify_span(ord_no, span, fp, hits, package_hint)
            considered += n
            if match:
                per_span.append(match)
        t2 = time.time()

        buckets = {}
        for match in per_span:
            doc = self.index.doc_for(match.pair.doc_id)
            buckets.setdefault(doc.package + "|" + doc.path, []).append(match)

        findings = []
        downgraded = 0
        for _, matches in buckets.items():
            doc = self.index.doc_for(matches[0].pair.doc_id)
            coverage = len(matches) / max(1, len(probe))
            peak = max(m.probability for m in matches)
            confidence = round(min(1.0, 0.65 * peak + 0.35 * min(1.0, coverage * 3)), 4)
            verbatim = max(m.pair.verbatim_run for m in matches)
            verdict = analyze(doc.license_spdx, target_license, self.usage)
            # A licence conflict proven by one isolated span is not a build
            # break: real reuse leaves either several spans across the file or a
            # long verbatim run. Without this test the gate blocks on structural
            # coincidence - measured at 3.5% of unrelated corpus files.
            corroborated = corroborates(len(matches), coverage, verbatim,
                                        confidence, self.corroborate_coverage,
                                        self.corroborate_verbatim,
                                        self.corroborate_confidence)
            risk = risk_level(verdict.status, confidence, self.usage)
            if risk in ("S3", "S4") and not corroborated:
                risk = "S2"
                downgraded += 1
            findings.append(Finding(
                doc.package, doc.version, doc.path, doc.license_spdx,
                doc.license_source, confidence, coverage, matches, verbatim,
                [min(m.lines[0] for m in matches),
                 max(m.lines[1] for m in matches)],
                verdict, risk, target, target_license, corroborated))
        findings.sort(key=lambda f: (-f.confidence, f.key))
        notes = ["本结论为工程风险提示，不构成法律意见。"]
        if downgraded:
            notes.append("有 %d 处许可证冲突的证据未达阻断门槛（覆盖率 <%.2f、逐字命中 <%d token、"
                         "整体置信度 <%.2f），已降级为 S2 提示而不阻断；请人工复核证据链。"
                         % (downgraded, self.corroborate_coverage,
                            self.corroborate_verbatim, self.corroborate_confidence))
        return ScanResult(target, target_license, self.usage, len(probe),
                          len(per_span), findings, t2,
                          {"probe_ms": int((t1 - t0) * 1000),
                           "verify_ms": int((t2 - t1) * 1000),
                           "pairs_verified": considered},
                          notes)

    def scan_file(self, path: str, target_license: str = "MIT",
                  usage: str = "") -> ScanResult:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if usage:
            self.usage = usage
        lang = language_for(path)
        return self.scan_text(text, target=path.replace(os.sep, "/"),
                              target_license=target_license,
                              package_hint=os.path.basename(path),
                              language=lang)


def language_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".py": "python", ".pyw": "python"}.get(ext, "generic")


def iter_sources(root: str, extensions=(".py",)):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", ".codeguard", "__pycache__",
                                    "node_modules", "build", "dist", ".venv", "venv")]
        for name in filenames:
            if name.endswith(extensions):
                yield os.path.join(dirpath, name)
