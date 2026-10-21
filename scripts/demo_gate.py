#!/usr/bin/env python3
"""Build a realistic "AI rewrote a copyleft helper" pull request and run the gate.

Nothing is downloaded and nothing is committed: the snippet comes from the local
corpus, the rewrite comes from the benchmark mutation engine, and the exit code
is the same one CI would see. Use it to sanity-check a workspace or to record the
demo video.

    python scripts/demo_gate.py --package paramiko --mutation compound
"""

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from codeguard.cli import main                                  # noqa: E402
from codeguard.mutations import _top_level_blocks, apply_mutation  # noqa: E402


def pick_snippet(corpus_root: str, package: str, min_lines: int) -> tuple:
    """First whole top-level blocks of a corpus file that reach ``min_lines``."""
    for folder in sorted(os.listdir(corpus_root)):
        if not folder.startswith(package + "-"):
            continue
        for dirpath, _, filenames in os.walk(os.path.join(corpus_root, folder)):
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                text = open(path, encoding="utf-8", errors="replace").read()
                head, blocks = _top_level_blocks(text)
                if not blocks:
                    continue
                chosen, count = [], 0
                for block in blocks:
                    if block.startswith("def ") or block.startswith("class "):
                        chosen.append(block)
                        count += block.count("\n")
                    if count >= min_lines:
                        break
                if count >= min_lines:
                    imports = [l for l in head.splitlines(True)
                               if l.startswith(("import ", "from "))][:6]
                    return "".join(imports) + "".join(chosen), os.path.join(folder, name)
    raise SystemExit("demo: 语料里没有 %s 的可切片文件，先运行 codeguard corpus" % package)


def as_diff(code: str, path: str) -> str:
    lines = ["diff --git a/%s b/%s" % (path, path),
             "--- /dev/null", "+++ b/%s" % path, "@@ -0,0 +1,%d @@" % code.count("\n")]
    lines += ["+" + l for l in code.splitlines()]
    return "\n".join(lines) + "\n"


def main_cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=".codeguard")
    ap.add_argument("--corpus", default="")
    ap.add_argument("--package", default="paramiko")
    ap.add_argument("--lines", type=int, default=40)
    ap.add_argument("--mutation", default="compound")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--license", default="LicenseRef-Proprietary",
                    help="被审查项目自身的许可证")
    ap.add_argument("--usage", default="distribution")
    ap.add_argument("--keep", action="store_true", help="保留生成的 diff 文件")
    args = ap.parse_args(argv)

    corpus_root = args.corpus or os.path.join(args.workspace, "corpus")
    snippet, origin = pick_snippet(corpus_root, args.package, args.lines)
    mutant = apply_mutation(snippet, args.mutation, args.seed)
    out_dir = tempfile.mkdtemp(prefix="codeguard-demo-")
    diff_path = os.path.join(out_dir, "pr-0001.diff")
    with open(diff_path, "w", encoding="utf-8") as fh:
        fh.write(as_diff(mutant, "myapp/helpers.py"))

    print("演示：把 %s 的实现改写后并入许可证为 %s 的项目" % (origin, args.license))
    print("变异：%s（seed=%d），原始 %d 行 → 提交 %d 行\n"
          % (args.mutation, args.seed, snippet.count("\n"), mutant.count("\n")))
    code = main(["--workspace", args.workspace, "gate", "--diff", diff_path,
                 "--name", "myapp/helpers.py", "--license", args.license,
                 "--usage", args.usage])
    print("\n退出码 %d（0 放行 / 1 阻断 / 2 环境或用法错误）" % code)
    print("diff 与报告：%s" % out_dir.replace(os.sep, "/"))
    return code


if __name__ == "__main__":
    raise SystemExit(main_cli())
