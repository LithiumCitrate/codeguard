"""Build the blind annotation packet for the 47 LiCoEval positives.

The packet puts the GPT-4o answer next to the paper's paired original and the
CodeGuard findings, so two annotators can independently label A/B/C without
searching the dataset by hand.  It is written to ``.codeguard/annotation/``
(gitignored): LiCoEval is AGPL-3.0-or-later and its source text must not enter
the repository.  The two CSVs under ``submission/evidence/`` contain only
sample IDs, licences and metrics; labels start blank and are preserved when
the generator is re-run after an annotator has filled them.

Usage:
    python scripts/make_annotation_packet.py
    python scripts/make_annotation_packet.py --out .codeguard/annotation
"""
from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "submission" / "evidence" / "model-leak-20261021.json"
DATASET = ROOT / ".codeguard" / "external" / "licoeval" / "gpt-4o_striking_sim.json"
DEFAULT_OUT = ROOT / ".codeguard" / "annotation"

CSV_COLUMNS = [
    "sample_id", "expected_project", "expected_license", "paper_bleu",
    "paper_jaccard", "paper_label", "codeguard_max_risk",
    "codeguard_verbatim", "codeguard_coverage", "codeguard_attributed",
    "codeguard_matched_packages", "label", "note", "annotator", "date",
]
RISK_ORDER = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "S4": 4}
LICENSE_DISPLAY = {
    "apache-2.0": "Apache-2.0",
    "bsd-3-clause": "BSD-3-Clause",
    "gpl-3.0-or-later": "GPL-3.0-or-later",
    "mit": "MIT",
    "mpl-2.0": "MPL-2.0",
}
LABEL_HELP = {
    "A": "实质逐字复现：连续、非平凡的实现被复制（通常 >=20 token，或 >=10 token 且覆盖率高）；改名/改格式不影响。",
    "B": "惯用写法/公共片段：imports、argparse、异常处理、常量表、短签名/文档字符串、通用算法骨架；没有实质表达被复制。",
    "C": "无法判断：片段过短、边界不清、原文本身过于通用，或需要第三人复核。",
}


def load_json(path: Path) -> object:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def source_text(record: dict) -> str:
    """The same text the evaluator indexed: licence notice + header + body."""
    parts = []
    for field in ("init_header", "header", "body"):
        chunk = (record.get(field) or "").replace("\r\n", "\n").strip("\n")
        if chunk:
            parts.append(chunk)
    return "\n".join(parts) + ("\n" if parts else "")


def build_dataset_index(records: dict) -> dict:
    index = {}
    for key, record in records.items():
        index.setdefault(key[:12], (key, record))
    return index


def finding_summary(sample: dict) -> tuple:
    findings = sample.get("findings") or []
    risk = "S0"
    for item in findings:
        candidate = str(item.get("risk") or "S0")
        if RISK_ORDER.get(candidate, 0) > RISK_ORDER.get(risk, 0):
            risk = candidate
    verbatim = max((int(item.get("verbatim_run") or 0) for item in findings), default=0)
    coverage = max((float(item.get("coverage") or 0.0) for item in findings), default=0.0)
    packages = sorted({str(item.get("package")) for item in findings if item.get("package")})
    return risk, verbatim, coverage, packages


def matching_blocks(answer: str, source: str, minimum: int = 20) -> tuple:
    """Exact common blocks as two independent index lists.

    The answer and the source have different offsets, so each side gets its
    own (start, end) list; reusing the answer offsets on the source would
    highlight the wrong lines.  Whitespace-only blocks are ignored.
    """
    matcher = difflib.SequenceMatcher(None, answer, source, autojunk=False)
    answer_blocks, source_blocks = [], []
    for block in matcher.get_matching_blocks():
        if block.size < minimum:
            continue
        if not answer[block.a:block.a + block.size].strip():
            continue
        answer_blocks.append((block.a, block.a + block.size))
        source_blocks.append((block.b, block.b + block.size))
    return answer_blocks, source_blocks


def mark_html(text: str, blocks: list) -> str:
    out = []
    cursor = 0
    for start, end in blocks:
        out.append(html.escape(text[cursor:start]))
        out.append("<mark>" + html.escape(text[start:end]) + "</mark>")
        cursor = end
    out.append(html.escape(text[cursor:]))
    return "".join(out)


def rows_from_evidence(evidence: dict, records: dict) -> list:
    index = build_dataset_index(records)
    rows = []
    missing = []
    for sample in evidence["samples"]:
        sample_id = str(sample["id"]).removeprefix("leak-")
        pair = index.get(sample_id[:12])
        if pair is None:
            missing.append(sample_id)
            continue
        key, record = pair
        risk, verbatim, coverage, packages = finding_summary(sample)
        answer = (record.get("answer") or "").replace("\r\n", "\n")
        source = source_text(record)
        rows.append({
            "sample_id": sample_id,
            "expected_project": record.get("project") or "",
            "expected_license": LICENSE_DISPLAY.get(
                str(record.get("license") or "").lower(), record.get("license") or ""),
            "paper_bleu": round(float(record.get("bleu") or 0.0), 4),
            "paper_jaccard": round(float(record.get("jaccard") or 0.0), 4),
            "paper_label": "copied (paper)",
            "codeguard_max_risk": risk,
            "codeguard_verbatim": verbatim,
            "codeguard_coverage": round(coverage, 4),
            "codeguard_attributed": "是" if sample.get("attributed") else "否",
            "codeguard_matched_packages": "; ".join(packages),
            "label": "",
            "note": "",
            "annotator": "",
            "date": "",
            "_key": key,
            "_record": record,
            "_answer": answer,
            "_source": source,
            "_findings": sample.get("findings") or [],
        })
    if missing:
        raise SystemExit("数据集里找不到这些样本的原文: %s" % ", ".join(missing))
    rows.sort(key=lambda row: (row["expected_project"], row["sample_id"]))
    return rows


def read_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return {}
    return {str(row.get("sample_id") or "").strip(): row
            for row in rows if str(row.get("sample_id") or "").strip()}


def write_csv(path: Path, rows: list, annotator: str) -> None:
    """Regenerate objective columns without wiping labels already filled in."""
    existing = read_existing(path)
    preserved = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            clean = {key: row.get(key, "") for key in CSV_COLUMNS}
            clean["annotator"] = annotator
            old = existing.get(row["sample_id"])
            if old:
                for field in ("label", "note", "date"):
                    value = (old.get(field) or "").strip()
                    if value:
                        clean[field] = value
                        if field == "label":
                            preserved += 1
                if (old.get("annotator") or "").strip():
                    clean["annotator"] = old["annotator"]
            writer.writerow(clean)
    if preserved:
        print("保留 %s 中已有的 %d 个 label（以及理由/日期/标注人）。" % (path.name, preserved))


def badge(text: str, css: str = "") -> str:
    return '<span class="badge %s">%s</span>' % (css, html.escape(str(text)))


def render_card(ordinal: int, row: dict) -> str:
    answer_blocks, source_blocks = matching_blocks(row["_answer"], row["_source"])
    answer = mark_html(row["_answer"], answer_blocks)
    source = mark_html(row["_source"], source_blocks)
    findings = row["_findings"]
    finding_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            html.escape(str(item.get("package") or "")),
            html.escape(str(item.get("path") or "")),
            html.escape(str(item.get("license") or "")),
            html.escape(str(item.get("risk") or "")),
            html.escape("%.4f" % float(item.get("confidence") or 0.0)),
            html.escape(str(item.get("verbatim_run") or 0)),
        )
        for item in findings
    )
    risk_css = "risk-high" if row["codeguard_max_risk"] in ("S3", "S4") else "risk-low"
    return f"""
<section class="sample" id="s-{html.escape(row['sample_id'])}">
  <h2>#{ordinal:02d} <code>{html.escape(row['sample_id'])}</code>
    {badge(row['expected_license'])}
    {badge(row['codeguard_max_risk'], risk_css)}
    {badge('归属正确' if row['codeguard_attributed'] == '是' else '归属其它副本')}
  </h2>
  <table class="meta">
    <tr><th>论文配对项目</th><td>{html.escape(row['expected_project'])}</td>
        <th>论文 BLEU / Jaccard</th><td>{row['paper_bleu']} / {row['paper_jaccard']}</td></tr>
    <tr><th>论文标签</th><td>{html.escape(row['paper_label'])}</td>
        <th>CodeGuard 逐字 / 覆盖率</th><td>{row['codeguard_verbatim']} token / {row['codeguard_coverage']}</td></tr>
    <tr><th>签名</th><td colspan="3"><code>{html.escape(str(row['_record'].get('signature') or ''))}</code></td></tr>
  </table>
  <p class="hint">黄色高亮 = 两段文本中 &gt;=20 字符的相同片段，仅用于定位；不是给你的结论。</p>
  <div class="grid">
    <div><h3>GPT-4o 回答</h3><pre>{answer}</pre></div>
    <div><h3>论文配对的原文（init_header + header + body）</h3><pre>{source}</pre></div>
  </div>
  <details>
    <summary>CodeGuard 实际命中（系统读数，仅供背景）</summary>
    <table class="findings">
      <tr><th>项目</th><th>路径</th><th>许可</th><th>风险</th><th>置信度</th><th>逐字</th></tr>
      {finding_rows or '<tr><td colspan="6">无命中</td></tr>'}
    </table>
  </details>
  <p class="todo">在 CSV 的 <code>label</code> 列填 <b>A</b>/<b>B</b>/<b>C</b>；B、C 或拿不准的 A 请在 <code>note</code> 写一句理由。</p>
</section>
"""


def build_packet(rows: list, annotator: str) -> str:
    toc = "".join(
        '<a href="#s-%s">%02d %s</a>' % (html.escape(row["sample_id"]), ordinal, html.escape(row["sample_id"]))
        for ordinal, row in enumerate(rows, 1)
    )
    cards = "".join(render_card(ordinal, row) for ordinal, row in enumerate(rows, 1))
    generated = time.strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CodeGuard 47 条正例盲标对照包 · {annotator}</title>
<style>
  :root {{ --ink:#111; --muted:#5b6470; --line:#d9dee5; --paper:#fbfbf8; --accent:#f3c400; --warn:#b42318; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.55 "Segoe UI", "Microsoft YaHei", sans-serif; }}
  header {{ padding:28px 36px 20px; border-bottom:3px solid var(--ink); background:#fff; }}
  h1 {{ margin:0 0 6px; font-size:28px; letter-spacing:.02em; }}
  h2 {{ margin:0 0 10px; font-size:18px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  h3 {{ margin:0 0 6px; font-size:14px; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }}
  code {{ font-family: Consolas, "Cascadia Code", monospace; font-size:.92em; }}
  .sub {{ color:var(--muted); margin:0; }}
  .warn {{ border-left:4px solid var(--warn); padding:10px 14px; background:#fff4f2; margin:14px 0 0; }}
  .criteria {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:16px 0 0; }}
  .criteria div {{ border:1px solid var(--line); padding:10px 12px; background:#fff; }}
  .criteria b {{ display:block; margin-bottom:4px; }}
  nav {{ padding:14px 36px; background:#111; color:#fff; display:flex; flex-wrap:wrap; gap:6px 12px; font-size:12px; }}
  nav a {{ color:#f3c400; text-decoration:none; }}
  main {{ padding:26px 36px 60px; max-width:1600px; margin:0 auto; }}
  .sample {{ background:#fff; border:1px solid var(--line); padding:20px 22px; margin:0 0 22px; page-break-inside:avoid; }}
  .meta {{ width:100%; border-collapse:collapse; margin:0 0 12px; font-size:13px; }}
  .meta th, .meta td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }}
  .meta th {{ background:#f3f5f7; width:16%; font-weight:600; }}
  .badge {{ display:inline-block; border:1px solid var(--ink); padding:1px 7px; font-size:11px; font-weight:700; letter-spacing:.03em; background:#fff; }}
  .risk-high {{ background:#ffe1dc; border-color:var(--warn); color:var(--warn); }}
  .risk-low {{ background:#e9f7ef; border-color:#1c7c4a; color:#1c7c4a; }}
  .hint {{ color:var(--muted); font-size:12px; margin:0 0 10px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  pre {{ margin:0; padding:12px; background:#0f1419; color:#e6edf3; overflow:auto; max-height:520px; font:12px/1.5 Consolas, "Cascadia Code", monospace; white-space:pre; }}
  mark {{ background:var(--accent); color:#111; padding:0; }}
  details {{ margin-top:12px; }}
  summary {{ cursor:pointer; color:var(--muted); }}
  .findings {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:12px; }}
  .findings th, .findings td {{ border:1px solid var(--line); padding:5px 7px; text-align:left; }}
  .todo {{ margin:12px 0 0; font-size:13px; border-top:1px dashed var(--line); padding-top:10px; }}
  footer {{ padding:20px 36px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); }}
  @media (max-width: 900px) {{ .grid, .criteria {{ grid-template-columns:1fr; }} main, header, nav, footer {{ padding-left:18px; padding-right:18px; }} }}
  @media print {{ nav {{ display:none; }} .sample {{ border:0; page-break-after:always; }} pre {{ max-height:none; background:#fff; color:#111; border:1px solid #ccc; }} }}
</style>
<body>
<header>
  <h1>47 条 LiCoEval 正例 · 双人盲标对照包</h1>
  <p class="sub">标注人：<b>{html.escape(annotator)}</b> · 生成：{generated} · 样本：{len(rows)} 条 · 来源：LiCoEval（ICSE 2025，AGPL-3.0-or-later）</p>
  <div class="criteria">
    <div><b>A · 实质逐字复现</b>{LABEL_HELP['A']}</div>
    <div><b>B · 惯用写法/公共片段</b>{LABEL_HELP['B']}</div>
    <div><b>C · 无法判断</b>{LABEL_HELP['C']}</div>
  </div>
  <p class="warn"><b>独立标注：</b>只看自己的对照包和 CSV，不与他人讨论答案。论文标签是样本入选依据，不是你的结论；
  高亮和 CodeGuard 读数只是定位提示，不能代替你的判断。<br>
  <b>许可与隐私：</b>本文件含第三方原文与模型输出，只在本机 <code>.codeguard/annotation/</code> 打开；
  不要上传、截图或粘贴进参赛材料。CSV 只保留标签、理由和签名，不要粘贴源码。</p>
</header>
<nav>{toc}</nav>
<main>{cards}</main>
<footer>CodeGuard 标注工具 · 生成脚本 scripts/make_annotation_packet.py · 本文件不入库（.codeguard/ 已 gitignore）</footer>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not EVIDENCE.exists():
        raise SystemExit("缺少评测证据: %s" % EVIDENCE)
    if not DATASET.exists():
        raise SystemExit(
            "缺少 LiCoEval 缓存: %s\n先运行 python scripts/eval_model_leak.py 获取并校验数据集。" % DATASET
        )

    evidence = load_json(EVIDENCE)
    records = load_json(DATASET)
    if len(records) != 47:
        raise SystemExit("LiCoEval 缓存应为 47 条，实际 %d 条" % len(records))
    rows = rows_from_evidence(evidence, records)
    if len(rows) != 47:
        raise SystemExit("证据应为 47 条，实际 %d 条" % len(rows))

    args.out.mkdir(parents=True, exist_ok=True)
    csv_a = ROOT / "submission" / "evidence" / "model-leak-20261021-标注表-标注人1.csv"
    csv_b = ROOT / "submission" / "evidence" / "model-leak-20261021-标注表-标注人2.csv"
    write_csv(csv_a, rows, "标注人1")
    write_csv(csv_b, rows, "标注人2")

    for number, annotator in ((1, "标注人1"), (2, "标注人2")):
        path = args.out / ("packet-annotator%d.html" % number)
        path.write_text(build_packet(rows, annotator), encoding="utf-8")
        print("写入 %s" % path)

    print("写入 %s" % csv_a)
    print("写入 %s" % csv_b)
    print("共 %d 条；两份 CSV 的 label/note 列留空，由标注人独立填写。" % len(rows))
    print("下一步：")
    print("  1. 两位标注人分别打开自己的 packet-annotatorN.html，独立填写自己的 CSV；")
    print("  2. 填完后运行 python scripts/merge_annotations.py；")
    print("  3. 不一致样本交第三人复核，复核结果填进 merge 输出的“复核结论”列。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
