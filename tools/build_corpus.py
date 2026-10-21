#!/usr/bin/env python3
"""Build the licence-annotated corpus used by CodeGuard.

    python tools/build_corpus.py --probe          # resolve licences only
    python tools/build_corpus.py                  # fetch + write manifest
    python tools/build_corpus.py --packages my.txt

The manifest records, for every package, the resolved SPDX id *and* the origin of
that decision (PEP 639 expression, legacy field, trove classifier or source
header), which is what makes the corpus auditable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from codeguard import corpus as cp  # noqa: E402

DEFAULT = [
    "six", "iniconfig", "pyyaml", "tqdm",              # MIT / MIT / MIT / MPL-2.0
    "requests", "urllib3", "click", "python-dotenv",   # Apache-2.0 / MIT / BSD-3 / BSD-3
    "argparse", "snowballstemmer", "packaging",        # PSF-2.0 / BSD-3 / BSD-2
    "pylint", "paramiko", "glances",                   # GPL-2.0-or-later / LGPL-2.1 / LGPL-3.0
    "fava", "mercurial", "mpmath",                     # MIT / GPL-2.0-or-later / BSD-3
    "defusedxml", "legacy-cgi", "websockets",          # Zlib / PSF / BSD-3
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packages", default="")
    ap.add_argument("--root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".codeguard", "corpus"))
    ap.add_argument("--manifest", default="")
    ap.add_argument("--probe", action="store_true",
                    help="only resolve licences, do not download sources")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-files", type=int, default=90)
    args = ap.parse_args()

    names = DEFAULT
    if args.packages:
        with open(args.packages, encoding="utf-8") as fh:
            names = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    root = os.path.abspath(args.root)
    os.makedirs(root, exist_ok=True)
    manifest = os.path.abspath(args.manifest or os.path.join(root, "corpus.json"))
    from codeguard.license_intel import load_spdx
    spdx_index = load_spdx()

    lines = []

    def log(msg):
        lines.append(msg)
        print(msg, flush=True)

    def work(name):
        try:
            if args.probe:
                meta = cp.fetch_json(cp.PYPI_JSON % name)
                spdx, origin, raw = cp.resolve_package_license(meta["info"], spdx_index)
                return "%-18s %-9s %-18s %-16s %s" % (
                    name, meta["info"]["version"], spdx, origin, raw)
            return cp.build_package(name, "", root, spdx_index,
                                    max_files=args.max_files, log=log)
        except Exception as exc:  # keep going: the corpus is best-effort
            return "FAIL %-16s %s: %s" % (name, type(exc).__name__, exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(work, names))

    if args.probe:
        for r in results:
            print(r, flush=True)
        return

    entries = []
    for r in results:
        if isinstance(r, list):
            entries.extend(r)
        else:
            print(r, flush=True)
    cp.write_manifest(entries, manifest,
                      extra={"packages": names, "files": len(entries),
                             "max_files_per_package": args.max_files})
    from collections import Counter
    counts = Counter(e.license_spdx for e in entries)
    print("\ncorpus: %d files, %d packages" % (len(entries), len({e.package for e in entries})))
    for lic, n in counts.most_common():
        print("  %-20s %5d files" % (lic, n))
    print("manifest: %s" % manifest)


if __name__ == "__main__":
    main()
