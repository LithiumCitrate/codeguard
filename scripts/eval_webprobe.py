"""Reproducible marginal-benefit benchmark for the web provenance channel.

Answers the question the controlled mutation benchmark cannot: does the AI
web-provenance channel detect copying that the *offline* engine provably cannot
see (sources outside the shipped corpus)? For each real out-of-corpus GitHub
file it runs, per trial: offline scan (baseline) -> /webprobe -> offline scan
(after), hard-asserting that the offline verdict is untouched and that the web
channel never blocks / never exceeds S3 / always carries audit fields.

Detection is reported as a rate across trials because LLM candidate proposal is
non-deterministic; the safety invariants are guaranteed on every trial. Query
code is fetched from public raw GitHub at run time (nothing third-party is
committed). Requires CODEGUARD_LLM_* and CODEGUARD_TAVILY_API_KEY in the env.

Usage:
    python scripts/eval_webprobe.py --trials 3
    python scripts/eval_webprobe.py --trials 5 --only ranger itsdangerous
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codeguard import web_evidence  # noqa: E402
from codeguard.adjudicate import Scanner  # noqa: E402
from codeguard.cli import load_index, load_model, workspace  # noqa: E402
from codeguard.llm import extract_license_markers, provider_from_settings  # noqa: E402
from codeguard import __version__  # noqa: E402

# Real projects deliberately OUTSIDE the shipped corpus. `upstream` is the
# substring the provenance URL must contain for a detection to count as correct.
CASES = [
    {"name": "ranger", "query": "https://raw.githubusercontent.com/ranger/ranger/master/ranger/ext/rifle.py",
     "file": "rifle.py", "upstream": "ranger", "license": "LicenseRef-Proprietary",
     "usage": "distribution", "permissive": False},
    {"name": "itsdangerous", "query": "https://raw.githubusercontent.com/pallets/itsdangerous/main/src/itsdangerous/serializer.py",
     "file": "serializer.py", "upstream": "itsdangerous", "license": "MIT",
     "usage": "distribution", "permissive": True},
    {"name": "toml", "query": "https://raw.githubusercontent.com/uiri/toml/master/toml/decoder.py",
     "file": "decoder.py", "upstream": "toml", "license": "MIT",
     "usage": "distribution", "permissive": True},
    {"name": "synapse", "query": "https://raw.githubusercontent.com/matrix-org/synapse/develop/synapse/util/stringutils.py",
     "file": "stringutils.py", "upstream": "synapse", "license": "LicenseRef-Proprietary",
     "usage": "distribution", "permissive": True},
    {"name": "aiohttp", "query": "https://raw.githubusercontent.com/aio-libs/aiohttp/master/aiohttp/helpers.py",
     "file": "helpers.py", "upstream": "aiohttp", "license": "LicenseRef-Proprietary",
     "usage": "distribution", "permissive": True},
    {"name": "markupsafe", "query": "https://raw.githubusercontent.com/pallets/markupsafe/main/src/markupsafe/__init__.py",
     "file": "markupsafe_init.py", "upstream": "markupsafe", "license": "MIT",
     "usage": "distribution", "permissive": True},
]


def offline_signature(scan):
    return {"blocking": scan.blocking,
            "findings": [{"key": f.package + ":" + f.path, "risk": f.risk,
                          "confidence": f.confidence} for f in scan.findings]}


def run_case(case, index, model, provider, trials):
    code = web_evidence.fetch_source(case["query"])["text"]
    markers = extract_license_markers(code)
    rows = []
    for _ in range(trials):
        before = Scanner(index, model=model, usage=case["usage"]).scan_text(
            code, target=case["file"], target_license=case["license"], language="python")
        t0 = time.time()
        probe = web_evidence.run_web_probe(index, model, provider, code, case["file"],
                                           markers, case["usage"], case["license"])
        elapsed = round(time.time() - t0, 1)
        after = Scanner(index, model=model, usage=case["usage"]).scan_text(
            code, target=case["file"], target_license=case["license"], language="python")

        # ---- safety invariants: guaranteed on every trial ----------------
        assert offline_signature(before) == offline_signature(after), "offline verdict mutated"
        assert probe["blocking"] is False, "web channel must never block"
        offline_hits_upstream = any(case["upstream"] in (f.package + f.path)
                                    for f in before.findings)
        for f in probe["findings"]:
            assert f["risk"] != "S4", "web findings must cap at S3"
            assert f["provenance"]["url"].startswith("https://")
            assert f["provenance"]["sha256"] and f["provenance"]["fetched_at"]
            assert case["upstream"] in f["provenance"]["url"], "wrong upstream"
            if case["permissive"]:
                assert f["risk"] in ("S0", "S1", "S2"), "permissive over-graded"
        top = probe["findings"][0] if probe["findings"] else None
        rows.append({"seconds": elapsed,
                     "offline_blocking": before.blocking,
                     "offline_hits_upstream": offline_hits_upstream,
                     "detected": bool(top),
                     "risk": top["risk"] if top else None,
                     "confidence": top["confidence"] if top else None,
                     "verbatim": top["max_verbatim_run"] if top else None,
                     "license": top["license_spdx"] if top else None,
                     "license_source": top["provenance"]["license_source"] if top else None,
                     "url": top["provenance"]["url"] if top else None,
                     "probe_error": probe.get("error"),
                     "search_errors": sum(1 for s in probe["searches"] if s.get("error")),
                     "fetch_errors": [f["error"] for f in probe["fetched"] if f.get("error")]})
    detected = sum(1 for r in rows if r["detected"])
    verified = sum(1 for r in rows if r["license_source"] == "web:license-text-verified")
    return {"name": case["name"], "query": case["query"], "upstream": case["upstream"],
            "license": case["license"], "permissive": case["permissive"],
            "source_sha256": hashlib.sha256(code.encode()).hexdigest(),
            "trials": rows, "detection_rate": "%d/%d" % (detected, trials),
            "offline_detection_rate": "%d/%d" % (
                sum(1 for r in rows if r["offline_hits_upstream"]), trials),
            "license_verified_rate": "%d/%d" % (verified, trials)}


def to_markdown(payload):
    s = payload["summary"]
    lines = ["# 联网溯源边际收益评测（AI 必要性证据）", "",
             "- 生成时间：%s；每例试验数：%d；安全不变量：%s" % (
                 payload["generated_at"], s["trials_per_case"], s["safety_invariants"]),
             "- 问题：离线引擎只能 attest 已 shipped 语料；本评测度量联网通道对**语料外**复制的边际检出。",
             "",
             "| 项目（语料外） | 许可证 | 离线检出上游 | 联网检出 | 许可证文本核验 | 最高风险 | 置信度 |",
             "|---|---|---|---|---|---|---|"]
    for c in payload["cases"]:
        if c.get("query_error"):
            lines.append("| %s | %s | — | 跳过（查询拉取失败） | — | — | — |" % (
                c["name"], c["license"]))
            continue
        tops = [r for r in c["trials"] if r["detected"]]
        risk = tops[0]["risk"] if tops else "—"
        conf = ("%.3f" % tops[0]["confidence"]) if tops else "—"
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            c["name"], c["license"], c["offline_detection_rate"], c["detection_rate"],
            c["license_verified_rate"], risk, conf))
    lines += ["", "## 解读", "",
              "- 离线检出上游为 0 而联网检出 >0 的行，即 AI 通道带来的**边际收益**：这些来源不在本地语料内，"
              "规则/指纹原理上无法检出，联网溯源把它们纳入同一套确定性验证。",
              "- 联网命中仅作补充提示（封顶 S3、不阻断）；许可证优先用上游 LICENSE 文本确定性核验"
              "（web:license-text-verified），失败回退模型推断（web:llm-inferred）。",
              "", "## 局限（如实披露）", "",
              "- 候选上游由大模型推断，召回受提案质量与网络可用性影响，故以多次试验的比率报告，不承诺单次必中。",
              "- 拉取仅限公开 https raw 白名单、限额限时、防跳转；任何拉取原文仍须通过精确验证才成为发现，不引入误报。",
              "- 本通道不修改语料、索引与离线结论；每次试验前后离线判定逐字节一致。",
              ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=".codeguard")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    parser.add_argument("--date", default="")
    args = parser.parse_args(argv)
    root = workspace(args.workspace)
    provider = provider_from_settings(root)
    if provider is None or not provider.tavily_api_key:
        raise SystemExit("需要 CODEGUARD_LLM_BASE_URL/API_KEY/MODEL 或 .codeguard/llm_config.json 与 Tavily API Key")
    index = load_index(root)
    model = load_model(root)
    cases = [c for c in CASES if not args.only or c["name"] in args.only]
    results = []
    for case in cases:
        print("== %s (%d trials)" % (case["name"], args.trials), flush=True)
        try:
            entry = run_case(case, index, model, provider, args.trials)
        except ValueError as exc:
            # A single network failure fetching the query code must not kill the
            # run; record the case as skipped and continue (mirrors eval_realworld).
            entry = {"name": case["name"], "query": case["query"],
                     "upstream": case["upstream"], "license": case["license"],
                     "permissive": case["permissive"], "source_sha256": "",
                     "trials": [], "detection_rate": "0/0",
                     "offline_detection_rate": "0/0", "license_verified_rate": "0/0",
                     "query_error": str(exc)}
            print("   QUERY FETCH FAILED (skipped): %s" % exc, flush=True)
        results.append(entry)
        print("   offline=%s web=%s license-verified=%s" % (
            entry["offline_detection_rate"], entry["detection_rate"],
            entry["license_verified_rate"]), flush=True)
    total_trials = sum(len(c["trials"]) for c in results)
    payload = {
        "schema": "codeguard.webprobe-eval/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metadata": {"tool": "codeguard", "version": __version__,
                     "model": provider.model},
        "summary": {"trials_per_case": args.trials,
                    "safety_invariants": "held on all %d trials" % total_trials},
        "cases": results,
    }
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / ("webprobe-eval-%s.json" % date)).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / ("webprobe-eval-%s.md" % date)).write_text(to_markdown(payload), encoding="utf-8")
    print("evidence written to", out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())