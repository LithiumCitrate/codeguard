"""Merge CodeGuard's per-file SARIF reports into a single-run document.

GitHub Code Scanning refuses several SARIF runs under one category, so CI folds
``codeguard scan --format sarif``'s per-file output into one file before the
upload step.

Usage:
    python scripts/merge_sarif.py .codeguard/reports/scan --out .codeguard/reports/self-scan.sarif
    python scripts/merge_sarif.py a.sarif b.sarif --out merged.sarif
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codeguard.report import merge_sarif


def collect(inputs: list) -> list:
    files = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            found = sorted(path.glob("*.sarif"))
            if not found:
                raise SystemExit("目录里没有 .sarif 文件：%s" % path)
            files.extend(found)
        elif path.exists():
            files.append(path)
        else:
            raise SystemExit("找不到输入：%s" % path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="SARIF 文件或包含 SARIF 的目录")
    parser.add_argument("--out", required=True, help="合并后的单文件输出路径")
    args = parser.parse_args()

    files = collect(args.inputs)
    docs = []
    for path in files:
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise SystemExit("%s 不是合法 JSON：%s" % (path, exc))

    try:
        merged = merge_sarif(docs)
    except ValueError as exc:
        raise SystemExit("合并失败：%s" % exc)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    run = merged["runs"][0]
    print("合并 %d 份 SARIF -> %s" % (len(docs), out))
    print("  run 数 1 · 结果 %d 条 · 规则 %d 条 · 覆盖文件 %d 个" % (
        len(run["results"]), len(run["tool"]["driver"]["rules"]),
        len(run["properties"]["scannedTargets"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
