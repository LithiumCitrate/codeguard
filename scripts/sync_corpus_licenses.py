#!/usr/bin/env python3
"""Ensure every corpus package directory ships its licence files.

The corpus tree is redistributed verbatim inside the portable Windows
build, so each package directory must carry the upstream licence/notice
files (GPL/AGPL/LGPL require the licence text to accompany the source).
Two sources are used:

* GitHub-cloned packages (``<repo>-<sha10>``): root licence files are
  copied from the clone cache in ``.codeguard/github-clone/``.
* PyPI sdist packages (``<pkg>-<version>``): if a licence file is
  missing, it is extracted from the pinned upstream archive recorded in
  ``submission/evidence/corpus-integrity.json`` (cached in
  ``.codeguard/upstream-archives/``).

Licence files carry no source extension, so the index and corpus
manifest are untouched. Safe to re-run; existing files are overwritten
with the upstream copy.

Usage:
    python scripts/sync_corpus_licenses.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from expand_corpus_github import (  # noqa: E402
    CLONE_DIR, CORPUS_ROOT, _LIC_SHIP_RE, run_git,
)

ARCHIVES = ROOT / ".codeguard" / "upstream-archives"
INTEGRITY = ROOT / "submission" / "evidence" / "corpus-integrity.json"


def has_license(pkg_dir: Path) -> bool:
    return any(p.is_file() and _LIC_SHIP_RE.match(p.name) for p in pkg_dir.iterdir())


def sync_github(log=print) -> int:
    fixed = 0
    if not CLONE_DIR.exists():
        return 0
    for clone in sorted(CLONE_DIR.iterdir()):
        if not (clone / ".git").is_dir():
            continue
        sha = run_git(["rev-parse", "HEAD"], cwd=str(clone))
        pkg_dir = CORPUS_ROOT / ("%s-%s" % (clone.name, sha[:10]))
        if not pkg_dir.is_dir():
            log("  跳过 %s：语料树中无 %s" % (clone.name, pkg_dir.name))
            continue
        for item in sorted(clone.iterdir()):
            if item.is_file() and _LIC_SHIP_RE.match(item.name):
                (pkg_dir / item.name).write_bytes(item.read_bytes())
        if has_license(pkg_dir):
            fixed += 1
        else:
            log("  警告：%s 根目录没有许可/声明文件" % clone.name)
    return fixed


def archive_license_members(archive: Path):
    names = []
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            for info in infos:
                parts = info.filename.split("/")
                if len(parts) == 2 and not info.is_dir() and _LIC_SHIP_RE.match(parts[1]):
                    names.append((info.filename, zf.read(info)))
    else:
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                parts = member.name.split("/")
                if (len(parts) == 2 and member.isfile()
                        and _LIC_SHIP_RE.match(parts[1])):
                    names.append((member.name, tf.extractfile(member).read()))
    return names


def sync_pypi(manifest: dict, log=print) -> int:
    integrity = json.loads(INTEGRITY.read_text(encoding="utf-8"))
    by_archive = {entry["archive"]: entry for entry in integrity}
    versions = {}
    for entry in manifest["entries"]:
        sha_field = entry.get("sdist_sha256", "")
        if sha_field.startswith("git:"):
            continue
        versions.setdefault((entry["package"], entry["version"]), None)

    fixed = missing_archive = 0
    for package, version in sorted(versions):
        pkg_dir = CORPUS_ROOT / ("%s-%s" % (package, version))
        if not pkg_dir.is_dir() or has_license(pkg_dir):
            continue
        archive = None
        for name in by_archive:
            if name.startswith("%s-%s" % (package, version)):
                archive = ARCHIVES / name
                break
        if archive is None or not archive.exists():
            log("  警告：%s 无 upstream 原档可用" % pkg_dir.name)
            missing_archive += 1
            continue
        found = archive_license_members(archive)
        if not found:
            log("  警告：%s 原档 %s 根目录无许可文件" % (pkg_dir.name, archive.name))
            continue
        for _, blob in found:
            name = Path(_[0]).name
            (pkg_dir / name).write_bytes(blob)
        fixed += 1
    if missing_archive:
        log("  %d 个包缺原档（可运行 codeguard corpus 补齐下载）" % missing_archive)
    return fixed


def main():
    manifest = json.loads((CORPUS_ROOT / "corpus.json").read_text(encoding="utf-8"))
    print("GitHub 克隆包：")
    n_git = sync_github()
    print("  已确保 %d 个包携带许可文件" % n_git)
    print("PyPI sdist 包：")
    n_pypi = sync_pypi(manifest)
    print("  本次从原档补入 %d 个包" % n_pypi)

    pkgs = sorted({(e["package"], e["version"]) for e in manifest["entries"]})
    still_missing = [d.name for package, version in pkgs
                     if (d := CORPUS_ROOT / ("%s-%s" % (package, version))).is_dir()
                     and not has_license(d)]
    if still_missing:
        print("仍缺许可证：%s" % ", ".join(still_missing))
        sys.exit(1)
    print("全部 %d 个语料包均随附许可/声明文件" % len(pkgs))


if __name__ == "__main__":
    main()
