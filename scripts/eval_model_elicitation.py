"""Turn elicited assistant answers into a labelled scan against our own corpus.

LiCoEval proves the gate catches leakage from a *foreign* corpus of real model
output.  This script answers the narrower question the judges will ask: does it
catch leakage from the copyleft packages we actually indexed (mercurial
GPL-2.0-or-later, pylint GPL-2.0-or-later, glances LGPL-3.0-only, paramiko
LGPL-2.1)?

Protocol, recorded into the emitted evidence:

* prompts live in ``scripts/elicitation_prompts.jsonl`` and never name a project
  - they describe the task a developer would type;
* responses are raw model output, one file per prompt id, kept outside the
  repository (``.codeguard/external/elicitation/responses``);
* the model must answer from parametric memory only: no corpus file may be read
  and no web search performed while generating, otherwise a hit would be
  retrieval rather than regurgitation;
* no expected source is claimed up front (``source_package`` empty), so a finding
  is a *candidate* leak that two people then label A/B/C.

Usage:
    python scripts/eval_model_elicitation.py                 # product index
    python scripts/eval_model_elicitation.py --responses DIR
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PROMPTS = ROOT / "scripts" / "elicitation_prompts.jsonl"
DEFAULT_RESPONSES = ROOT / ".codeguard" / "external" / "elicitation" / "responses"
WORK = ROOT / ".codeguard" / "external" / "elicitation"
TARGET_LICENSE = "MIT"
USAGE = "distribution"
# 供应方策略不允许披露底层模型标识，因此只记录可核验的事实：接口、日期与协议
MODEL_LABEL = "Qoder Desktop 内置编码助手（底层模型标识受供应方策略限制，无法披露）"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_prompts(path: Path) -> list:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def build_manifest(prompts: list, responses: Path) -> tuple:
    rows, missing = [], []
    for prompt in prompts:
        path = responses / (prompt["id"] + ".py")
        if not path.exists():
            missing.append(prompt["id"])
            continue
        code = path.read_text(encoding="utf-8")
        rows.append({
            "id": "elicit-" + prompt["id"],
            "label": "copied",
            "language": prompt.get("language", "python"),
            "license": TARGET_LICENSE,
            "usage": USAGE,
            "code": code,
            "note": "诱发样本 %s：%s；答案 SHA-256 %s" % (
                prompt["id"], prompt.get("hypothesis", ""), sha256_text(code)[:12]),
        })
    manifest = WORK / "elicit-manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows, missing, manifest


COPYLEFT = ("strong", "weak", "network")


def copyleft_hits(sample: dict) -> list:
    from codeguard.license_intel import profile_for
    return [f for f in sample["findings"]
            if profile_for(f["license"]).family in COPYLEFT]


def render(payload: dict, protocol: dict) -> str:
    from codeguard.evaluate import to_markdown
    from codeguard.license_intel import profile_for
    leak = payload["elicitation"]
    base = to_markdown(payload, "模型记忆诱发正例评测（自有 copyleft 语料）")
    lines = ["", "## 诱发协议", ""]
    for key in ("model", "generated_at", "prompts_file", "prompts_sha256", "responses_dir",
                "constraints"):
        lines.append("- %s：%s" % (key, protocol[key]))
    lines += ["", "| 指标 | 数值 |", "|---|---|",
              "| 提示词 / 已采集回答 | %d / %d |" % (protocol["prompts"], leak["samples"]),
              "| 出现任意命中 | %d / %d |" % (leak["any_finding"], leak["samples"]),
              "| 达到阻断阈值 | %d / %d |" % (leak["blocking"], leak["samples"]),
              "| 命中 copyleft 语料（mercurial/pylint/glances/paramiko） | %d / %d |" % (
                  leak["copyleft_hit"], leak["samples"]),
              "| 最长逐字命中 | %d token |" % leak["max_verbatim"], "",
              "## 逐条候选（归属待双人标注，不预先断言）", "",
              "| 样本 | 最高风险 | copyleft 命中 | 命中来源 | 逐字 | 覆盖率 | 置信度 |",
              "|---|---|---|---|---|---|---|"]
    for sample in payload["samples"]:
        hits = copyleft_hits(sample)
        source = ", ".join(sorted({f["package"] for f in hits}))[:40] or "-"
        lines.append("| %s | %s | %d | %s | %d | %.2f | %.2f |" % (
            sample["id"], sample["max_risk"] or "-", len(hits), source,
            max([f["verbatim_run"] for f in hits] or [0]),
            max([f["coverage"] for f in hits] or [0.0]),
            max([f["confidence"] for f in hits] or [0.0])))
    lines += ["", "## 标注口径", "",
              "- **A**：输出与某段 copyleft 源码构成实质逐字复现（许可污染正例）；",
              "- **B**：仅命中通用惯用写法/样板（例如 argparse、异常处理），不构成复现；",
              "- **C**：需要查看原文才能判断，交第三人复核。",
              "- 未标注前，本表数字只能表述为“候选”，不能表述为“检出 N 条真实泄漏”。", ""]
    if not leak["copyleft_hit"]:
        lines += ["## 试点读数解释", "",
                  "- 本组 %d 条回答与自有 copyleft 语料**没有任何片段命中**；" % leak["samples"],
                  "- 这既不能读成“模型不会泄漏”（外部数据集已证明会，见 model-leak 证据），"
                  "也不能读成“检测器失效”（同一索引的变异基准仍 99% 检出）；",
                  "- 合理解释是：自有语料只收录每个包的部分文件（≤90 个），且指令化模型逐字复现"
                  "小众项目内部实现的概率很低；要把它变成正例证据，需要改用可披露型号的公开对话模型"
                  "并扩大提示数量。", ""]
    if protocol["missing"]:
        lines += ["## 尚未采集", "", "缺少回答的提示词：%s" % ", ".join(protocol["missing"]), ""]
    return base + "\n".join(lines) + "\n"


def worksheet(payload: dict) -> str:
    lines = ["# 模型记忆诱发样本标注表（双人独立标注）", "",
             "逐条把 CodeGuard 的命中与提示词原文对照，判定 A/B/C（口径见评测报告）。", "",
             "| 样本 | 提示词 | 命中来源与许可 | 逐字 | 判定1 | 判定2 |", "|---|---|---|---|---|---|"]
    prompts = {row["id"]: row for row in load_prompts(PROMPTS)}
    for sample in payload["samples"]:
        pid = sample["id"].split("-", 1)[1]
        prompt = prompts.get(pid, {})
        hits = collections.Counter(
            "%s/%s" % (f["package"], f["license"]) for f in copyleft_hits(sample))
        lines.append("| %s | %s | %s | %d |  |  |" % (
            sample["id"], str(prompt.get("prompt", ""))[:60].replace("|", "\\|"),
            ", ".join("%s×%d" % (k, v) for k, v in hits.most_common(3)) or "无 copyleft 命中",
            max([f["verbatim_run"] for f in copyleft_hits(sample)] or [0])))
    lines += ["", "- 标注人1：＿＿＿＿＿＿　日期：＿＿＿＿＿＿",
              "- 标注人2：＿＿＿＿＿＿　日期：＿＿＿＿＿＿", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--responses", default=str(DEFAULT_RESPONSES))
    parser.add_argument("--date", default="")
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    args = parser.parse_args(argv)
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    if not PROMPTS.exists():
        raise SystemExit("找不到提示词文件 %s" % PROMPTS)
    prompts = load_prompts(PROMPTS)
    rows, missing, manifest = build_manifest(prompts, Path(args.responses))
    if not rows:
        raise SystemExit(" responses 目录里没有回答：%s" % args.responses)
    print("诱发样本：%d 条（缺回答 %s）" % (len(rows), ",".join(missing) or "无"), flush=True)

    stem = "model-elicit-%s" % date
    tmp_out = WORK / ("eval-" + stem)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code = subprocess.run([sys.executable, "-m", "codeguard", "eval",
                           "--manifest", str(manifest), "--out", str(tmp_out),
                           "--title", "模型记忆诱发正例评测（%d 条回答）" % len(rows)],
                          cwd=str(ROOT), env=env).returncode
    payload_path = tmp_out / "eval.json"
    if not payload_path.exists():
        raise SystemExit("评测未产出 %s（退出码 %d）" % (payload_path, code))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    blocking = sum(1 for s in payload["samples"] if s["blocking"])
    any_hit = sum(1 for s in payload["samples"] if s["finding_count"])
    copyleft_hit = sum(1 for s in payload["samples"] if copyleft_hits(s))
    max_verbatim = max([f["verbatim_run"] for s in payload["samples"]
                        for f in copyleft_hits(s)] or [0])
    packages = collections.Counter(f["package"] for s in payload["samples"]
                                   for f in copyleft_hits(s))
    if payload.get("metadata", {}).get("manifest"):
        payload["metadata"]["manifest"] = os.path.relpath(
            payload["metadata"]["manifest"], ROOT).replace(os.sep, "/")
    payload["elicitation"] = {"samples": len(rows), "blocking": blocking,
                              "any_finding": any_hit, "copyleft_hit": copyleft_hit,
                              "max_verbatim": max_verbatim,
                              "copyleft_package_census": dict(packages)}
    payload["protocol"] = {
        "model": MODEL_LABEL,
        "generated_at": date,
        "prompts_file": str(PROMPTS.relative_to(ROOT)).replace(os.sep, "/"),
        "prompts_sha256": sha256_text(PROMPTS.read_text(encoding="utf-8"))[:16],
        "responses_dir": os.path.relpath(args.responses, ROOT).replace(os.sep, "/"),
        "prompts": len(prompts),
        "missing": missing,
        "constraints": ("生成时未读取 .codeguard/corpus 下的任何原文、未联网检索原文；"
                        "每条回答为单次问答的原始输出，未做人工改写；"
                        "同一助手族也参与过本项目开发，因此本组样本只作为自有语料上的"
                        "诱发试点，不替代外部数据集结论"),
        "target_license": TARGET_LICENSE, "usage": USAGE,
        "claim_limit": ("本组样本没有预先断言的真实来源，命中只是候选；"
                        "在双人标注完成前不得写成“检出 N 条真实泄漏”"),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / (stem + ".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / (stem + ".md")).write_text(render(payload, payload["protocol"]), encoding="utf-8")
    (out_dir / (stem + "-标注表.md")).write_text(worksheet(payload), encoding="utf-8")
    print("\n诱发样本证据：%s" % (out_dir / (stem + ".md")))
    print("  候选命中 %d/%d；copyleft 命中 %d/%d；阻断 %d；最长逐字 %d token"
          % (any_hit, len(rows), copyleft_hit, len(rows), blocking, max_verbatim))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
