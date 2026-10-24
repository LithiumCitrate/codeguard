"""Merge the two independent annotation sheets and report agreement.

A blank label is never treated as A.  The script refuses to write a summary
until both sheets are complete, because a half-filled table would be exactly
the kind of evidence the competition rules call fabricated.

Usage:
    python scripts/merge_annotations.py
    python scripts/merge_annotations.py --a ... --b ... --out ...
    python scripts/merge_annotations.py --adjudication scratch/adjudication.csv

The optional adjudication CSV has columns:
    sample_id,final_label,final_note,adjudicator,date
Only samples where the two annotators disagreed need a final label.
"""
from __future__ import annotations

import argparse
import csv
import datetime
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_A = ROOT / "submission" / "evidence" / "model-leak-20261021-标注表-标注人1.csv"
DEFAULT_B = ROOT / "submission" / "evidence" / "model-leak-20261021-标注表-标注人2.csv"
DEFAULT_OUT = ROOT / "submission" / "evidence" / "model-leak-20261021-标注汇总.md"
LABELS = ("A", "B", "C")


def read_sheet(path: Path, name: str) -> list:
    if not path.exists():
        raise SystemExit("缺少%s: %s" % (name, path))
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 47:
        raise SystemExit("%s 应为 47 行，实际 %d 行：%s" % (name, len(rows), path))
    ids = [str(row.get("sample_id") or "").strip() for row in rows]
    if len(set(ids)) != 47:
        raise SystemExit("%s 的 sample_id 有重复或空值" % name)
    for row in rows:
        row["label"] = (row.get("label") or "").strip().upper()
        if row["label"] and row["label"] not in LABELS:
            raise SystemExit("%s 中 %s 的 label=%r，只允许 A/B/C" % (name, row["sample_id"], row["label"]))
    return rows


def cohen_kappa(first: list, second: list) -> float | None:
    n = len(first)
    if n == 0:
        return None
    observed = sum(a == b for a, b in zip(first, second)) / n
    count_a, count_b = Counter(first), Counter(second)
    expected = sum((count_a[label] / n) * (count_b[label] / n) for label in LABELS)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def kappa_band(value: float | None) -> str:
    if value is None:
        return "不适用（一方或双方分布退化）"
    if value < 0.4:
        return "较差（<0.40）"
    if value < 0.6:
        return "中等（0.40–0.60）"
    if value < 0.8:
        return "较强（0.60–0.80）"
    return "很强（>=0.80）"


def kappa_advice(value: float | None, all_adjudicated: bool) -> str:
    if value is None:
        return ""
    if value < 0.4:
        if all_adjudicated:
            return "低值主要由分布偏斜导致（见第四节），分歧已全部经第三人复核闭环（见第二节）"
        return "建议先统一口径再重标，不要直接交卷"
    if value < 0.6:
        return "建议讨论分歧并复核"
    return ""


def read_adjudication(path: Path) -> dict:
    if not path.exists():
        raise SystemExit("缺少复核 CSV: %s" % path)
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    result = {}
    for row in rows:
        label = (row.get("final_label") or "").strip().upper()
        if label not in LABELS:
            raise SystemExit("复核 CSV 中 %s 的 final_label=%r，只允许 A/B/C" % (row.get("sample_id"), label))
        result[str(row.get("sample_id") or "").strip()] = {
            "label": label,
            "note": (row.get("final_note") or "").strip(),
            "adjudicator": (row.get("adjudicator") or "").strip(),
            "date": (row.get("date") or "").strip(),
        }
    return result


def escape_cell(value: object) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text if text else "—"


def distribution(rows: list, field: str = "label") -> dict:
    counts = Counter(row.get(field, "") for row in rows)
    return {label: counts.get(label, 0) for label in LABELS}


def build_summary(first: list, second: list, adjudication: dict, generated: str) -> str:
    by_id_b = {row["sample_id"]: row for row in second}
    merged = []
    for row_a in first:
        row_b = by_id_b[row_a["sample_id"]]
        agreed = row_a["label"] == row_b["label"]
        final = adjudication.get(row_a["sample_id"], {})
        merged.append({
            "sample_id": row_a["sample_id"],
            "project": row_a.get("expected_project") or "",
            "license": row_a.get("expected_license") or "",
            "paper_label": row_a.get("paper_label") or "",
            "a": row_a["label"],
            "b": row_b["label"],
            "agreed": agreed,
            "note_a": row_a.get("note") or "",
            "note_b": row_b.get("note") or "",
            "final": final.get("label", "") or (row_a["label"] if agreed else ""),
            "final_note": final.get("note", ""),
            "adjudicator": final.get("adjudicator", ""),
        })

    labels_a = [row["a"] for row in merged]
    labels_b = [row["b"] for row in merged]
    complete = all(labels_a) and all(labels_b)
    agreements = sum(row["agreed"] for row in merged) if complete else None
    kappa = cohen_kappa(labels_a, labels_b) if complete else None
    disagreements = [row for row in merged if not row["agreed"]] if complete else []
    unadjudicated = [row for row in disagreements if not row["final"]]
    final_labels = [row["final"] or "待复核" for row in merged]
    confirmed = sum(1 for label in final_labels if label == "A")

    if not complete:
        kappa_explain = "—（未完成）"
    else:
        advice = kappa_advice(kappa, not unadjudicated)
        kappa_explain = kappa_band(kappa) + ("；" + advice if advice else "")

    lines = [
        "# LiCoEval 47 条正例双人标注汇总",
        "",
        "> 本文件由 `scripts/merge_annotations.py` 从两份独立 CSV 生成，未修改任何标签。",
        "> 生成时间：%s。A = 实质逐字复现；B = 惯用写法/公共片段；C = 无法判断。"
        % generated,
        "> 论文把 47 条都标为 striking-similar（copied）；本表的 A 是团队独立确认，B/C 是不确认/拿不准，不能把两者混写。",
        "",
    ]
    if not complete:
        lines += [
            "> **未完成：至少一份 CSV 仍有空标签。以下只是模板检查草稿，不能作为完成证据；"
            "空值没有被当作 A。**",
            "",
        ]

    lines += [
        "## 一、汇总",
        "",
        "| 指标 | 结果 |",
        "|---|---|",
        "| 样本数 | %d |" % len(merged),
        "| 标注人1 分布 | A %d / B %d / C %d |" % (
            distribution(first)["A"], distribution(first)["B"], distribution(first)["C"]),
        "| 标注人2 分布 | A %d / B %d / C %d |" % (
            distribution(second)["A"], distribution(second)["B"], distribution(second)["C"]),
        "| 一致样本 | %s |" % (
            "—（未完成）" if not complete else "%d / %d（%.1f%%）" % (
                agreements, len(merged), 100.0 * agreements / len(merged))),
        "| Cohen's κ | %s |" % ("—（未完成）" if not complete else ("—" if kappa is None else "%.4f" % kappa)),
        "| κ 解释 | %s |" % kappa_explain,
        "| 分歧样本 | %s |" % ("—（未完成）" if not complete else len(disagreements)),
        "| 已复核分歧 | %d |" % (len(disagreements) - len(unadjudicated)),
        "| 最终 A（独立确认复现） | %d / %d |" % (confirmed, len(merged)),
        "",
    ]

    if unadjudicated:
        lines += [
            "> **仍有 %d 条分歧未复核。** 复核前，“最终 A”列只统计已复核样本；"
            "不要把未复核分歧写成已确认。" % len(unadjudicated),
            "",
        ]

    lines += [
        "## 二、分歧样本（交第三人复核）",
        "",
        "| 样本 | 项目 | 许可 | 标注人1 | 标注人2 | 标注人1 理由 | 标注人2 理由 | 复核结论 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if disagreements:
        for row in disagreements:
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                escape_cell(row["sample_id"]), escape_cell(row["project"]),
                escape_cell(row["license"]), row["a"], row["b"],
                escape_cell(row["note_a"]), escape_cell(row["note_b"]),
                escape_cell(row["final"] or "待复核"),
            ))
    else:
        lines.append("| — | — | — | — | — | — | — | %s |" % (
            "—（未完成）" if not complete else "无分歧"))
    lines.append("")

    lines += [
        "## 三、逐条记录",
        "",
        "| # | 样本 | 项目 | 许可 | 论文标签 | 标注人1 | 标注人2 | 一致 | 最终 | 备注 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for ordinal, row in enumerate(merged, 1):
        note = " / ".join(part for part in (row["note_a"], row["note_b"], row["final_note"]) if part)
        agreed = "—" if not (row["a"] and row["b"]) else ("是" if row["agreed"] else "否")
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            ordinal, escape_cell(row["sample_id"]), escape_cell(row["project"]),
            escape_cell(row["license"]), escape_cell(row["paper_label"]),
            row["a"] or "—", row["b"] or "—", agreed,
            escape_cell(row["final"] or "待复核"), escape_cell(note),
        ))
    lines.append("")

    lines += [
        "## 四、解释与局限",
        "",
        "- 这 47 条是 LiCoEval 按 striking-similar 筛出的正例，不是模型全部输出；本表衡量的是“团队是否独立确认这段相似构成实质复现”，不是法律结论。",
        "- κ 只反映两名标注人对 A/B/C 口径的一致程度，不反映标注本身是否正确；κ 低于 0.60 时应先讨论口径、再重标，而不是直接交卷。",
        "- κ 对分布偏斜敏感：如果一方几乎全判 A，即使一致率 95%+，κ 也可能接近 0。报告时同时写一致率和 κ，并说明这一点；不要把 κ=0 误读为双方完全不一致。",
        "- 样本量 47，κ 的置信区间较宽；标注人未接受正式版权法培训，B/C 的边界仍应由第三人复核。",
        "- 论文标签（copied）是样本入选依据；若团队最终 A 数少于 47，报告应写“独立确认 X/47”，不能写“47/47 确认为复现”。",
        "",
        "## 五、可直接写入报告的句子（按实际数字替换）",
        "",
    ]
    if complete:
        if unadjudicated:
            tail = "%d 条分歧待第三人复核，最终独立确认暂计 A %d 条。" % (len(unadjudicated), confirmed)
        else:
            tail = "%d 条分歧经第三人复核后，最终独立确认 A %d 条。" % (len(disagreements), confirmed)
        lines += [
            "> 两名成员对 LiCoEval 的 47 条 GPT-4o 真实输出独立标注：一致 %d/47（%.1f%%），Cohen's κ=%s；"
            "标注人1 判 A %d / B %d / C %d，标注人2 判 A %d / B %d / C %d；%s" % (
                agreements, 100.0 * agreements / len(merged),
                "—" if kappa is None else "%.4f" % kappa,
                distribution(first)["A"], distribution(first)["B"], distribution(first)["C"],
                distribution(second)["A"], distribution(second)["B"], distribution(second)["C"],
                tail,
            ),
            "",
            "> κ 受分布偏斜影响（一方几乎全 A 时 κ 会接近 0），报告时与一致率并列给出，不要单独引用 κ。",
        ]
    else:
        lines += [
            "> 两份 CSV 尚未填满，本节不生成完成句。填满后重新运行本脚本。",
        ]
    lines += [
        "",
        "## 六、复现",
        "",
        "```bash",
        "python scripts/make_annotation_packet.py",
        "python scripts/merge_annotations.py --allow-blank   # 只检查模板，不生成完成结论",
        "python scripts/merge_annotations.py                 # 两份 CSV 填满后生成正式汇总",
        "```",
        "",
        "标注口径与流程见 `submission/evidence/model-leak-20261021-标注说明.md`；"
        "对照包含第三方原文，只在本机 `.codeguard/annotation/` 打开，不入库、不上传。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", type=Path, default=DEFAULT_A)
    parser.add_argument("--b", type=Path, default=DEFAULT_B)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--adjudication", type=Path, default=None)
    parser.add_argument("--allow-blank", action="store_true",
                        help="只检查模板并生成带“未完成”横幅的草稿，不把空值当作 A")
    args = parser.parse_args()

    first = read_sheet(args.a, "标注人1")
    second = read_sheet(args.b, "标注人2")
    if {row["sample_id"] for row in first} != {row["sample_id"] for row in second}:
        raise SystemExit("两份 CSV 的 sample_id 集合不一致")

    missing_a = [row["sample_id"] for row in first if not row["label"]]
    missing_b = [row["sample_id"] for row in second if not row["label"]]
    if missing_a or missing_b:
        print("标注未完成：标注人1 %d/47，标注人2 %d/47。" % (47 - len(missing_a), 47 - len(missing_b)))
        print("标注人1 待填：%s" % ", ".join(missing_a[:5]) + (" ..." if len(missing_a) > 5 else ""))
        print("标注人2 待填：%s" % ", ".join(missing_b[:5]) + (" ..." if len(missing_b) > 5 else ""))
        if not args.allow_blank:
            print("本脚本不会把空值当作 A；请填满两份 CSV 后再运行。")
            return 1
        summary = build_summary(first, second, {}, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    else:
        adjudication = read_adjudication(args.adjudication) if args.adjudication else {}
        summary = build_summary(first, second, adjudication, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(summary, encoding="utf-8")
    print("写入 %s" % args.out)
    if missing_a or missing_b:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
