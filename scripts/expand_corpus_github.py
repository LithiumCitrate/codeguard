#!/usr/bin/env python3
"""Expand the corpus with shallow-cloned GitHub repositories.

The shipped `codeguard corpus` pulls pinned PyPI sdists (Python only). This
script widens the knowledge base with real repositories in other languages and
licences: it shallow-clones each repo, resolves its licence from the licence
files at the repo root (falling back to the per-repo override), copies the
source files into the corpus tree as `<repo>-<commit>/...` and merges the
entries into `.codeguard/corpus/corpus.json` so a plain `codeguard index`
rebuild picks them up.

Clones are cached in `.codeguard/github-clone/`; re-running re-uses them and
only refreshes the file copies. Nothing here is loaded at import time and no
repository code is ever executed.

Usage:
    PYTHONPATH=src python scripts/expand_corpus_github.py            # all repos
    PYTHONPATH=src python scripts/expand_corpus_github.py --only git jquery
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codeguard.corpus import CorpusEntry  # noqa: E402
from codeguard.license_intel import normalize_expression, profile_for  # noqa: E402
from codeguard.normalize import tokenize_source  # noqa: E402

WORKSPACE = ROOT / ".codeguard"
CLONE_DIR = WORKSPACE / "github-clone"
CORPUS_ROOT = WORKSPACE / "corpus"
MANIFEST = CORPUS_ROOT / "corpus.json"

MAX_FILE_BYTES = 180_000
MIN_FILE_BYTES = 120
MAX_FILES_PER_REPO = 120

LANGS = {
    ".py": "python", ".pyw": "python",
    ".js": "generic", ".mjs": "generic", ".ts": "generic", ".jsx": "generic", ".tsx": "generic",
    ".c": "generic", ".h": "generic", ".cpp": "generic", ".cc": "generic", ".hpp": "generic",
    ".go": "generic", ".rs": "generic", ".java": "generic", ".rb": "generic", ".php": "generic",
}
SKIP_DIRS = {".git", ".github", "node_modules", "vendor", "third_party", "thirdparty",
             "__pycache__", "build", "dist", ".venv", "venv", "testdata", "fuzz"}
MINIFIED = re.compile(r"\.min\.(js|css)$", re.I)

# (repo dir name, clone url, expected SPDX or None, note)
REPOS = [
    ("fastapi", "https://github.com/tiangolo/fastapi", "MIT", "Python · web framework"),
    ("httpx", "https://github.com/encode/httpx", "BSD-3-Clause", "Python · http client"),
    ("requests", "https://github.com/psf/requests", "Apache-2.0", "Python · http client"),
    ("flask", "https://github.com/pallets/flask", "BSD-3-Clause", "Python · web framework"),
    ("pydantic", "https://github.com/pydantic/pydantic", "MIT", "Python · validation"),
    ("django", "https://github.com/django/django", "BSD-3-Clause", "Python · web framework"),
    ("git", "https://github.com/git/git", "GPL-2.0-only", "C · VCS"),
    ("nginx", "https://github.com/nginx/nginx", "BSD-2-Clause", "C · http server"),
    ("radare2", "https://github.com/radareorg/radare2", "LGPL-3.0-only", "C · reverse engineering"),
    ("minio", "https://github.com/minio/minio", "AGPL-3.0-only", "Go · object storage"),
    ("cobra", "https://github.com/spf13/cobra", "Apache-2.0", "Go · cli"),
    ("jquery", "https://github.com/jquery/jquery", "MIT", "JavaScript · dom"),
    ("html5ever", "https://github.com/servo/html5ever", None, "Rust · html parser (dual)"),
]

_LIC_RE = re.compile(r"^(licen[cs]e|copying|copyright)([.\-_ ].*)?$", re.I)
_LIC_PHRASES = [
    (re.compile(r"affero.*general public license.*version 3|gnu affero general public license", re.I | re.S), "AGPL-3.0-only"),
    (re.compile(r"lesser general public license.*version 3|gnu lesser general public license v3", re.I | re.S), "LGPL-3.0-only"),
    (re.compile(r"lesser general public license.*version 2\.1|gnu lesser general public license v2", re.I | re.S), "LGPL-2.1"),
    (re.compile(r"mozilla public license.*2\.0", re.I | re.S), "MPL-2.0"),
    (re.compile(r"general public license.*version 2(?!.*later)|gnu general public license v2", re.I | re.S), "GPL-2.0-only"),
    (re.compile(r"general public license.*version 3", re.I | re.S), "GPL-3.0-only"),
    (re.compile(r"apache license.*version 2", re.I | re.S), "Apache-2.0"),
    (re.compile(r"mit license", re.I | re.S), "MIT"),
    (re.compile(r"bsd 2-clause", re.I | re.S), "BSD-2-Clause"),
    (re.compile(r"bsd 3-clause|redistribution and use.*neither the name", re.I | re.S), "BSD-3-Clause"),
    (re.compile(r"the unlicense", re.I | re.S), "Unlicense"),
    (re.compile(r"isc license", re.I | re.S), "ISC"),
]


def run_git(args: list, cwd: str | None = None) -> str:
    out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True,
                         timeout=420, check=True)
    return out.stdout.strip()


def detect_license(repo_dir: Path) -> tuple:
    """Read the root licence files and map their wording to an SPDX id."""
    blobs = []
    for item in sorted(repo_dir.iterdir()):
        if item.is_file() and _LIC_RE.match(item.name) and item.stat().st_size < 400_000:
            blobs.append((item.name, item.read_text(encoding="utf-8", errors="replace")))
    for blob_name, blob in blobs:
        for pattern, spdx in _LIC_PHRASES:
            if pattern.search(blob[:4000]) or pattern.search(blob[:20000]):
                return spdx, "repo-license:" + blob_name
    if blobs:
        return "UNKNOWN", "repo-license:" + blobs[0][0]
    return "UNKNOWN", "repo-license:none"


def collect_files(repo_dir: Path) -> list:
    picked = []
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            lang = LANGS.get(ext)
            if not lang or MINIFIED.search(name):
                continue
            full = Path(dirpath) / name
            size = full.stat().st_size
            if not MIN_FILE_BYTES <= size <= MAX_FILE_BYTES:
                continue
            picked.append((lang, full))
    picked.sort(key=lambda p: str(p[1]).lower())
    return picked[:MAX_FILES_PER_REPO]


def expand_repo(name: str, url: str, expected: str | None, note: str, log=print) -> list:
    repo_dir = CLONE_DIR / name
    if (repo_dir / ".git").exists():
        log("  复用已有克隆：%s" % repo_dir)
    else:
        log("  浅克隆 %s …" % url)
        shutil.rmtree(repo_dir, ignore_errors=True)
        run_git(["clone", "--depth", "1", "--quiet", url, str(repo_dir)])
    sha = run_git(["rev-parse", "HEAD"], cwd=str(repo_dir))
    short = sha[:10]

    spdx, lic_source = detect_license(repo_dir)
    raw = spdx
    if spdx == "UNKNOWN" and expected:
        spdx, lic_source = expected, "repo-override"
    if expected and spdx != expected:
        log("  注意：检出许可证 %s 与预期 %s 不同，按检出值记录" % (spdx, expected))
    if spdx == "UNKNOWN":
        log("  跳过 %s：许可证未识别（%s）" % (name, lic_source))
        return []

    profile = profile_for(spdx)
    log("  %-10s %-16s (%s) %s · %s" % (name, spdx, lic_source, profile.name, note))

    version = short
    pkg_dir = CORPUS_ROOT / ("%s-%s" % (name, version))
    pkg_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for lang, full in collect_files(repo_dir):
        data = full.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        rel = full.relative_to(repo_dir).as_posix()
        out = pkg_dir / rel.replace("/", os.sep)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        entries.append(CorpusEntry(
            name, version, "%s-%s/%s" % (name, version, rel), str(out), spdx, lic_source,
            raw, lang, text.count("\n") + 1, len(tokenize_source(text, lang)),
            hashlib.sha256(data).hexdigest(), len(data), "git:" + sha, home=url))
    log("  收录 %d 个文件" % len(entries))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="只处理这些仓库（目录名）")
    args = parser.parse_args()

    if not MANIFEST.exists():
        sys.exit("找不到 %s，请先运行 `codeguard corpus`" % MANIFEST)
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    CLONE_DIR.mkdir(parents=True, exist_ok=True)

    repos = [r for r in REPOS if not args.only or r[0] in args.only]
    # 重跑覆盖：先清掉这些仓库此前克隆进来的条目（sdist_sha256 以 git: 开头），
    # PyPI 的同名包（如 requests）不受影响。
    names = {r[0] for r in repos}
    payload["entries"] = [e for e in payload["entries"]
                          if not (e["package"] in names and e["sdist_sha256"].startswith("git:"))]
    have = {(e["package"], e["version"], e["path"]) for e in payload["entries"]}
    added = []
    for name, url, expected, note in repos:
        print("== %s" % name, flush=True)
        try:
            for entry in expand_repo(name, url, expected, note):
                key = (entry.package, entry.version, entry.path)
                if key not in have:
                    payload["entries"].append(entry.__dict__)
                    have.add(key)
                    added.append(entry)
        except Exception as exc:  # 单仓失败不拖垮整体
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc), flush=True)

    payload["github_repos"] = {n: {"url": u, "expected": e} for n, u, e, _ in REPOS}
    payload["github_note"] = ("浅克隆的 GitHub 仓库语料：许可证按仓库根目录许可文件检出，"
                              "提交哈希记录在条目的 sdist_sha256 字段（git:<sha>）。")
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, MANIFEST)

    counts = {}
    for e in added:
        counts[e.license_spdx] = counts.get(e.license_spdx, 0) + 1
    print("\n本次新增：%d 个文件；许可证分布：" % len(added))
    for lic, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  %-20s %5d files" % (lic, n))
    print("清单：%s（下一步：PYTHONPATH=src python -m codeguard index）" % MANIFEST)


if __name__ == "__main__":
    main()
