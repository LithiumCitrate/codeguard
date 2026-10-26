"""Machine-readable outputs: provenance receipt, CycloneDX SBOM, offline HTML.

Emitting CycloneDX (an OWASP open standard) is deliberate: it lets an existing
SBOM pipeline consume CodeGuard results instead of a bespoke format, and it shows
the licence evidence as component occurrences with line ranges.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import time
import uuid
from urllib.parse import quote

from . import __version__
from .license_intel import RISK_LABELS

TOOL_NAME = "codeguard"
TOOL_VERSION = __version__
SPEC_VERSION = "1.6"


def _utc_stamp(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts or time.time()))


def index_fingerprint(index) -> str:
    """Stable identity of the knowledge base the verdict was produced against."""
    st = index.stats()
    blob = json.dumps({"docs": [(d.package, d.version, d.path, d.license_spdx, d.sha256)
                                 for d in sorted(index.docs, key=lambda d: d.doc_id)],
                       "stats": {k: v for k, v in st.items() if k != "built_at"}},
                      sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def file_digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance_receipt(scan, index, explanations: dict | None = None) -> dict:
    findings = []
    for f in scan.findings:
        evidence = []
        for m in f.spans:
            evidence.append({
                "query_lines": list(m.lines),
                "source_lines": [m.pair.line_start, m.pair.line_end],
                "probability": m.probability,
                "verbatim_token_run": m.pair.verbatim_run,
                "weighted_containment": round(m.pair.weighted_containment, 4),
                "exact_layer_jaccard": m.pair.exact,
                "lsh_band_hits": m.pair.band_hits,
                "features": m.pair.features})
        findings.append({
            "source": {"package": f.package, "version": f.version, "path": f.path,
                       "license_spdx": f.license_spdx,
                       "license_resolved_from": f.license_origin},
            "confidence": f.confidence, "span_coverage": f.coverage,
            "risk": f.risk, "risk_label": RISK_LABELS[f.risk],
            "verdict": f.verdict.as_dict(),
            "explanation": (explanations or {}).get(f.key, ""),
            "evidence": evidence})
    return {
        "schema": "codeguard.provenance/v1",
        "metadata": {"tool": TOOL_NAME, "version": TOOL_VERSION,
                     "generated_at": _utc_stamp(scan.scanned_at),
                     "index_fingerprint": index_fingerprint(index),
                     "corpus_root": index.corpus_root.replace(os.sep, "/"),
                     "ai_usage": _ai_usage()},
        "subject": {"target": scan.target.replace(os.sep, "/"),
                    "target_license": scan.target_license,
                    "usage_mode": scan.usage,
                    "total_spans": scan.total_spans,
                    "matched_spans": scan.matched_spans},
        "findings": findings,
        "timings": scan.timings,
        "notes": scan.notes,
        "disclaimer": "工程性风险提示，不构成法律意见。",
    }


def _ai_usage() -> dict:
    from .llm import DISCLOSURE, OpenAICompatProvider
    llm = OpenAICompatProvider.from_env()
    return {"provider": llm.name if llm else "offline-template",
            "external_calls": bool(llm),
            "model": llm.model if llm else "",
            "statement": DISCLOSURE}


def to_cyclonedx(scan, index) -> dict:
    components = {}
    from .license_intel import load_spdx
    known = set(load_spdx())
    def licenses(expression):
        if expression in known:
            return [{'license': {'id': expression}}]
        if (' AND ' in expression or ' OR ' in expression) and 'LicenseRef' not in expression:
            return [{'expression': expression}]
        return [{'license': {'name': expression}}]
    for f in scan.findings:
        cid = "pkg:pypi/%s@%s" % (quote(f.package, safe=''), quote(f.version, safe=''))
        # One component per package/version/license; evidence from multiple files
        # belongs to that component rather than producing duplicate bom-refs.
        ref = cid + '#' + hashlib.sha256(f.license_spdx.encode()).hexdigest()[:12]
        if ref not in components:
            components[ref] = {
            "bom-ref": ref, "type": "library", "name": f.package,
            "version": f.version, "purl": cid,
            "licenses": licenses(f.license_spdx),
            "evidence": {
                "occurrences": [],
                "identity": [{"field": "purl", "confidence": f.confidence,
                              "methods": [{"technique": "source-code-analysis",
                                           "confidence": f.confidence}]}]},
            "properties": []}
        component = components[ref]
        component['evidence']['occurrences'].extend([
            {'location': scan.target, 'line': m.lines[0],
             'additionalContext': 'query lines %d-%d; source %s:%d-%d' %
                                  (*m.lines, f.path, m.pair.line_start, m.pair.line_end)}
            for m in f.spans])
        component['evidence']['identity'][0]['confidence'] = max(
            component['evidence']['identity'][0]['confidence'], f.confidence)
        component['properties'].extend([{"name": "codeguard:risk", "value": f.risk},
                           {"name": "codeguard:verbatim-token-run",
                            "value": str(f.max_verbatim_run)},
                           {"name": "codeguard:verdict", "value": f.verdict.status}])
    return {"bomFormat": "CycloneDX", "specVersion": SPEC_VERSION,
            "serialNumber": "urn:uuid:" + str(uuid.uuid4()),
            "version": 1,
            "metadata": {"timestamp": _utc_stamp(scan.scanned_at),
                         "tools": [{"vendor": TOOL_NAME, "name": TOOL_NAME,
                                    "version": TOOL_VERSION}],
                         "component": {"type": "application",
                                       "bom-ref": "file:" + scan.target,
                                       "name": os.path.basename(scan.target),
                                       "licenses": licenses(scan.target_license)}},
            "components": list(components.values()),
            "dependencies": [{"ref": "file:" + scan.target,
                              "dependsOn": sorted(components)}]}


CSS = """
:root{--bg:#0f1115;--card:#171a21;--fg:#e6e9ef;--mut:#9aa4b2;--ok:#3fb950;
--warn:#d29922;--bad:#f85149;--line:#232833}
*{box-sizing:border-box}body{margin:0;padding:32px;background:var(--bg);
color:var(--fg);font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;color:var(--mut)}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;
font-weight:600;border:1px solid var(--line)}
.S0,.S1{color:var(--ok)}.S2{color:var(--warn)}.S3,.S4{color:var(--bad)}
.incompatible{color:var(--bad)}.conditional,.unknown{color:var(--warn)}
.compatible{color:var(--ok)}
code{background:#20242d;padding:1px 5px;border-radius:4px;font-size:12.5px}
.bar{height:6px;background:#20242d;border-radius:3px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--ok)}
footer{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--line);
padding-top:12px}
"""

_LAYER_LABEL = {"role": "角色层 L3", "abs": "抽象层 L2", "edge": "结构边层 L4",
                "lit": "字面层 L1"}


def to_html(receipt: dict) -> str:
    subject = receipt["subject"]
    rows = []
    for f in receipt["findings"]:
        src = f["source"]
        ev = f["evidence"][0] if f["evidence"] else {}
        feats = " · ".join("%s=%.2f" % (k, v) for k, v in
                           sorted(ev.get("exact_layer_jaccard", {}).items()))
        rows.append(
            "<tr><td><code>%s@%s</code><br><span class=sub>%s</span></td>"
            "<td><b>%s</b><br><span class=sub>%s</span></td>"
            "<td><span class='badge %s'>%s</span></td>"
            "<td><span class='%s'>%s</span></td>"
            "<td>%.3f<div class=bar><i style='width:%.0f%%'></i></div></td>"
            "<td>%d</td><td><code>%s</code></td></tr>" % (
                html.escape(src["package"]), html.escape(src["version"]),
                html.escape(src["path"]),
                html.escape(src["license_spdx"]),
                html.escape("解析来源: " + src["license_resolved_from"]),
                f["risk"], f["risk"],
                f["verdict"]["status"], f["verdict"]["status"],
                f["confidence"], f["confidence"] * 100,
                ev.get("verbatim_token_run", 0), html.escape(feats)))
    evidence_block = ""
    for f in receipt["findings"]:
        lines = ["<div class=card><h2>%s ← %s@%s</h2>" % (
            html.escape(f["explanation"].split("\n")[0]),
            html.escape(f["source"]["package"]), html.escape(f["source"]["version"]))]
        for e in f["evidence"][:8]:
            lines.append(
                "<table><tr><th>目标片段</th><th>来源行</th><th>判定概率</th>"
                "<th>逐字连续命中</th><th>加权覆盖率</th><th>LSH 命中带</th></tr>"
                "<tr><td>第 %d-%d 行</td><td>%s</td><td>%.3f</td><td>%d token</td>"
                "<td>%.3f</td><td>%d/30</td></tr></table>" % (
                    e["query_lines"][0], e["query_lines"][1],
                    html.escape("%s:%d-%d" % (f["source"]["path"],
                            e["source_lines"][0], e["source_lines"][1])),
                    e["probability"],
                    e["verbatim_token_run"], e["weighted_containment"],
                    e["lsh_band_hits"]))
        lines.append("</div>")
        evidence_block += "\n".join(lines)
    obligations = []
    for f in receipt["findings"]:
        for o in f["verdict"]["obligations"]:
            obligations.append("<li><b>%s</b>（%s）：%s</li>" % (
                html.escape(f["source"]["package"]),
                html.escape(f["source"]["license_spdx"]), html.escape(o)))
        for c in f["verdict"]["conflicts"]:
            obligations.append("<li><b>冲突</b> %s：%s</li>" % (
                html.escape(f["source"]["package"]), html.escape(c)))
    ai = receipt["metadata"]["ai_usage"]
    return """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>CodeGuard 合规报告 · %s</title><style>%s</style></head><body>
<h1>CodeGuard 开源许可证污染溯源报告</h1>
<div class=sub>目标 <code>%s</code> ｜ 项目许可证 <code>%s</code> ｜ 使用方式 <code>%s</code>
｜ 片段 %d/%d ｜ 索引指纹 <code>%s</code> ｜ 生成于 %s</div>
<div class=card>%s</div>
<h2>命中来源</h2>
<table><tr><th>语料来源</th><th>许可证</th><th>风险</th><th>合规结论</th>
<th>置信度</th><th>逐字命中</th><th>各层精确相似度</th></tr>%s</table>
<h2>逐片段证据链</h2>%s
<h2>需要履行的义务 / 冲突条款</h2><ul>%s</ul>
<h2>AI 使用声明</h2><div class=card><b>%s</b>（外部调用：%s）<br>%s</div>
<footer>%s<br>%s<br>由 %s v%s 生成，报告与 HTML 不含任何外部资源引用，可离线打开。</footer>
</body></html>""" % (html.escape(os.path.basename(subject["target"])), CSS,
                     html.escape(subject["target"]), html.escape(subject["target_license"]),
                     html.escape(subject["usage_mode"]), subject["matched_spans"],
                     subject["total_spans"], receipt["metadata"]["index_fingerprint"],
                     receipt["metadata"]["generated_at"],
                     "<b>结论：</b>共 %d 条来源命中，其中 %d 条为阻断级风险（S3/S4）。" % (
                         len(receipt["findings"]),
                         sum(1 for f in receipt["findings"] if f["risk"] in ("S3", "S4"))),
                     "\n".join(rows) or "<tr><td colspan=7>未检出来自语料库的复用</td></tr>",
                     evidence_block, "\n".join(obligations) or "<li>无</li>",
                     html.escape(ai["provider"]), ai["external_calls"],
                     html.escape(ai["statement"]),
                     html.escape("；".join(receipt["notes"])),
                     receipt["disclaimer"], TOOL_NAME, TOOL_VERSION)


SARIF_RULES = [
    {"id": "CG001", "name": "BlockingLicenseConflict",
     "shortDescription": {"text": "阻断级许可证冲突（S4）"},
     "fullDescription": {"text": "来源代码使用方式与目标项目许可证不兼容，且证据达到阻断门槛。"},
     "defaultConfiguration": {"level": "error"},
     "properties": {"tags": ["license", "compliance", "open-source"]}},
    {"id": "CG002", "name": "ConditionalLicenseConflict",
     "shortDescription": {"text": "需履行条件的许可证冲突（S3）"},
     "fullDescription": {"text": "来源许可证要求附加义务或升级目标许可证，需人工复核后放行。"},
     "defaultConfiguration": {"level": "error"},
     "properties": {"tags": ["license", "compliance", "open-source"]}},
    {"id": "CG003", "name": "LicenseReviewRequired",
     "shortDescription": {"text": "许可证复核项（S2）"},
     "fullDescription": {"text": "存在相似来源或义务冲突，但证据未达到阻断门槛，应人工复核。"},
     "defaultConfiguration": {"level": "warning"},
     "properties": {"tags": ["license", "review", "open-source"]}},
    {"id": "CG004", "name": "ProvenanceObservation",
     "shortDescription": {"text": "来源观察（S0/S1）"},
     "fullDescription": {"text": "检出来源候选，但当前使用方式不构成阻断级义务冲突。"},
     "defaultConfiguration": {"level": "note"},
     "properties": {"tags": ["license", "provenance", "open-source"]}},
]
SARIF_RULE_INDEX = {"S4": 0, "S3": 1, "S2": 2, "S1": 3, "S0": 3}
SARIF_LEVEL = {"S4": "error", "S3": "error", "S2": "warning",
               "S1": "note", "S0": "note"}


def to_sarif(scan, index) -> dict:
    """SARIF 2.1.0 for GitHub Code Scanning / SARIF viewers.

    One result per finding. The primary location is the queried file and line
    range; the matched upstream file is attached as a related location so a
    reviewer can jump to both sides of the evidence.
    """
    target = scan.target.replace(os.sep, "/")
    results = []
    for finding in scan.findings:
        rule_index = SARIF_RULE_INDEX.get(finding.risk, 3)
        start_line = max(1, int(finding.matched_query_lines[0]))
        end_line = max(start_line, int(finding.matched_query_lines[1]))
        fingerprint = hashlib.sha256(
            ("%s|%s|%s|%s|%s|%d|%d" % (
                target, finding.package, finding.version, finding.path,
                finding.license_spdx, start_line, end_line)).encode("utf-8")
        ).hexdigest()[:16]
        message = ("%s %s：%s@%s:%s（%s），置信度 %.2f，覆盖率 %.2f，"
                   "判定 %s。来源候选需人工复核，不构成法律意见。" % (
                       finding.risk, RISK_LABELS[finding.risk], finding.package,
                       finding.version, finding.path, finding.license_spdx,
                       finding.confidence, finding.coverage,
                       finding.verdict.status if finding.verdict else "unknown"))
        result = {
            "ruleId": SARIF_RULES[rule_index]["id"],
            "ruleIndex": rule_index,
            "level": SARIF_LEVEL.get(finding.risk, "note"),
            "message": {"text": message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": target},
                    "region": {"startLine": start_line, "endLine": end_line},
                }
            }],
            "partialFingerprints": {
                "codeguard/v1": fingerprint,
                "primaryLocationLineHash": fingerprint,
            },
            "properties": {
                "risk": finding.risk,
                "riskLabel": RISK_LABELS[finding.risk],
                "license": finding.license_spdx,
                "package": finding.package,
                "version": finding.version,
                "sourcePath": finding.path,
                "confidence": round(finding.confidence, 4),
                "coverage": round(finding.coverage, 4),
                "verbatimTokenRun": finding.max_verbatim_run,
                "verdict": finding.verdict.status if finding.verdict else "unknown",
                "corroborated": finding.corroborated,
            },
            "relatedLocations": [{
                "id": 1,
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.path},
                    "region": {
                        "startLine": max(1, int(finding.spans[0].pair.line_start))
                        if finding.spans else 1,
                        "endLine": max(1, int(finding.spans[0].pair.line_end))
                        if finding.spans else 1,
                    },
                },
                "message": {"text": "命中的上游来源文件"}
            }],
        }
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "CodeGuard",
                "version": TOOL_VERSION,
                "informationUri": "https://www.aicomp.cn/tracks/tracks-5/4924.html",
                "rules": SARIF_RULES,
            }},
            "columnKind": "utf16CodeUnits",
            "results": results,
            "properties": {
                "target": target,
                "targetLicense": scan.target_license,
                "usage": scan.usage,
                "indexFingerprint": index_fingerprint(index),
                "disclaimer": "工程性风险提示，不构成法律意见。",
            },
        }],
    }


def write_outputs(scan, index, out_dir: str, explanations: dict | None = None,
                  formats=("json", "cdx", "html")) -> list:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(scan.target.replace(os.sep, "/")))[0] \
        or "snippet"
    receipt = provenance_receipt(scan, index, explanations)
    written = []
    if "json" in formats:
        p = os.path.join(out_dir, base + ".provenance.json")
        _dump(p, receipt)
        written.append(p)
    if "cdx" in formats:
        p = os.path.join(out_dir, base + ".cdx.json")
        _dump(p, to_cyclonedx(scan, index))
        written.append(p)
    if "html" in formats:
        p = os.path.join(out_dir, base + ".report.html")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(to_html(receipt))
        written.append(p)
    if "sarif" in formats:
        p = os.path.join(out_dir, base + ".sarif")
        _dump(p, to_sarif(scan, index))
        written.append(p)
    return written


def merge_sarif(docs: list) -> dict:
    """Fold per-file SARIF documents into a single run.

    ``scan`` writes one report per source file, but GitHub Code Scanning rejects
    several runs sharing one category, so the directory has to be collapsed
    before upload.  Rule tables are merged by id and every ``ruleIndex`` is
    remapped, which keeps the result correct even if an input came from a
    different rule set; conflicting definitions are refused rather than guessed
    at.
    """
    if not docs:
        raise ValueError("没有可合并的 SARIF 文档")
    rules, order = {}, []
    results, seen = [], set()
    targets = []
    shared = {}
    base_run = None
    base_schema = None
    for doc in docs:
        if doc.get("version") != "2.1.0":
            raise ValueError("只支持 SARIF 2.1.0，实际为 %r" % doc.get("version"))
        runs = doc.get("runs") or []
        if len(runs) != 1:
            raise ValueError("每个输入文档必须只含一个 run，实际 %d 个" % len(runs))
        run = runs[0]
        if base_run is None:
            base_run, base_schema = run, doc.get("$schema")
        driver = (run.get("tool") or {}).get("driver") or {}
        for rule in driver.get("rules") or []:
            rid = rule.get("id")
            if not rid:
                raise ValueError("规则缺少 id")
            if rid in rules and rules[rid] != rule:
                raise ValueError("规则 %s 在输入文档之间定义不一致" % rid)
            if rid not in rules:
                rules[rid] = rule
                order.append(rid)
        props = run.get("properties") or {}
        if props.get("target"):
            targets.append(props["target"])
        for key in ("targetLicense", "usage", "indexFingerprint", "disclaimer"):
            if key in props and shared.setdefault(key, props[key]) != props[key]:
                raise ValueError("字段 %s 在输入文档之间不一致" % key)
        source_ids = [r.get("id") for r in driver.get("rules") or []]
        for result in run.get("results") or []:
            result = json.loads(json.dumps(result, ensure_ascii=False))
            rid = result.get("ruleId")
            if rid is None and result.get("ruleIndex") is not None:
                index = result["ruleIndex"]
                if index < len(source_ids):
                    rid = source_ids[index]
            if rid in rules:
                result["ruleId"] = rid
                result["ruleIndex"] = order.index(rid)
            key = json.dumps([rid, result.get("locations"),
                              result.get("partialFingerprints")], sort_keys=True,
                             ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            results.append(result)

    driver = json.loads(json.dumps((base_run.get("tool") or {}).get("driver") or {},
                                   ensure_ascii=False))
    driver["rules"] = [rules[rid] for rid in order]
    properties = json.loads(json.dumps(base_run.get("properties") or {}, ensure_ascii=False))
    properties.pop("target", None)
    properties["scannedTargets"] = sorted(set(targets))
    properties["mergedDocuments"] = len(docs)
    results.sort(key=lambda r: (
        ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
        .get("artifactLocation", {}).get("uri", ""),
        ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
        .get("region", {}).get("startLine", 0),
        r.get("ruleId") or ""))
    return {
        "$schema": base_schema or "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": driver},
            "columnKind": base_run.get("columnKind", "utf16CodeUnits"),
            "results": results,
            "properties": properties,
        }],
    }


def _dump(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
