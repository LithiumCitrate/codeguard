"""Corpus acquisition: fetch real open-source packages and resolve their licence.

Everything the matcher knows about provenance starts here, so the module records
*how* each licence was determined (PEP 639 expression -> legacy field -> trove
classifier -> header scan) instead of pretending the answer was obvious. Only
fingerprints enter the index; the corpus tree stays in a git-ignored work dir.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tarfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass

from .license_intel import load_spdx, normalize_expression, profile_for
from .normalize import tokenize_source

PYPI_JSON = "https://pypi.org/pypi/%s/json"
SOURCE_FILENAME_RE = re.compile(r"(licen[cs]e|copying|notice|ead(er)?\.txt)", re.I)
_HEADER_RE = re.compile(
    r"(SPDX-License-Identifier|Licensed under the|This software is licensed under|"
    r"许可证|木兰宽松许可证)[:\s]*([^\n]{0,80})", re.I)
_CODE_EXT = (".py",)
MAX_FILE_BYTES = 180_000
MAX_FILES_PER_PACKAGE = 90


@dataclass
class CorpusEntry:
    package: str
    version: str
    path: str
    abs_path: str
    license_spdx: str
    license_source: str
    license_raw: str
    language: str
    lines: int
    tokens: int
    sha256: str
    size: int
    sdist_sha256: str
    home: str = ""


def fetch_json(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "CodeGuard/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_bytes(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CodeGuard/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def resolve_package_license(info: dict, spdx_index: dict, sdist_text: str = "") -> tuple:
    """Run the documented resolution chain and return (spdx, origin, raw)."""
    expr = info.get("license_expression") or ""
    legacy = info.get("license") or ""
    classifiers = [c.split(" :: ")[-1] for c in info.get("classifiers", [])
                   if c.startswith("License ::")]
    chain = [(expr, "pep639-expression"), (legacy, "license-field")]
    for cls in classifiers:
        chain.append((cls, "trove-classifier"))
    spdx, origin = normalize_expression_best(chain, spdx_index)
    if spdx == "UNKNOWN" and sdist_text:
        m = _HEADER_RE.search(sdist_text)
        if m:
            spdx, origin = normalize_expression(m.group(2) or m.group(1), spdx_index)
            origin = "source-header"
    raw = expr or legacy or (classifiers[0] if classifiers else "")
    return spdx, origin, raw


def normalize_expression_best(chain, spdx_index) -> tuple:
    for value, origin in chain:
        if not value:
            continue
        spdx, how = normalize_expression(value, spdx_index)
        if spdx != "UNKNOWN":
            return spdx, origin if how != "expression:%s" % value else origin
    return "UNKNOWN", "unresolved"


def _iter_archive_files(blob: bytes, is_zip: bool):
    import io
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                yield name, zf.read(name)
        return
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
        for member in tf:
            if not member.isfile():
                continue
            handle = tf.extractfile(member)
            if handle is None:
                continue
            yield member.name, handle.read()


def build_package(name: str, version: str, dest_root: str, spdx_index: dict,
                  max_files: int = MAX_FILES_PER_PACKAGE, log=None) -> list:
    """Download one sdist, write source files out and return corpus entries."""
    def say(msg):
        if log:
            log(msg)

    meta = fetch_json(PYPI_JSON % name)
    chosen = version or meta["info"]["version"]
    records = [u for u in meta.get("releases", {}).get(chosen, [])
               if u.get("packagetype") == "sdist"]
    if not records:
        records = [u for u in meta.get("urls", []) if u.get("packagetype") == "sdist"]
        chosen = meta["info"]["version"]
    if not records:
        records = [u for u in meta.get("urls", []) if u.get("packagetype") == "bdist_wheel"]
    if not records:
        say("skip %s: no distribution found" % name)
        return []
    dist = records[0]
    blob = fetch_bytes(dist["url"])
    sdist_sha = hashlib.sha256(blob).hexdigest()
    is_zip = dist["filename"].endswith(".zip") or dist["url"].endswith(".whl")
    pkg_dir = os.path.join(dest_root, "%s-%s" % (name, chosen))
    os.makedirs(pkg_dir, exist_ok=True)

    # first pass: peek licence files for the header fallback
    peek = []
    for arcname, data in _iter_archive_files(blob, is_zip):
        base = os.path.basename(arcname)
        if SOURCE_FILENAME_RE.search(base) and len(data) < 200_000:
            peek.append(data.decode("utf-8", "replace"))
        if len(peek) >= 3:
            break
    spdx, origin, raw = resolve_package_license(meta["info"], spdx_index,
                                                 "\n".join(peek[:1]))
    profile = profile_for(spdx)
    say("%-16s %-10s %-18s (%s) %s" % (name, chosen, spdx, origin, profile.name))

    entries, written = [], 0
    for arcname, data in _iter_archive_files(blob, is_zip):
        if not arcname.endswith(_CODE_EXT):
            continue
        if any(part.startswith("test") and "site-packages" not in part
               for part in arcname.split("/")[:-1]):
            continue
        if len(data) > MAX_FILE_BYTES or len(data) < 120:
            continue
        rel = "/".join(arcname.split("/")[1:]) or os.path.basename(arcname)
        if not rel:
            continue
        out = os.path.join(pkg_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        with open(out, "wb") as fh:
            fh.write(data)
        entries.append(CorpusEntry(
            name, chosen, "%s-%s/%s" % (name, chosen, rel), out, spdx, origin, raw,
            "python", text.count("\n") + 1, len(tokenize_source(text)),
            hashlib.sha256(data).hexdigest(), len(data), sdist_sha,
            home=(meta["info"].get("project_urls") or {}).get("Homepage", "")))
        written += 1
        if written >= max_files:
            break
    return entries


def write_manifest(entries, path: str, extra: dict | None = None):
    payload = {"schema": "codeguard.corpus/v1", "entries": [asdict(e) for e in entries]}
    if extra:
        payload.update(extra)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return path


def read_manifest(path: str) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [CorpusEntry(**e) for e in data["entries"]]
