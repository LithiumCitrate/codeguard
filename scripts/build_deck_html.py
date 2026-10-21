"""Compile the 17 SVG pages into the self-contained web deck.

The deck's single source of truth is ``submission/deck/*.svg`` (the same pages
``svg_to_pptx.py`` exports).  The previous hand-written HTML drifted away from
the slides - it still showed 99 tests and the old conf=0.66 demo - so this
script rebuilds it deterministically: one <section> per SVG, ids prefixed per
page (slide 04 draws an arrow marker), notes from the speaker-note Markdown,
no external resource at all.

Usage:
    python scripts/build_deck_html.py
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "submission" / "deck"
NOTES = ROOT / "submission" / "答辩演示-讲者备注.md"
OUT = ROOT / "submission" / "答辩演示.html"

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CodeGuard：许可证污染溯源门禁 · 答辩演示</title>
<style>
  :root {{ --stage: #14181c; --muted: #8b98a3; --accent: #7de6ff; --line: #2b333b; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; background: var(--stage); color: #e8edf1;
    font-family: "Saira", "Microsoft YaHei", "PingFang SC", sans-serif; }}
  .deck {{ display: grid; gap: 24px; padding: 64px 16px 40px; }}
  .slide {{ width: min(100%, calc((100vh - 56px) * 16 / 9)); margin: 0 auto; }}
  .slide svg {{ display: block; width: 100%; height: auto; background: #fff; }}
  .notes {{ max-width: 960px; margin: 8px auto 0; padding: 12px 16px;
    border-left: 3px solid var(--accent); background: #1b2127; color: #cbd5dc;
    font-size: 14px; line-height: 1.8; }}
  .notes[hidden] {{ display: none; }}
  .bar {{ position: fixed; top: 0; left: 0; right: 0; z-index: 5;
    display: flex; justify-content: flex-end; gap: 12px; align-items: center;
    padding: 7px 16px; background: rgba(20, 24, 28, .94);
    border-bottom: 1px solid var(--line); font-size: 12px; letter-spacing: .12em;
    text-transform: uppercase; color: var(--muted); }}
  .bar b {{ color: var(--accent); font-variant-numeric: tabular-nums; }}
  .bar button {{ font: inherit; letter-spacing: .08em; color: #e8edf1;
    background: transparent; border: 1px solid var(--line); padding: 5px 9px;
    cursor: pointer; }}
  .bar button:hover {{ border-color: var(--accent); }}
  @media print {{
    @page {{ size: 1280px 720px; margin: 0; }}
    html, body {{ background: #fff; }}
    .deck {{ display: block; padding: 0; gap: 0; }}
    .slide {{ width: 1280px; height: 720px; page-break-after: always; }}
    .notes, .bar {{ display: none !important; }}
  }}
</style>
</head>
<body>
<main class="deck">
{slides}
</main>
<div class="bar"><button id="toggleNotes" type="button">备注 N</button><span><b id="pos">01</b> / {count}</span></div>
<script>
  const slides = [...document.querySelectorAll('.slide')];
  const notes = [...document.querySelectorAll('.notes')];
  let hidden = true;
  notes.forEach(n => {{ n.hidden = true; }});
  const toggle = document.getElementById('toggleNotes');
  toggle.addEventListener('click', () => {{
    hidden = !hidden;
    notes.forEach(n => {{ n.hidden = hidden; }});
    toggle.textContent = hidden ? '备注 N' : '收起备注';
  }});
  document.addEventListener('keydown', (event) => {{
    const current = slides.findIndex(s => s.getBoundingClientRect().top > -window.innerHeight / 2);
    const index = current < 0 ? slides.length - 1 : current;
    if (['ArrowRight', 'PageDown', ' '].includes(event.key)) {{
      event.preventDefault();
      slides[Math.min(index + 1, slides.length - 1)].scrollIntoView({{ behavior: 'smooth' }});
    }} else if (['ArrowLeft', 'PageUp'].includes(event.key)) {{
      event.preventDefault();
      slides[Math.max(index - 1, 0)].scrollIntoView({{ behavior: 'smooth' }});
    }} else if (event.key.toLowerCase() === 'n') {{
      toggle.click();
    }}
  }});
  const pos = document.getElementById('pos');
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach(entry => {{
      if (entry.isIntersecting) {{
        pos.textContent = String(slides.indexOf(entry.target) + 1).padStart(2, '0');
      }}
    }});
  }}, {{ threshold: 0.6 }});
  slides.forEach(s => observer.observe(s));
</script>
</body>
</html>
"""


def load_notes() -> dict:
    if not NOTES.exists():
        return {}
    text = NOTES.read_text(encoding="utf-8")
    parts = re.split(r"^#\s+Slide\s+(\d+)\s*$", text, flags=re.M)
    out = {}
    for index in range(1, len(parts), 2):
        body = re.sub(r"\n---\s*$", "", parts[index + 1]).strip()
        out[int(parts[index])] = body
    return out


def inline(svg: str, page: int) -> str:
    """Prefix ids so 17 inlined SVGs keep their local marker references."""
    prefix = "p%02d-" % page
    svg = re.sub(r'\bid="([^"]+)"', lambda m: 'id="%s%s"' % (prefix, m.group(1)), svg)
    svg = re.sub(r"url\(#([^)]+)\)", lambda m: "url(#%s%s)" % (prefix, m.group(1)), svg)
    svg = re.sub(r"href=\"#([^\"]+)\"", lambda m: 'href="#%s%s"' % (prefix, m.group(1)), svg)
    return svg.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default=str(DECK))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    pages = sorted(Path(args.deck).glob("*.svg"))
    if not pages:
        raise SystemExit("no SVG pages under %s" % args.deck)
    notes = load_notes()
    blocks = []
    for index, path in enumerate(pages, 1):
        svg = path.read_text(encoding="utf-8")
        note = notes.get(index, "")
        note_html = ('<aside class="notes">%s</aside>' % html.escape(note).replace("\n", "<br>")
                     if note else "")
        blocks.append('<section class="slide" id="slide-%02d">\n%s\n</section>\n%s'
                      % (index, inline(svg, index), note_html))
    document = PAGE.format(slides="\n".join(blocks), count=len(pages))
    Path(args.out).write_text(document, encoding="utf-8", newline="\n")
    externals = re.findall(r'(?:src|href)="(https?://[^"]+)"', document)
    print("pages: %d | notes: %d | bytes: %d | external refs: %d"
          % (len(pages), sum(1 for i in range(1, len(pages) + 1) if notes.get(i)),
             len(document.encode("utf-8")), len(externals)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
