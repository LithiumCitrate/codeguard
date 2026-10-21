#!/usr/bin/env python3
"""Control experiment behind the "0% false blocking" claim.

`codeguard benchmark --fp-study N` measures the gate as shipped. This script runs the
same 200-file cross-package study with the corroboration requirement switched off, so
the 3.5% -> 0% comparison in docs/DESIGN.md and the technical report is reproducible
without editing source.

    python scripts/false_block_control.py --sample 200
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from codeguard.adjudicate import Scanner          # noqa: E402
from codeguard.corpus import read_manifest        # noqa: E402
from codeguard.index import FingerprintIndex      # noqa: E402
from codeguard.score import LogisticRegression    # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=".codeguard")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--corroborate", action="store_true",
                    help="按出厂设置运行（默认关闭佐证要求，用于对照）")
    args = ap.parse_args(argv)

    index = FingerprintIndex.load(os.path.join(args.workspace, "index.bin"))
    model_path = os.path.join(args.workspace, "model.json")
    model = (LogisticRegression.from_json(json.load(open(model_path, encoding="utf-8")))
             if os.path.exists(model_path) else None)
    corpus_root = os.path.join(args.workspace, "corpus")
    entries = read_manifest(os.path.join(corpus_root, "corpus.json"))
    pool = [e for e in entries if e.lines >= 40]
    picked = random.Random(args.seed).sample(pool, min(args.sample, len(pool)))

    off = dict(corroborate_coverage=0.0, corroborate_verbatim=0,
               corroborate_confidence=0.0)
    scanner = Scanner(index, model=model, usage="distribution",
                      **({} if args.corroborate else off))
    risk, blocked_files, findings = {}, set(), 0
    for e in picked:
        path = os.path.join(corpus_root, e.path.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        # worst-case target licence: every copyleft source becomes a conflict
        scan = scanner.scan_text(text, target=e.path,
                                 target_license="LicenseRef-Proprietary",
                                 package_hint=e.package)
        findings += len(scan.findings)
        for f in scan.findings:
            risk[f.risk] = risk.get(f.risk, 0) + 1
            if f.risk in ("S3", "S4"):
                blocked_files.add(e.path)

    mode = "出厂设置（含佐证要求）" if args.corroborate else "对照：关闭佐证要求"
    print("跨包误阻断对照 · %s · 样本 %d 个真实文件" % (mode, len(picked)))
    print("  命中 %d 处；风险分布 %s" % (findings, risk or "无"))
    print("  阻断级 %d 处，涉及 %d 个文件 → 按文件误阻断率 %.2f%%"
          % (sum(v for k, v in risk.items() if k in ("S3", "S4")),
             len(blocked_files), 100.0 * len(blocked_files) / max(1, len(picked))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
