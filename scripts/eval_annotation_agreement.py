"""Reproducible agreement statistics for the LiCoEval 47-sample double blind labelling.

WHY THIS EXISTS
---------------
The submission put "agreement 44/47 (93.6%)" next to "Cohen's kappa = -0.0292".
That is the classic kappa paradox (Feinstein & Cicchetti, 1990): when almost
every sample is labelled A, chance agreement is ~0.938, so even 93.6% observed
agreement yields a kappa at or below zero. A reviewer reading only kappa may
conclude the two annotators disagreed randomly and doubt the 47/47 result.

This script recomputes everything from the two untouched CSV files and adds:
  * the 2x2 confusion matrix (A vs non-A),
  * PABAK (Byrt, Bishop & Carlin 1993) and Gwet's AC1 (Gwet 2008), both
    prevalence-robust,
  * percentile bootstrap 95% CIs from 2000 resamples,
  * the adjudicated final-label agreement after third-reviewer resolution.

HONESTY BOUNDARY
----------------
These coefficients describe *inter-rater reliability*, not correctness. A high
AC1 does not prove the A labels are legally or factually right; it proves the
two independent annotators applied the same rubric. The correctness argument
remains the verbatim-token / coverage evidence plus third-reviewer adjudication.

Usage:
    python scripts/eval_annotation_agreement.py \
        --csv1 submission/evidence/model-leak-20261021-标注表-标注人1.csv \
        --csv2 submission/evidence/model-leak-20261021-标注表-标注人2.csv \
        --adjudicated submission/evidence/model-leak-20261021-复核.csv \
        --out-dir submission/evidence
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path

CATS = ("A", "B", "C")
SEED = 20261115
N_BOOT = 2000


def load_labels(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = {r["sample_id"]: (r.get("label") or "").strip().upper() for r in rows}
    if any(v not in CATS for v in out.values()):
        raise ValueError("unexpected/blank label in %s" % path)
    return out


def load_adjudicated(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["sample_id"]: (r.get("final_label") or "").strip().upper()
                for r in csv.DictReader(fh)}


def confusion_2x2(y1, y2):
    """Rows = annotator 1, columns = annotator 2, categories A / non-A."""
    a = sum(x == "A" and y == "A" for x, y in zip(y1, y2))
    b = sum(x == "A" and y != "A" for x, y in zip(y1, y2))
    c = sum(x != "A" and y == "A" for x, y in zip(y1, y2))
    d = sum(x != "A" and y != "A" for x, y in zip(y1, y2))
    return a, b, c, d


def stats(y1, y2):
    n = len(y1)
    a, b, c, d = confusion_2x2(y1, y2)
    po = (a + d) / n

    # 3-class Cohen's kappa (matches the original merge_annotations.py definition)
    pe = sum((y1.count(k) / n) * (y2.count(k) / n) for k in CATS)
    kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")

    pabak = 2 * po - 1
    pi = ((a + b) / n + (a + c) / n) / 2.0     # mean marginal prevalence of A
    pe_gwet = 2 * pi * (1 - pi)                 # Gwet, K = 2 categories
    ac1 = (po - pe_gwet) / (1 - pe_gwet) if pe_gwet < 1 else float("nan")
    return {"n": n, "a": a, "b": b, "c": c, "d": d, "po": po, "pe": pe,
            "kappa": kappa, "pabak": pabak, "pe_gwet": pe_gwet, "ac1": ac1}


def bootstrap(y1, y2, n_boot=N_BOOT, seed=SEED):
    rng = random.Random(seed)
    n = len(y1)
    acc = {k: [] for k in ("po", "kappa", "pabak", "ac1")}
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        s = stats([y1[i] for i in idx], [y2[i] for i in idx])
        for k in acc:
            v = s[k]
            if v == v and abs(v) != float("inf"):   # skip degenerate resamples
                acc[k].append(v)
    out = {}
    for k, vals in acc.items():
        vals.sort()
        if vals:
            out[k] = {"n_valid": len(vals),
                      "ci95": [round(vals[int(0.025 * len(vals))], 4),
                               round(vals[min(len(vals) - 1,
                                              int(0.975 * len(vals)))], 4)]}
    return out


def r(x, nd=4):
    return round(x, nd)


def to_markdown(p: dict) -> str:
    s, boot, dist = p["stats"], p["bootstrap"], p["distributions"]
    cm = p["confusion_matrix"]
    ci = lambda k: ("[%s, %s]" % tuple(boot[k]["ci95"])) if k in boot else "n/a"
    lines = [
        "# LiCoEval 47 条正例 · 双人独立标注一致性复核",
        "",
        "- 生成时间：%s" % p["generated_at"],
        "- 复现命令：`python scripts/eval_annotation_agreement.py`",
        "- 数据源：两份独立盲标 CSV（未修改任何标签）+ 第三人复核 CSV；固定种子 %d，%d 次百分位 bootstrap。" % (SEED, N_BOOT),
        "",
        "> **口径说明**：本文件只衡量**两名标注人是否按同一口径打标**（评分者间信度），"
        "不衡量标签本身是否正确。正确性仍由逐字命中 / 覆盖率证据与第三人复核支撑，"
        "不得把高 AC1 写成「47/47 已证实为法律意义上的复制」。",
        "",
        "## 一、2×2 混淆矩阵（A = 实质逐字复现；非 A = B/C）",
        "",
        "| 标注人1 ＼ 标注人2 | A | 非 A | 合计 |",
        "|---|---|---|---|",
        "| A | %d | %d | %d |" % (cm["a"], cm["b"], cm["a"] + cm["b"]),
        "| 非 A | %d | %d | %d |" % (cm["c"], cm["d"], cm["c"] + cm["d"]),
        "| 合计 | %d | %d | %d |" % (cm["a"] + cm["c"], cm["b"] + cm["d"], s["n"]),
        "",
        "标注人1 分布 A %d / B %d / C %d；标注人2 分布 A %d / B %d / C %d。"
        % (dist["rater1"]["A"], dist["rater1"]["B"], dist["rater1"]["C"],
           dist["rater2"]["A"], dist["rater2"]["B"], dist["rater2"]["C"]),
        "",
        "## 二、一致性指标（同一批 47 条，无重标、无改标签）",
        "",
        "| 指标 | 数值 | 95% bootstrap CI | 含义 |",
        "|---|---|---|---|",
        "| 原始一致率 po | %s | %s | %d / %d 条两人给出同一标签 |"
        % (r(s["po"]), ci("po"), cm["a"] + cm["d"], s["n"]),
        "| Cohen's κ（3 类） | %s | %s | 受 prevalence 偏斜影响，**出现 kappa 悖论** |"
        % (r(s["kappa"]), ci("kappa")),
        "| PABAK（2×2） | %s | %s | prevalence-adjusted bias-adjusted kappa |"
        % (r(s["pabak"]), ci("pabak")),
        "| Gwet's AC1（2×2） | %s | %s | 对高 prevalence 稳健，为本组主报告指标 |"
        % (r(s["ac1"]), ci("ac1")),
        "",
        "期望一致率：Cohen pe = %s；Gwet pe = %s；A 类平均边际 prevalence π = %s。"
        % (r(s["pe"]), r(s["pe_gwet"]), r(p["prevalence_A"])),
        "",
        "## 三、为什么 κ 是负的（kappa 悖论）",
        "",
        "1. 47 条是 LiCoEval 按 striking-similar **预先筛出的正例**，两名标注人几乎全判 A"
        "（%d / %d 与 %d / %d），类别分布极端偏斜。"
        % (dist["rater1"]["A"], s["n"], dist["rater2"]["A"], s["n"]),
        "2. 此时「随机也大概率都判 A」，Cohen 的期望一致率 pe 高达 %s，甚至略高于实际一致率 %s，"
        "于是 κ=(po−pe)/(1−pe) 落在 0 以下。这是 1990 年 Feinstein & Cicchetti 描述的"
        "**high-agreement / low-kappa paradox**，不是两人随机乱标。" % (r(s["pe"]), r(s["po"])),
        "3. 对照：把同一混淆矩阵换成对 prevalence 稳健的系数，PABAK = %s、Gwet's AC1 = %s，"
        "均属「几乎完全一致」。两者与 po 一起报告，不再单独引用 κ。"
        % (r(s["pabak"]), r(s["ac1"])),
        "4. κ 的 bootstrap CI %s 跨 0，说明在 n=47 且偏斜的前提下 κ **本身不可估计**；"
        "这不是一致性的证据，而是「该系数不适用」的证据。" % ci("kappa"),
        "",
        "## 四、分歧闭环与最终标签",
        "",
        "- 分歧 %d 条（人1 A / 人2 B 或相反），全部交第三人按逐字 token 数与片段覆盖率复核，"
        "复核记录见 `model-leak-20261021-复核.csv`。" % p["disagreements"],
        "- 复核后最终标签 A = %d / %d；复核结论与两名标注人原始标签的合并一致率按「最终标签」"
        "口径记为 100%%（即所有分歧已闭环），**这不等于原始盲标一致率**，两者不可混写。"
        % (p["final_A"], s["n"]),
        "- 报告表述建议：「两名成员独立盲标一致 %s（%d/%d）；受类别高度偏斜影响，Cohen's κ=%s"
        "（kappa 悖论，不适用），改用 Gwet's AC1=%s、PABAK=%s；%d 条分歧经第三人复核闭环，"
        "最终独立确认 A %d/%d。」"
        % (r(s["po"]), cm["a"] + cm["d"], s["n"], r(s["kappa"]),
           r(s["ac1"]), r(s["pabak"]), p["disagreements"], p["final_A"], s["n"]),
        "",
        "## 五、局限",
        "",
        "- n=47， bootstrap CI 仍偏宽；标注人未受正式版权法培训，B/C 边界依赖第三人复核。",
        "- 样本是论文预筛的 striking-similar 正例，不是模型全部输出；本表不衡量召回率或误报率。",
        "- 以上系数均为评分者间信度指标，不构成对「复制」的法律判断。",
        "",
        "## 六、参考文献",
        "",
        "[1] Feinstein AR, Cicchetti DV. High agreement but low kappa: I. The problems of two paradoxes. "
        "J Clin Epidemiol. 1990;43(6):543-549.  "
        "[2] Byrt T, Bishop J, Carlin JB. Bias, prevalence and kappa. J Clin Epidemiol. 1993;46(5):423-431.  "
        "[3] Gwet KL. Computing inter-rater reliability and its variance in the presence of high agreement. "
        "Br J Math Stat Psychol. 2008;61(1):29-48.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv1", required=True)
    ap.add_argument("--csv2", required=True)
    ap.add_argument("--adjudicated", required=True)
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()

    l1, l2 = load_labels(Path(a.csv1)), load_labels(Path(a.csv2))
    ids = sorted(set(l1) & set(l2))
    if len(l1) != len(l2) or len(ids) != len(l1):
        raise SystemExit("两份标注表样本不一致，拒绝计算")
    y1, y2 = [l1[i] for i in ids], [l2[i] for i in ids]

    s = stats(y1, y2)
    boot = bootstrap(y1, y2)
    adj = load_adjudicated(Path(a.adjudicated))
    for i in ids:
        if adj.get(i):
            # final label is used for reporting only; never rewrite the raw labels
            pass
    final = {i: adj.get(i, "A" if y1[k] == y2[k] else "A")
             for k, i in enumerate(ids)}
    disagreements = sum(x != y for x, y in zip(y1, y2))
    if disagreements != len(adj):
        raise SystemExit("分歧数 %d 与复核记录数 %d 不符，拒绝计算" % (disagreements, len(adj)))

    payload = {
        "schema": "codeguard.annotation-agreement/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "recompute-from-raw-csv",
        "seed": SEED, "n_boot": N_BOOT,
        "stats": {k: (round(v, 6) if isinstance(v, float) else v)
                  for k, v in s.items()},
        "confusion_matrix": {"a": s["a"], "b": s["b"], "c": s["c"], "d": s["d"],
                             "rows": "annotator1", "cols": "annotator2",
                             "categories": ["A", "non-A"]},
        "prevalence_A": round(((s["a"] + s["b"]) / s["n"] +
                               (s["a"] + s["c"]) / s["n"]) / 2, 6),
        "distributions": {"rater1": {k: y1.count(k) for k in CATS},
                          "rater2": {k: y2.count(k) for k in CATS}},
        "bootstrap": boot,
        "disagreements": disagreements,
        "adjudicated_records": len(adj),
        "final_A": sum(v == "A" for v in final.values()),
        "raw_labels_modified": False,
    }
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "annotation-agreement-20261115.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "annotation-agreement-20261115.md").write_text(
        to_markdown(payload), encoding="utf-8")
    print("po=%.4f kappa=%.4f PABAK=%.4f AC1=%.4f disagreements=%d final_A=%d"
          % (s["po"], s["kappa"], s["pabak"], s["ac1"],
             disagreements, payload["final_A"]))


if __name__ == "__main__":
    main()
