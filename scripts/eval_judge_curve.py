"""Pair-level ablation: rule fallback vs the 12-feature logistic-regression judge.

WHY THIS EXISTS
---------------
The technical report states "file-level detection is 97% with and without the
model; what the model buys is pair-level ranking and threshold headroom" but
only backed it with words. The official rubric asks whether the AI's role is
*explicit and necessary*. This script turns that claim into a reproducible
precision-recall / threshold-recall curve computed over the exact same
candidate pairs as benchmark-20261115.json.

HONESTY BOUNDARY
----------------
* Unit of analysis = one (span, candidate chunk) PAIR, not one file. Do not
  read these numbers as file-level detection rates.
* Both configurations share the same retrieval, the same exact-verification
  features (feats_idf) and the same candidate set; only the scorer differs.
* File-level detection stays 97% for both because the production gate is
  ultimately decided by the corroboration rule (coverage / verbatim run /
  confidence). The curve quantifies *ranking headroom*, not a detection gain.
* The judge is the shipped, already-trained model (.codeguard/model.json);
  no retraining, no new labels, no tuning against this curve.

Usage:
    python scripts/eval_judge_curve.py --root . --out-dir submission/evidence
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SEED = 20260101
FILES = 24
CHARS = 5000
PER_PACKAGE = 2
THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(15)]   # 0.20 .. 0.90
PROD_THRESHOLD = 0.55


def build_pairs(root: Path):
    sys.path.insert(0, str(root / "src"))
    from codeguard import benchmark as bm
    from codeguard.adjudicate import CandidateReader
    from codeguard.score import LogisticRegression

    cg = root / ".codeguard"
    corpus_root = cg / "corpus"
    entries = bm.read_manifest(str(corpus_root / "corpus.json"))
    origins = bm.sample_origins(str(corpus_root), entries, PER_PACKAGE, SEED,
                                min_chars=1500)
    origins = sorted(origins, key=lambda e: e.sha256)[:FILES]
    doc_id_by_path = {e.path: i for i, e in enumerate(origins)}
    index = bm.build_bench_index(str(corpus_root), origins)
    cases = bm.make_cases(str(corpus_root), origins, CHARS, SEED, bm.MUTATIONS,
                          doc_ids=[doc_id_by_path[e.path] for e in origins])
    cases += bm.negative_cases(CHARS, len(origins) * len(bm.MUTATIONS) + 1000)
    collected = bm.collect_traces(index, cases, CandidateReader(index))
    traces_all = collected["traces"]
    model = LogisticRegression.from_json(
        json.loads((cg / "model.json").read_text(encoding="utf-8")))

    rows = []
    for case in cases:
        for tr in traces_all[case.cid]:
            feats = tr.feats_idf
            label = 1 if (case.origin_doc >= 0 and tr.doc == case.origin_doc) else 0
            rule = bm.rule_prob(feats, bm.ALL_LAYERS, sum(tr.band_hits.values()))
            judge = bm.judge_prob(model, feats)
            rows.append((rule, judge, label))
    return rows, collected["pairs_verified"], collected["collect_seconds"], index.stats()


def metrics_at(rows, scorer_idx, threshold):
    tp = fp = fn = 0
    for r in rows:
        hit = r[scorer_idx] >= threshold
        if hit and r[2] == 1:
            tp += 1
        elif hit and r[2] == 0:
            fp += 1
        elif not hit and r[2] == 1:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)
    return {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4)}


def to_markdown(p: dict) -> str:
    a = p["summary"]
    lines = [
        "# 判定层消融：规则回退 vs 12 维逻辑回归（配对级）",
        "",
        "- 生成时间：%s" % p["generated_at"],
        "- 复现命令：`python scripts/eval_judge_curve.py --root <repo>`",
        "- 候选对：%d（与 `benchmark-20261115.json` 同源、同种子 %d、同 %d 个来源文件）；"
        "固定语料与已训练模型，无重训、无调参。" % (p["pairs"], SEED, FILES),
        "",
        "> **口径边界（务必先读）**：本表的单位是 **(片段, 候选原文) 配对**，不是文件。"
        "文件级检出在两种打分下均为 97%，因为生产门禁由佐证规则（覆盖率 / 逐字命中 / 置信度）兜底；"
        "本曲线量化的是**配对级排序能力与阈值余量**，不得写成「模型把检出率提高了多少」。",
        "",
        "## 一、总体",
        "",
        "| 指标 | 规则回退（RULE_WEIGHTS） | 12 维逻辑回归 |",
        "|---|---|---|",
        "| 配对级 AUC | %s | %s |" % (a["rule"]["auc"], a["judge"]["auc"]),
        "| 出厂阈值 %s 精确率 | %s | %s |"
        % (PROD_THRESHOLD, a["rule"]["at_prod"]["precision"],
           a["judge"]["at_prod"]["precision"]),
        "| 出厂阈值 %s 召回率 | %s | %s |"
        % (PROD_THRESHOLD, a["rule"]["at_prod"]["recall"],
           a["judge"]["at_prod"]["recall"]),
        "| 出厂阈值 %s F1 | %s | %s |"
        % (PROD_THRESHOLD, a["rule"]["at_prod"]["f1"],
           a["judge"]["at_prod"]["f1"]),
        "| 最佳 F1（扫描阈值后） | %s @ %s | %s @ %s |"
        % (a["rule"]["best_f1"], a["rule"]["best_threshold"],
           a["judge"]["best_f1"], a["judge"]["best_threshold"]),
        "",
        "AUC 用 Mann-Whitney 秩统计（含并列平均）计算，与 `score.py:rank_auc` 一致。",
        "",
        "## 二、阈值扫描（同一批候选对）",
        "",
        "| 阈值 | 规则精确率 | 规则召回 | 模型精确率 | 模型召回 |",
        "|---|---|---|---|---|",
    ]
    for r, j in zip(p["curves"]["rule"], p["curves"]["judge"]):
        lines.append("| %s | %s | %s | %s | %s |"
                     % (r["threshold"], r["precision"], r["recall"],
                        j["precision"], j["recall"]))
    lines += [
        "",
        "## 三、怎么读这张图",
        "",
        "1. `eval_judge_curve.png` 左图为配对级 PR 曲线，右图为阈值—精确率/召回曲线；"
        "竖线标出生产门禁阈值 %s。" % PROD_THRESHOLD,
        "2. 报告三.1 的主张「IDF 与模型买到的是允许调低阈值追更高召回而不失控的空间」，"
        "现在有可复算的曲线支撑：比较两条曲线在阈值下调时精确率的衰减速度，"
        "而不是比较文件级检出率。",
        "3. 规则回退并非摆设：未加载模型时工具仍完整可用（报告三.1 明确写「规则回退」）。"
        "模型的价值是把人工权衡 12 维证据的组合权重变成可学习、可校准、可交叉验证的组合器，"
        "使同一阈值下的配对级排序更稳。",
        "",
        "## 四、局限",
        "",
        "- 候选对来自受控变异基准的 24 个来源文件，正例由构造性变异产生，不代表真实开源生态的先验分布。",
        "- 曲线衡量的是「候选对是否指向正确来源文档」，与 HumanEval 干净负例的误阻断率是两个不同问题。",
        "- 判定模型留出 AUC 0.870、ECE 0.074 与 5 种子 CV 见 `benchmark-20261115.json`，"
        "本曲线不替代留出评估，只补充「相对规则回退」这一对照组。",
        "",
    ]
    return "\n".join(lines)


def make_plot(payload: dict, out: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rule, judge = payload["curves"]["rule"], payload["curves"]["judge"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.3), dpi=160)

    ax1.plot([r["recall"] for r in rule], [r["precision"] for r in rule],
             "o-", color="#7a6a4f", lw=1.6, ms=3.5, label="Rule fallback")
    ax1.plot([r["recall"] for r in judge], [r["precision"] for r in judge],
             "s-", color="#a32d2d", lw=1.8, ms=3.5, label="Logistic-regression judge")
    ax1.set_xlabel("Pair-level recall")
    ax1.set_ylabel("Pair-level precision")
    ax1.set_title("Pair-level precision-recall (same candidate set)")
    ax1.set_xlim(-0.02, 1.02)
    ax1.set_ylim(-0.02, 1.02)
    ax1.grid(alpha=0.25, ls=":")
    ax1.legend(fontsize=8, loc="lower left")

    ths = [r["threshold"] for r in rule]
    ax2.plot(ths, [r["precision"] for r in rule], "--", color="#7a6a4f",
             lw=1.4, label="Rule precision")
    ax2.plot(ths, [r["recall"] for r in rule], "-", color="#7a6a4f",
             lw=1.6, label="Rule recall")
    ax2.plot(ths, [r["precision"] for r in judge], "--", color="#a32d2d",
             lw=1.4, label="Judge precision")
    ax2.plot(ths, [r["recall"] for r in judge], "-", color="#a32d2d",
             lw=1.8, label="Judge recall")
    ax2.axvline(PROD_THRESHOLD, color="#185fa5", lw=1.2, ls=":",
                label="Production threshold 0.55")
    ax2.set_xlabel("Score threshold")
    ax2.set_ylabel("Precision / recall")
    ax2.set_title("Threshold sensitivity (pair level)")
    ax2.set_ylim(-0.02, 1.02)
    ax2.grid(alpha=0.25, ls=":")
    ax2.legend(fontsize=7.5, ncol=2, loc="lower left")

    fig.tight_layout()
    fig.savefig(out / "eval_judge_curve.png", bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="repo root containing .codeguard/")
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()
    root, out = Path(a.root), Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows, pairs_verified, collect_seconds, index_stats = build_pairs(root)
    sys.path.insert(0, str(root / "src"))
    from codeguard.score import rank_auc

    curves = {}
    summary = {}
    for name, idx in (("rule", 0), ("judge", 1)):
        curve = [metrics_at(rows, idx, t) for t in THRESHOLDS]
        curves[name] = curve
        best = max(curve, key=lambda r: r["f1"])
        prod = min(curve, key=lambda r: abs(r["threshold"] - PROD_THRESHOLD))
        summary[name] = {
            "auc": round(rank_auc([r[idx] for r in rows],
                                  [r[2] for r in rows]), 4),
            "at_prod": prod, "best_f1": best["f1"],
            "best_threshold": best["threshold"]}

    payload = {
        "schema": "codeguard.judge-ablation/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "offline-recompute-from-shipped-model",
        "seed": SEED, "files": FILES, "chars": CHARS,
        "pairs": len(rows), "pairs_verified_reported": pairs_verified,
        "collect_seconds": collect_seconds,
        "index_documents": index_stats.get("documents"),
        "index_chunks": index_stats.get("chunks"),
        "production_threshold": PROD_THRESHOLD,
        "unit": "candidate pair (span x chunk), NOT file",
        "scorers": {"rule": "benchmark.rule_prob / adjudicate RULE_WEIGHTS",
                    "judge": ".codeguard/model.json (12-feature logistic regression, shipped)"},
        "curves": curves, "summary": summary,
        "curve_image": "eval_judge_curve.png",
        "honesty": ["file-level detection is 97% for both scorers",
                    "gate decision is made by corroboration rules, not by model confidence",
                    "do not present pair-level AUC as a detection-rate improvement"],
    }
    (out / "judge-ablation-20261115.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "judge-ablation-20261115.md").write_text(to_markdown(payload),
                                                    encoding="utf-8")
    make_plot(payload, out)
    print("pairs=%d (reported %d) rule_auc=%s judge_auc=%s | at 0.55 rule P=%s R=%s judge P=%s R=%s"
          % (len(rows), pairs_verified, summary["rule"]["auc"],
             summary["judge"]["auc"], summary["rule"]["at_prod"]["precision"],
             summary["rule"]["at_prod"]["recall"],
             summary["judge"]["at_prod"]["precision"],
             summary["judge"]["at_prod"]["recall"]))


if __name__ == "__main__":
    main()
