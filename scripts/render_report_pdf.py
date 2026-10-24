"""Render the technical report from its markdown source into a submission PDF.

``create_submission_pdf.py`` keeps its own copy of the report text and writes
back over ``09-技术报告-升级版.md``, which is how the shipped PDF drifted away
from the markdown.  This renderer is the opposite: markdown is the single
source of truth, the PDF is a pure build artifact.

Usage:
    python scripts/render_report_pdf.py
    python scripts/render_report_pdf.py --src submission/09-技术报告-升级版.md \
        --out submission/CodeGuard-技术报告-v0.5.1.pdf
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = "C:/Windows/Fonts/simsun.ttc"
INK = colors.HexColor("#17303a")
MUTED = colors.HexColor("#4a5b66")
RULE = colors.HexColor("#c9d3da")
ACCENT = colors.HexColor("#007d72")


def register_font() -> str:
    pdfmetrics.registerFont(TTFont("CJK", FONT_PATH, subfontIndex=0))
    return "CJK"


def clean(text: str) -> str:
    """Strip inline markdown so reportlab only ever sees escaped plain text."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    return text.strip()


def styles(font: str) -> dict:
    return {
        "cover_kicker": ParagraphStyle("ck", fontName=font, fontSize=11, leading=16,
                                       textColor=MUTED, alignment=TA_CENTER, spaceAfter=4),
        "cover_title": ParagraphStyle("ct", fontName=font, fontSize=27, leading=36,
                                      textColor=INK, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6),
        "cover_sub": ParagraphStyle("cs", fontName=font, fontSize=12.5, leading=19,
                                    textColor=ACCENT, alignment=TA_CENTER, spaceAfter=10),
        "cover_meta": ParagraphStyle("cm", fontName=font, fontSize=10.5, leading=18,
                                     textColor=INK, alignment=TA_CENTER, spaceAfter=4),
        "h1": ParagraphStyle("h1", fontName=font, fontSize=15.5, leading=22, textColor=ACCENT,
                             spaceBefore=13, spaceAfter=7),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=11.5, leading=17, textColor=INK,
                             spaceBefore=9, spaceAfter=5),
        "body": ParagraphStyle("b", fontName=font, fontSize=9.4, leading=14.2, textColor=INK,
                               spaceAfter=6, wordWrap="CJK"),
        "quote": ParagraphStyle("q", fontName=font, fontSize=8.9, leading=13.4, textColor=MUTED,
                                leftIndent=9, spaceAfter=5, wordWrap="CJK"),
        "bullet": ParagraphStyle("bl", fontName=font, fontSize=9.4, leading=14.2, textColor=INK,
                                 leftIndent=13, bulletIndent=3, spaceAfter=3, wordWrap="CJK"),
        "code": ParagraphStyle("c", fontName=font, fontSize=8.2, leading=12, textColor=MUTED,
                               leftIndent=9, spaceAfter=5, wordWrap="CJK"),
        "cell": ParagraphStyle("tc", fontName=font, fontSize=7.6, leading=10.4, textColor=INK,
                               wordWrap="CJK"),
        "cellhead": ParagraphStyle("th", fontName=font, fontSize=7.8, leading=10.6,
                                   textColor=colors.white, wordWrap="CJK"),
    }


def split_row(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    return bool(re.match(r"^\|?[\s:|-]+\|?$", line.strip())) and "-" in line


def column_widths(rows: list, total: float) -> list:
    cols = max(len(r) for r in rows)
    weights = []
    for c in range(cols):
        longest = max(len(r[c]) if c < len(r) else 0 for r in rows)
        weights.append(min(max(longest, 6), 46) ** 0.72)
    scale = total / sum(weights)
    return [w * scale for w in weights]


def make_table(rows: list, st: dict, total: float):
    widths = column_widths(rows, total)
    body = [[Paragraph(clean(cell), st["cellhead"] if i == 0 else st["cell"])
             for i, cell in enumerate(row)] for i, row in enumerate(rows)]
    for row in body[1:]:
        while len(row) < len(widths):
            row.append(Paragraph("", st["cell"]))
    table = Table(body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f8")]),
    ]))
    return table


def build(story: list, st: dict, text: str, total: float) -> None:
    lines = text.split("\n")
    idx = 0
    cover_done = False
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            idx += 1
            continue
        if stripped.startswith("```"):
            buf = []
            idx += 1
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                buf.append(lines[idx])
                idx += 1
            idx += 1
            story.append(Paragraph("\n".join(buf).replace("&", "&amp;").replace("<", "&lt;")
                                   .replace(">", "&gt;"), st["code"]))
            continue
        if stripped.startswith("|"):
            rows = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                row = lines[idx].strip()
                if not is_separator(row):
                    rows.append(split_row(row))
                idx += 1
            if rows:
                story.append(make_table(rows, st, total))
                story.append(Spacer(1, 5))
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(clean(stripped[4:]), st["h2"]))
            cover_done = True
        elif stripped.startswith("## ") or re.match(r"^#\s", stripped):
            text_head = re.sub(r"^#+\s*", "", stripped)
            story.append(Paragraph(clean(text_head), st["h1"]))
            cover_done = True
        elif stripped.startswith("> "):
            story.append(Paragraph(clean(stripped[2:]), st["quote"]))
        elif re.match(r"^[-*]\s+", stripped):
            story.append(Paragraph(clean(re.sub(r"^[-*]\s+", "", stripped)),
                                   st["bullet"], bulletText="·"))
        elif not cover_done and idx < 14:
            # cover block: kicker / title / subtitle / meta lines
            if idx == 0:
                story.append(Spacer(1, 46))
                story.append(Paragraph(clean(stripped), st["cover_kicker"]))
            elif stripped.startswith("CodeGuard"):
                story.append(Paragraph("CodeGuard", st["cover_title"]))
            elif re.match(r"^(申报方向|团队名称|团队成员|团队编号|报告日期)", stripped):
                story.append(Paragraph(clean(stripped), st["cover_meta"]))
            elif stripped.startswith("技术报告"):
                story.append(Paragraph(clean(stripped), st["cover_sub"]))
            else:
                story.append(Paragraph(clean(stripped), st["cover_meta"]))
            idx += 1
            continue
        else:
            story.append(Paragraph(clean(stripped), st["body"]))
        idx += 1


def footer_factory(date_label: str):
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.setFont("CJK", 7.6)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9.5 * mm, "CodeGuard · AI+开源 · %s" % date_label)
        canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, "%d" % doc.page)
        canvas.restoreState()
    return footer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=ROOT / "submission" / "09-技术报告-升级版.md")
    parser.add_argument("--out", type=Path, default=ROOT / "submission" / "CodeGuard-技术报告-v0.5.1.pdf")
    parser.add_argument("--date", default="2026-10-25")
    args = parser.parse_args()

    font = register_font()
    st = styles(font)
    text = args.src.read_text(encoding="utf-8")
    story: list = []
    total = A4[0] - 36 * mm
    build(story, st, text, total)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(args.out), pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=19 * mm,
                            title="CodeGuard：许可证污染溯源门禁", author="千里IT队")
    doc.build(story, onFirstPage=footer_factory(args.date), onLaterPages=footer_factory(args.date))

    import fitz  # noqa: WPS433 - only used for the build-time self check
    pages = fitz.open(str(args.out)).page_count
    size_kb = args.out.stat().st_size / 1024
    print("写入 %s" % args.out)
    print("页数 %d（要求正文≤15页）· 大小 %.0f KB（要求≤10MB）" % (pages, size_kb))
    if pages > 15:
        print("提示：超过 15 页，按 submission/00-提交清单.md §F 的删减顺序压缩。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
