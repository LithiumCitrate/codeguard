#!/usr/bin/env python3
"""Materialise the demo subject for the video / defence deck.

Writes a corpus-derived sample (a GPL-2.0-or-later file with every locally defined
identifier renamed, i.e. what "the model rewrote it" actually looks like) into
``<workspace>/demo/`` - deliberately *inside* the gitignored workspace, because a
corpus-derived fragment must never be committed into an Apache-2.0 repository.

    python scripts/make_demo_sample.py                 # -> .codeguard/demo/feature_flags.py
    python scripts/make_demo_sample.py --mutation dead_code --seed 7
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from codeguard.corpus import read_manifest                      # noqa: E402
from codeguard.mutations import _top_level_blocks, apply_mutation  # noqa: E402


def pick_entry(entries, package, min_lines, max_lines):
    for e in entries:
        if e.package == package and min_lines <= e.lines <= max_lines:
            return e
    for e in entries:
        if e.package == package:
            return e
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=".codeguard")
    ap.add_argument("--package", default="mercurial")
    ap.add_argument("--min-lines", type=int, default=40)
    ap.add_argument("--max-lines", type=int, default=400)
    ap.add_argument("--blocks", type=int, default=3, help="保留前几个顶层定义")
    ap.add_argument("--mutation", default="rename")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--name", default="feature_flags.py")
    args = ap.parse_args(argv)

    corpus_root = os.path.join(args.workspace, "corpus")
    manifest = os.path.join(corpus_root, "corpus.json")
    if not os.path.exists(manifest):
        raise SystemExit("先运行 codeguard corpus（找不到 %s）" % manifest)
    entry = pick_entry(read_manifest(manifest), args.package,
                       args.min_lines, args.max_lines)
    if entry is None:
        raise SystemExit("语料中没有 %s 包；--package 可选：见 corpus.json" % args.package)

    path = os.path.join(corpus_root, entry.path.replace("/", os.sep))
    text = open(path, encoding="utf-8", errors="replace").read()
    head, blocks = _top_level_blocks(text)
    chosen = [b for b in blocks if b.startswith(("def ", "class "))][:args.blocks]
    imports = [l for l in head.splitlines(True)
               if l.startswith(("import ", "from "))][:6]
    snippet = "".join(imports) + "".join(chosen)
    sample = apply_mutation(snippet, args.mutation, args.seed)

    out_dir = os.path.join(args.workspace, "demo")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, args.name)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(sample)

    print("演示样本已生成：%s" % out.replace(os.sep, "/"))
    print("  来源      %s@%s（%s，解析来源 %s）"
          % (entry.package, entry.version, entry.license_spdx, entry.license_source))
    print("  来源文件  %s（原文件 %d 行）" % (entry.path, entry.lines))
    print("  取样      前 %d 个顶层定义 + %d 行 import，共 %d 行"
          % (len(chosen), len(imports), snippet.count("\n")))
    print("  改写      %s（seed=%d）→ %d 行，标识符已全量重命名"
          % (args.mutation, args.seed, sample.count("\n")))
    print("  边界      样本写在 .codeguard/ 内（已 gitignore）：语料派生片段不进仓库，"
          "本作品 Apache-2.0 源码中不含任何 copyleft 派生代码")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
