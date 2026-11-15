"""Offline, reproducible evaluation of the llmFusion LICENSE-text grounding channel.

WHY THIS EXISTS
---------------
The 2026-11-15 webprobe / round2 evidence records license_verified_rate 0/2:
every successful finding was labelled ``web:llm-inferred`` even though the
upstream LICENSE files (ranger/LICENSE, itsdangerous/LICENSE.txt) exist and are
recognisable. The old ``ground_license`` returned ``{}`` on any failure, so the
evidence could not distinguish "channel not implemented" from "three extra
network fetches timed out". It also refetched the same LICENSE once per finding
and never tried ``COPYING``.

This script proves, with fixed offline inputs and no API key, that:

  1. ``classify_license_text`` maps the common upstream licence texts to the
     right SPDX id (including the GPL-3.0 §13 / AGPL false-positive trap);
  2. ``ground_license`` succeeds on LICENSE, succeeds on COPYING after the
     LICENSE names 404, and reports an auditable reason + per-URL attempts
     when every fetch fails;
  3. ``run_web_probe`` really produces ``web:license-text-verified`` end to end,
     still caps web findings at S3, never blocks, and leaves the offline index
     untouched; and on grounding failure it now records *why*.

HONESTY BOUNDARY
----------------
``mode`` is ``offline-fixture``. Upstream files are simulated by an injected
``fetch_source``. This validates the channel's logic and reproducibility; it
does NOT claim any real-network verification rate. A real-network
``web:license-text-verified`` rate still has to be measured with
``scripts/eval_webprobe.py`` on a stable connection. Do not merge the two.

Usage:
    python scripts/eval_license_grounding.py
    python scripts/eval_license_grounding.py --out-dir submission/evidence
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from codeguard import web_evidence  # noqa: E402
from helpers import build_index, make_corpus, read_negative  # noqa: E402

RAW = "https://raw.githubusercontent.com/fixture/proj/main/victim.py"
ROOT_URL = "https://raw.githubusercontent.com/fixture/proj/main/"


class FixtureProvider:
    """Deterministic stand-in for the LLM + Tavily proposal step."""

    model = "offline-fixture-provider"

    def __init__(self, spdx="UNKNOWN"):
        self.spdx = spdx

    def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
        assert "严禁逐字包含" in prompt, "search-query guard must stay in the prompt"
        reply = ('```json\n{"candidates": [{"url": "%s", "package": "fixtureproj", '
                 '"version": "1.0", "license_spdx": "%s", "reason": "offline fixture"}]}\n```'
                 % (RAW, self.spdx))
        return reply, [{"query": "fixtureproj license", "results": []}]


GPL3 = ("                    GNU GENERAL PUBLIC LICENSE\n"
        "                       Version 3, 29 June 2007\n"
        "  13. Use with the GNU Affero General Public License.\n")
AGPL3 = ("                    GNU AFFERO GENERAL PUBLIC LICENSE\n"
         "                       Version 3, 19 November 2007\n")
LGPL21 = ("                  GNU LESSER GENERAL PUBLIC LICENSE\n"
          "                       Version 2.1, February 1999\n")
GPL2 = ("                    GNU GENERAL PUBLIC LICENSE\n"
        "                        Version 2, June 1991\n")
APACHE2 = ("                                 Apache License\n"
           "                           Version 2.0, January 2004\n")
MPL2 = "Mozilla Public License Version 2.0\n==================================\n"
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person\n"
BSD3 = ("Redistribution and use in source and binary forms, with or without\n"
        "modification, are permitted provided that the following conditions are met:\n"
        "...\nNeither the name of the copyright holder nor the names of its\n"
        "contributors may be used to endorse or promote products derived from\n")
BSD2 = ("Redistribution and use in source and binary forms, with or without\n"
        "modification, are permitted provided that the following conditions are met:\n")
UNLICENSE = "This is free and unencumbered software released into the public domain.\n"
UNKNOWN = "Some bespoke proprietary terms and conditions apply.\n"

CLASSIFIER_CASES = [
    ("GPL-3.0 全文含 §13 提及 Affero（不得误判 AGPL）", GPL3, "GPL-3.0-only"),
    ("AGPL-3.0", AGPL3, "AGPL-3.0-only"),
    ("LGPL-2.1", LGPL21, "LGPL-2.1"),
    ("GPL-2.0", GPL2, "GPL-2.0-only"),
    ("Apache-2.0", APACHE2, "Apache-2.0"),
    ("MPL-2.0", MPL2, "MPL-2.0"),
    ("MIT", MIT, "MIT"),
    ("BSD-3-Clause（应优先于 BSD-2）", BSD3, "BSD-3-Clause"),
    ("BSD-2-Clause", BSD2, "BSD-2-Clause"),
    ("Unlicense", UNLICENSE, "Unlicense"),
    ("专有条款（应识别不出，返回空）", UNKNOWN, ""),
]


def _payload(text):
    raw = text.encode()
    return {"url": "", "text": text, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "fetched_at": 1760000000}


def make_fetch(source_text, licence_url=None, licence_text=None, fail_licences=False):
    """Injected fetch_source: source URL succeeds, licence URLs are scripted."""
    calls = []

    def fetch(url, timeout=web_evidence.FETCH_TIMEOUT):
        calls.append(url)
        if url == RAW:
            out = _payload(source_text)
            out["url"] = url
            return out
        if fail_licences:
            raise ValueError("拉取超时或网络错误：%s" % url)
        if licence_url and url == licence_url and licence_text is not None:
            out = _payload(licence_text)
            out["url"] = url
            return out
        raise ValueError("拉取失败：HTTP 404（%s）" % url)

    return fetch, calls


def run_classifier():
    rows = []
    for label, text, expected in CLASSIFIER_CASES:
        got = web_evidence.classify_license_text(text)
        rows.append({"case": label, "expected": expected or "(unrecognised)",
                     "actual": got or "(unrecognised)", "passed": got == expected})
    return {"cases": rows, "passed": sum(r["passed"] for r in rows),
            "total": len(rows)}


def run_grounding(original_fetch):
    cases = []

    def one(label, fetch, expect_spdx, expect_status, expect_reason=None):
        web_evidence.fetch_source = fetch
        try:
            out = web_evidence.ground_license(RAW)
        finally:
            web_evidence.fetch_source = original_fetch
        ok = (out["spdx"] == expect_spdx and out["status"] == expect_status
              and (expect_reason is None or out["reason"] == expect_reason)
              and isinstance(out.get("attempts"), list))
        cases.append({"case": label, "status": out["status"], "reason": out["reason"],
                      "spdx": out["spdx"], "url": out["url"],
                      "attempts": out["attempts"], "passed": ok})
        return out

    f1, _ = make_fetch("", ROOT_URL + "LICENSE", GPL3)
    one("LICENSE 存在且被识别 → verified", f1, "GPL-3.0-only", "verified")

    f2, _ = make_fetch("", ROOT_URL + "COPYING", GPL2)
    one("LICENSE* 全 404、仅 COPYING 存在 → verified（旧版会漏）",
        f2, "GPL-2.0-only", "verified")

    f3, calls = make_fetch("", fail_licences=True)
    one("全部拉取超时 → unavailable + 逐 URL 失败原因（旧版静默返回 {}）",
        f3, "", "unavailable", "all-candidates-unavailable")

    f4, _ = make_fetch("", ROOT_URL + "LICENSE", UNKNOWN)
    one("拉取成功但文本无法识别 → unavailable + 明确原因",
        f4, "", "unavailable", "no-recognised-license-text")

    # One probe shares a cache: a second finding from the same repository root
    # must not repeat the network requests.
    f5, calls5 = make_fetch("", ROOT_URL + "LICENSE", GPL3)
    web_evidence.fetch_source = f5
    try:
        cache = {}
        first = web_evidence.ground_license(RAW, _cache=cache)
        n_after_first = len(calls5)
        second = web_evidence.ground_license(
            RAW.replace("victim.py", "other.py"), _cache=cache)
        reused = (second.get("cache_hit") is True
                  and len(calls5) == n_after_first
                  and second["spdx"] == first["spdx"])
    finally:
        web_evidence.fetch_source = original_fetch
    cases.append({"case": "同一仓库多条命中共享缓存，不重复拉取",
                  "status": second["status"], "reason": second["reason"],
                  "spdx": second["spdx"], "url": second["url"],
                  "attempts": second["attempts"], "passed": reused})

    return {"cases": cases, "passed": sum(c["passed"] for c in cases),
            "total": len(cases)}


def _build_index():
    import tempfile
    corpus = tempfile.mkdtemp(prefix="cg-license-eval-")
    docs, texts = make_corpus(["ring_cache.py"], corpus)
    return build_index(corpus, docs, texts)


def run_end_to_end(original_fetch):
    web_text = read_negative("word_tally.py")
    out = {}

    def probe(fetch, label):
        web_evidence.fetch_source = fetch
        try:
            index = _build_index()
            docs_before, cms_before = len(index.docs), index.cms.total
            result = web_evidence.run_web_probe(
                index, None, FixtureProvider("UNKNOWN"), web_text, "review.py", {},
                "distribution", "MIT")
            f = result["findings"][0] if result["findings"] else {}
            prov = f.get("provenance", {})
            invariants = {
                "offline_index_unchanged": (len(index.docs) == docs_before
                                            and index.cms.total == cms_before),
                "never_blocks": result["blocking"] is False,
                "risk_capped_at_S3": f.get("risk") != "S4",
                "audit_fields_present": all(
                    k in prov for k in ("url", "sha256", "fetched_at", "license_grounding")),
            }
            return {"label": label,
                    "license_source": prov.get("license_source"),
                    "license_spdx": f.get("license_spdx"),
                    "risk": f.get("risk"),
                    "grounding_status": prov.get("license_grounding", {}).get("status"),
                    "grounding_reason": prov.get("license_grounding", {}).get("reason"),
                    "grounding_attempts": len(prov.get("license_grounding", {}).get("attempts", [])),
                    "invariants": invariants}
        finally:
            web_evidence.fetch_source = original_fetch

    ok_fetch, _ = make_fetch(web_text, ROOT_URL + "LICENSE", GPL3)
    ok = probe(ok_fetch, "上游 LICENSE 可拉取并可识别")
    ok["passed"] = (ok["license_source"] == "web:license-text-verified"
                    and ok["grounding_status"] == "verified"
                    and all(ok["invariants"].values()))

    fail_fetch, _ = make_fetch(web_text, fail_licences=True)
    failed = probe(fail_fetch, "上游 LICENSE 全部拉取失败")
    failed["passed"] = (failed["license_source"] == "web:llm-inferred"
                        and failed["grounding_status"] == "unavailable"
                        and bool(failed["grounding_reason"])
                        and failed["grounding_attempts"] > 0
                        and all(failed["invariants"].values()))

    out["verified_case"] = ok
    out["failed_case"] = failed
    out["passed"] = sum(1 for c in (ok, failed) if c["passed"])
    out["total"] = 2
    return out


def to_markdown(payload):
    s = payload["summary"]
    lines = [
        "# llmFusion LICENSE 文本核验通道 · 离线可复现评测",
        "",
        "- 生成时间：%s" % payload["generated_at"],
        "- 模式：**%s**（`fetch_source` 由固定离线夹具注入，未发起任何真实网络请求、未使用任何 API Key）" % payload["mode"],
        "- 复现命令：`python scripts/eval_license_grounding.py`",
        "",
        "> **不得据此主张真实联网核验成功率。** 本评测只证明核验通道的分类逻辑、"
        "审计字段与端到端链路正确且可复现。真实联网的 `web:license-text-verified` 比率"
        "仍须在稳定网络下用 `scripts/eval_webprobe.py` 另行测量。"
        "2026-11-15 的 webprobe / round2 留存证据中该比率为 0/2，口径不变。",
        "",
        "## 结果总览",
        "",
        "| 分组 | 通过 / 总数 |",
        "|---|---|",
        "| SPDX 签名分类 | %d / %d |" % (payload["classifier"]["passed"], payload["classifier"]["total"]),
        "| 核验通道（成功/回退/失败审计/缓存） | %d / %d |" % (payload["grounding"]["passed"], payload["grounding"]["total"]),
        "| 端到端 webprobe（成功 + 失败两条路径） | %d / %d |" % (payload["end_to_end"]["passed"], payload["end_to_end"]["total"]),
        "| **合计** | **%d / %d** |" % (s["passed"], s["total"]),
        "",
        "## 1. SPDX 签名分类",
        "",
        "| 用例 | 期望 | 实际 | 结果 |",
        "|---|---|---|---|",
    ]
    for r in payload["classifier"]["cases"]:
        lines.append("| %s | %s | %s | %s |" % (
            r["case"], r["expected"], r["actual"], "通过" if r["passed"] else "失败"))
    lines += ["", "## 2. ground_license 行为", "",
              "| 用例 | status | reason | SPDX | 尝试 URL 数 | 结果 |",
              "|---|---|---|---|---|---|"]
    for r in payload["grounding"]["cases"]:
        lines.append("| %s | %s | %s | %s | %d | %s |" % (
            r["case"], r["status"], r["reason"], r["spdx"] or "—",
            len(r["attempts"]), "通过" if r["passed"] else "失败"))
    lines += ["", "## 3. 端到端 webprobe", ""]
    for key in ("verified_case", "failed_case"):
        c = payload["end_to_end"][key]
        lines += ["### %s" % c["label"], "",
                  "- `license_source`: `%s`；`license_spdx`: `%s`；`risk`: `%s`" % (
                      c["license_source"], c["license_spdx"], c["risk"]),
                  "- `license_grounding`: status=`%s`，reason=`%s`，记录尝试 %d 个 URL" % (
                      c["grounding_status"], c["grounding_reason"], c["grounding_attempts"]),
                  "- 安全不变量：%s" % "、".join(
                      "%s=%s" % (k, "成立" if v else "违反") for k, v in c["invariants"].items()),
                  ""]
    lines += ["## 本次修补相对旧版的变化", "",
              "1. 失败不再静默：`provenance.license_grounding` 记录 status / reason / 逐 URL attempts。",
              "2. 候选文件名补入 `COPYING`、`LICENSE.rst`、`LICENCE`、`docs/LICENSE`（旧版只试 3 个）。",
              "3. 同一仓库的多条命中共享缓存，不再按 finding 重复拉取 LICENSE。",
              "4. LICENSE 拉取使用独立的 8 秒超时，避免拖垮整次 probe。",
              "5. `ground_license` 恒定返回可审计字典；调用方以 `spdx` 判定成功，而非字典真值。",
              ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    parser.add_argument("--date", default="")
    args = parser.parse_args(argv)

    original_fetch = web_evidence.fetch_source
    classifier = run_classifier()
    grounding = run_grounding(original_fetch)
    e2e = run_end_to_end(original_fetch)
    total = (classifier["total"] + grounding["total"] + e2e["total"])
    passed = (classifier["passed"] + grounding["passed"] + e2e["passed"])
    payload = {
        "schema": "codeguard.license-grounding-eval/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "offline-fixture",
        "not_a_claim": ("离线夹具验证通道逻辑与可复现性；不代表真实联网核验成功率。"
                        "2026-11-15 留存联网证据的 license_verified_rate 仍为 0/2。"),
        "environment": {"python": sys.version.split()[0],
                        "network": "none", "api_key": "none",
                        "fixture_source_url": RAW,
                        "grounding_timeout_s": web_evidence.GROUNDING_TIMEOUT,
                        "licence_candidates": list(web_evidence._LIC_NAMES)},
        "classifier": classifier,
        "grounding": grounding,
        "end_to_end": e2e,
        "summary": {"passed": passed, "total": total,
                    "all_passed": passed == total},
    }
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / ("license-grounding-eval-%s.json" % date)).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / ("license-grounding-eval-%s.md" % date)).write_text(
        to_markdown(payload), encoding="utf-8")
    print("passed %d/%d; evidence -> %s" % (passed, total, out), flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
