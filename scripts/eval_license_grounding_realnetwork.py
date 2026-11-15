"""Real-network LICENSE grounding: trigger ``web:license-text-verified`` end to end.

WHY THIS EXISTS
---------------
The 2026-11-15 webprobe / round2 evidence records ``license_verified_rate 0/2``:
the channel existed but never fired on a real run. ``eval_license_grounding.py``
already proves the logic end to end with *fully injected* offline fixtures
(18/18), but that cannot be presented as a real-network verification.

This evaluation is deliberately **hybrid** and says so:

  * the upstream-proposal step stays an offline deterministic fixture (no
    Tavily / LLM key, no query sent, no user source uploaded);
  * the upstream LICENSE text is fetched from the **real public network** via
    the shipped ``fetch_source``, with URL + SHA-256 + timestamp recorded;
  * ``run_web_probe`` must then promote the finding's provenance from
    ``web:llm-inferred`` to ``web:license-text-verified``.

HONESTY BOUNDARY
----------------
This is ONE successful real-network grounding case, not a success-rate claim.
It does NOT rewrite the historical ``0/2`` in webprobe-eval-20261115.json or
llmfusion-round2-realprojects.json, and it does NOT claim a real LLM proposal.
A full real-network webprobe rate still needs a stable connection plus user
provisioned keys, measured with ``scripts/eval_webprobe.py``.

Usage:
    python scripts/eval_license_grounding_realnetwork.py [--out-dir DIR]
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

from codeguard import web_evidence as w                # noqa: E402
from helpers import build_index, make_corpus, read_negative   # noqa: E402

REAL_RAW = ("https://raw.githubusercontent.com/pallets/itsdangerous/"
            "main/src/itsdangerous/timed.py")
REAL_ROOT = "https://raw.githubusercontent.com/pallets/itsdangerous/main/"
LICENCE_MARKERS = ("LICENSE", "COPYING", "LICENCE")
MAX_NETWORK_ATTEMPTS = 3
NETWORK_TIMEOUT = 6

real_fetch_source = w.fetch_source
w.GROUNDING_TIMEOUT = NETWORK_TIMEOUT


class FixtureProvider:
    """Deterministic stand-in for the LLM + Tavily proposal step (no keys)."""

    model = "offline-fixture-provider (real-network grounding)"

    def chat_with_search(self, prompt, seeds=(), timeout=90, max_rounds=3):
        assert "严禁逐字包含" in prompt, "search-query guard must stay in the prompt"
        reply = ('```json\n{"candidates": [{"url": "%s", "package": "itsdangerous", '
                 '"version": "main", "license_spdx": "UNKNOWN", '
                 '"reason": "fixture proposal; licence verified against upstream text"}]}\n```'
                 % REAL_RAW)
        return reply, [{"query": "itsdangerous license", "results": []}]


def _payload(text, url):
    raw = text.encode()
    return {"url": url, "text": text, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "fetched_at": int(time.time())}


def make_hybrid_fetch(web_text, log):
    """Source = deterministic fixture; upstream LICENSE = real network."""

    def hybrid(url, timeout=NETWORK_TIMEOUT):
        tail = url.rsplit("/", 1)[-1].upper()
        if not any(m in tail for m in LICENCE_MARKERS):
            out = _payload(web_text, url)
            out["url"] = url
            return out
        last = None
        for attempt in range(MAX_NETWORK_ATTEMPTS):
            t0 = time.time()
            try:
                out = real_fetch_source(url, timeout)
                log.append({"url": url, "outcome": "real-network-200",
                            "bytes": out["bytes"], "sha256": out["sha256"],
                            "elapsed_s": round(time.time() - t0, 2),
                            "attempt": attempt + 1})
                return out
            except ValueError as exc:
                log.append({"url": url, "outcome": "real-network-failed",
                            "reason": str(exc)[:160],
                            "elapsed_s": round(time.time() - t0, 2),
                            "attempt": attempt + 1})
                last = exc
                time.sleep(0.4)
        raise last

    return hybrid


def build_temp_index():
    import tempfile
    corpus = tempfile.mkdtemp(prefix="cg-realground-")
    docs, texts = make_corpus(["ring_cache.py"], corpus)
    return build_index(corpus, docs, texts)


def run():
    web_text = read_negative("word_tally.py")
    network_log = []
    hybrid = make_hybrid_fetch(web_text, network_log)

    w.fetch_source = hybrid
    try:
        index = build_temp_index()
        docs_before, cms_before = len(index.docs), index.cms.total
        t0 = time.time()
        result = w.run_web_probe(index, None, FixtureProvider(), web_text,
                                 "review.py", {}, "distribution", "MIT")
        elapsed_ms = int((time.time() - t0) * 1000)
        finding = result["findings"][0] if result["findings"] else {}
        prov = finding.get("provenance", {})
        grounding = prov.get("license_grounding", {})
        invariants = {
            "offline_index_unchanged": (len(index.docs) == docs_before
                                        and index.cms.total == cms_before),
            "never_blocks": result["blocking"] is False,
            "risk_capped_at_S3": finding.get("risk") != "S4",
            "audit_fields_present": all(k in prov for k in
                                        ("url", "sha256", "fetched_at",
                                         "license_source", "license_grounding")),
            "real_network_license_fetched": any(
                x["outcome"] == "real-network-200" for x in network_log),
        }
        verified = (prov.get("license_source") == "web:license-text-verified"
                    and grounding.get("status") == "verified"
                    and all(invariants.values()))
        return {"verified": verified, "invariants": invariants,
                "license_source": prov.get("license_source"),
                "license_spdx": finding.get("license_spdx"),
                "license_spdx_verified": prov.get("license_spdx_verified"),
                "license_url": prov.get("license_url"),
                "license_sha256": prov.get("license_sha256"),
                "grounding_status": grounding.get("status"),
                "grounding_reason": grounding.get("reason"),
                "grounding_attempts": grounding.get("attempts", []),
                "risk": finding.get("risk"),
                "blocking": result.get("blocking"),
                "elapsed_ms": elapsed_ms,
                "network_log": network_log,
                "notes": result.get("notes", [])}
    finally:
        w.fetch_source = real_fetch_source


def to_markdown(p: dict) -> str:
    r = p["result"]
    lines = [
        "# llmFusion LICENSE 文本核验通道 · 真实网络触发用例",
        "",
        "- 生成时间：%s" % p["generated_at"],
        "- 模式：**%s**（混合模式）" % p["mode"],
        "- 复现命令：`python scripts/eval_license_grounding_realnetwork.py`",
        "",
        "> **口径边界（务必先读）**：本用例**提案环节为离线确定性夹具**（未使用 Tavily / 大模型密钥、"
        "未发出检索查询、未上传用户源码），但 **上游 LICENSE 原文由真实公网拉取**，"
        "经 `fetch_source` → `classify_license_text` → `ground_license` 走完出厂代码路径。"
        "它证明「给定正确候选地址时，核验通道能在真实网络触发并留下可核验证据」，"
        "**不改写** `webprobe-eval-20261115.json` 与 `llmfusion-round2-realprojects.json` 中"
        "真实联网评测 `license_verified_rate 0/2` 的历史口径，也不构成联网核验成功率结论。"
        "完整真实联网（含 LLM 提案）的成功率仍须自配密钥、在稳定网络下用 `scripts/eval_webprobe.py` 测量。",
        "",
        "## 一、结果",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 端到端 `license_source` | `%s` |" % r["license_source"],
        "| 核验状态 / 原因 | `%s` / `%s` |" % (r["grounding_status"], r["grounding_reason"]),
        "| 上游 LICENSE URL | `%s` |" % r["license_url"],
        "| 上游 LICENSE SHA-256 | `%s` |" % r["license_sha256"],
        "| 确定性 SPDX 识别 | `%s` |" % (r["license_spdx_verified"] or r["license_spdx"]),
        "| 命中风险 / 是否阻断 | `%s` / `%s` |" % (r["risk"], r["blocking"]),
        "| 本次耗时 | %d ms |" % r["elapsed_ms"],
        "| 判定 | **%s** |" % ("PASS：核验通道真实触发" if r["verified"] else "FAIL"),
        "",
        "## 二、逐 URL 网络轨迹（真实请求）",
        "",
        "| URL | 结果 | 字节 | SHA-256 | 耗时 |",
        "|---|---|---|---|---|",
    ]
    for x in r["network_log"]:
        lines.append("| `%s` | %s | %s | `%s` | %s s |"
                     % (x["url"], x["outcome"], x.get("bytes", "—"),
                        x.get("sha256", x.get("reason", "—"))[:20], x["elapsed_s"]))
    lines += [
        "",
        "## 三、安全不变量",
        "",
        "| 不变量 | 成立 |",
        "|---|---|",
    ]
    for k, v in r["invariants"].items():
        lines.append("| `%s` | %s |" % (k, "是" if v else "否"))
    lines += [
        "",
        "## 四、与已有证据的关系",
        "",
        "- `license-grounding-eval-20261115.*`（18/18，offline-fixture）：证明分类逻辑、失败可审计、"
        "端到端链路正确且完全可复现，**不代表联网成功率**。",
        "- `webprobe-eval-20261115.*` / `llmfusion-round1/2-*`：真实联网评测，成功检出均为 "
        "`web:llm-inferred`，`license_verified_rate 0/2`；**本文件不修改该结论**。",
        "- 本文件（hybrid-real-network-grounding）：补上一次**真实网络原文拉取**并成功升级为 "
        "`web:license-text-verified` 的用例，把「通道已实现」推进到「通道在真实原文上可核验」。",
        "",
        "三者口径不同，引用时必须分别标注，不得合并成一个成功率。",
        "",
        "## 五、局限",
        "",
        "- 仅 1 个上游仓库（itsdangerous，LICENSE.txt → BSD-3-Clause），样本量为 1，不推断总体成功率。",
        "- 网络经本机代理，其它候选 URL 在本次试验中出现 502 / 超时，均已记录在轨迹中并按失败回退处理。",
        "- 提案环节仍是夹具，因此本用例不能支撑「AI 联网提案有效」的结论；该结论仍以 round2 的比率口径为准。",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = run()
    payload = {
        "schema": "codeguard.license-grounding-realnetwork/v1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "hybrid-real-network-grounding",
        "proposal": "offline-deterministic-fixture (no API key, no query, no source upload)",
        "licence_fetch": "real public network via shipped fetch_source",
        "source_url": REAL_RAW,
        "result": result,
        "does_not_rewrite": ["webprobe-eval-20261115.json license_verified_rate 0/2",
                             "llmfusion-round2-realprojects.json licence labels"],
    }
    stem = "license-grounding-realnetwork-20261115"
    (out / (stem + ".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / (stem + ".md")).write_text(to_markdown(payload), encoding="utf-8")
    print("verified=%s license_source=%s spdx=%s licence_url=%s"
          % (result["verified"], result["license_source"],
             result["license_spdx_verified"], result["license_url"]))


if __name__ == "__main__":
    main()
