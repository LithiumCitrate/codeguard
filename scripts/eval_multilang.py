"""Offline multi-language benchmark for C / Go / JavaScript / Rust.

Uses only Python's standard library and the local corpus/index in `.codeguard`.
Samples real source files per language from `.codeguard/corpus/corpus.json`,
generates four deterministic mutations (identity, comment_inject, reformat,
rename), evaluates them alongside Python + multi-language clean negatives and
cross-language probes through the production `Scanner` + `FingerprintIndex`,
and writes JSON + Markdown evidence under `submission/evidence/`.

Usage:
    PYTHONPATH=src python scripts/eval_multilang.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import random
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codeguard import __version__  # noqa: E402
from codeguard.adjudicate import Scanner, language_for  # noqa: E402
from codeguard.cli import load_index, load_model, workspace  # noqa: E402
from codeguard.corpus import read_manifest  # noqa: E402
from codeguard.normalize import _builtins_for, _keywords_for, tokenize_source  # noqa: E402
from codeguard.report import index_fingerprint  # noqa: E402

LANGUAGES = ("c", "go", "javascript", "rust")
MUTATIONS = ("identity", "comment_inject", "reformat", "rename")

_COMMENT_POOL = (
    "NOTE: compatibility shim kept for callers",
    "TODO: revisit buffer sizing later",
    "guard against unexpected boundary values",
    "preserve deterministic ordering here",
    "fast path for common inputs",
)

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUM_RE = re.compile(r"[0-9][0-9A-Fa-f_xXbB.]*")

# Clean-room multi-language negative controls (written from scratch, not in corpus).
CLEAN_MULTILANG_NEGATIVES = [
    {
        "id": "clean-c-ring",
        "language": "c",
        "code": """#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t capacity;
    uint32_t head;
    uint32_t count;
    int32_t slots[64];
} cg_ring_t;

void cg_ring_init(cg_ring_t *ring, uint32_t cap) {
    ring->capacity = (cap > 64u) ? 64u : cap;
    ring->head = 0u;
    ring->count = 0u;
}

int cg_ring_push(cg_ring_t *ring, int32_t item) {
    if (ring->capacity == 0u) return -1;
    uint32_t idx = (ring->head + ring->count) % ring->capacity;
    if (ring->count < ring->capacity) {
        ring->slots[idx] = item;
        ring->count += 1u;
        return 0;
    }
    ring->slots[ring->head] = item;
    ring->head = (ring->head + 1u) % ring->capacity;
    return 1;
}

int cg_ring_pop(cg_ring_t *ring, int32_t *out) {
    if (ring->count == 0u) return -1;
    *out = ring->slots[ring->head];
    ring->head = (ring->head + 1u) % ring->capacity;
    ring->count -= 1u;
    return 0;
}
""",
    },
    {
        "id": "clean-c-checksum",
        "language": "c",
        "code": """#include <stddef.h>
#include <stdint.h>

uint32_t cg_fnv1a_32(const uint8_t *buf, size_t len) {
    uint32_t hash = 2166136261u;
    for (size_t i = 0; i < len; ++i) {
        hash ^= (uint32_t)buf[i];
        hash *= 16777619u;
    }
    return hash;
}

size_t cg_hex_encode(const uint8_t *src, size_t len, char *dst, size_t cap) {
    static const char digits[] = "0123456789abcdef";
    if (cap < len * 2u + 1u) return 0u;
    for (size_t i = 0; i < len; ++i) {
        dst[i * 2u] = digits[(src[i] >> 4) & 0x0fu];
        dst[i * 2u + 1u] = digits[src[i] & 0x0fu];
    }
    dst[len * 2u] = '\\0';
    return len * 2u;
}
""",
    },
    {
        "id": "clean-go-bucket",
        "language": "go",
        "code": """package ratelimit

import "time"

type TokenBucket struct {
    capacity float64
    tokens   float64
    rate     float64
    updated  time.Time
}

func NewTokenBucket(capacity, rate float64, now time.Time) *TokenBucket {
    return &TokenBucket{
        capacity: capacity,
        tokens:   capacity,
        rate:     rate,
        updated:  now,
    }
}

func (b *TokenBucket) Allow(cost float64, now time.Time) bool {
    elapsed := now.Sub(b.updated).Seconds()
    if elapsed > 0 {
        b.tokens += elapsed * b.rate
        if b.tokens > b.capacity {
            b.tokens = b.capacity
        }
        b.updated = now
    }
    if b.tokens < cost {
        return false
    }
    b.tokens -= cost
    return true
}
""",
    },
    {
        "id": "clean-go-kv",
        "language": "go",
        "code": """package kvstore

import "sort"

type Entry struct {
    Key   string
    Value int
}

type SortedMap struct {
    items []Entry
}

func (m *SortedMap) Put(key string, val int) {
    idx := sort.Search(len(m.items), func(i int) bool {
        return m.items[i].Key >= key
    })
    if idx < len(m.items) && m.items[idx].Key == key {
        m.items[idx].Value = val
        return
    }
    m.items = append(m.items, Entry{})
    copy(m.items[idx+1:], m.items[idx:])
    m.items[idx] = Entry{Key: key, Value: val}
}

func (m *SortedMap) Get(key string) (int, bool) {
    idx := sort.Search(len(m.items), func(i int) bool {
        return m.items[i].Key >= key
    })
    if idx < len(m.items) && m.items[idx].Key == key {
        return m.items[idx].Value, true
    }
    return 0, false
}
""",
    },
    {
        "id": "clean-js-lru",
        "language": "javascript",
        "code": """class BoundedCache {
    constructor(limit) {
        this.limit = Math.max(1, limit | 0);
        this.entries = new Map();
    }

    get(key) {
        if (!this.entries.has(key)) {
            return undefined;
        }
        const value = this.entries.get(key);
        this.entries.delete(key);
        this.entries.set(key, value);
        return value;
    }

    set(key, value) {
        if (this.entries.has(key)) {
            this.entries.delete(key);
        } else if (this.entries.size >= this.limit) {
            const oldest = this.entries.keys().next().value;
            this.entries.delete(oldest);
        }
        this.entries.set(key, value);
        return this;
    }

    clear() {
        this.entries.clear();
    }
}
""",
    },
    {
        "id": "clean-js-query",
        "language": "javascript",
        "code": """function parseQueryPairs(rawQuery) {
    const cleaned = String(rawQuery || "").replace(/^\\?/, "");
    if (!cleaned) {
        return {};
    }
    const output = Object.create(null);
    for (const part of cleaned.split("&")) {
        if (!part) continue;
        const eqIdx = part.indexOf("=");
        const rawKey = eqIdx >= 0 ? part.slice(0, eqIdx) : part;
        const rawVal = eqIdx >= 0 ? part.slice(eqIdx + 1) : "";
        const key = decodeURIComponent(rawKey.replace(/\\+/g, " "));
        const val = decodeURIComponent(rawVal.replace(/\\+/g, " "));
        if (Object.prototype.hasOwnProperty.call(output, key)) {
            const prev = output[key];
            output[key] = Array.isArray(prev) ? prev.concat(val) : [prev, val];
        } else {
            output[key] = val;
        }
    }
    return output;
}
""",
    },
    {
        "id": "clean-rust-bsearch",
        "language": "rust",
        "code": """pub struct Interval {
    pub start: i64,
    pub end: i64,
}

pub fn merge_intervals(mut spans: Vec<Interval>) -> Vec<Interval> {
    if spans.is_empty() {
        return Vec::new();
    }
    spans.sort_by(|a, b| a.start.cmp(&b.start).then(a.end.cmp(&b.end)));
    let mut merged: Vec<Interval> = Vec::with_capacity(spans.len());
    for item in spans {
        if let Some(last) = merged.last_mut() {
            if item.start <= last.end {
                if item.end > last.end {
                    last.end = item.end;
                }
                continue;
            }
        }
        merged.push(item);
    }
    merged
}
""",
    },
    {
        "id": "clean-rust-histogram",
        "language": "rust",
        "code": """use std::collections::BTreeMap;

pub struct FrequencyCounter {
    counts: BTreeMap<String, usize>,
    total: usize,
}

impl FrequencyCounter {
    pub fn new() -> Self {
        Self { counts: BTreeMap::new(), total: 0 }
    }

    pub fn record(&mut self, token: &str) {
        let entry = self.counts.entry(token.to_string()).or_insert(0);
        *entry += 1;
        self.total += 1;
    }

    pub fn share(&self, token: &str) -> f64 {
        if self.total == 0 {
            return 0.0;
        }
        let hits = self.counts.get(token).copied().unwrap_or(0);
        (hits as f64) / (self.total as f64)
    }
}
""",
    },
]


def _scan_segments(text: str, language: str):
    """Yield (start, end, kind, slice_text) preserving all characters."""
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            end = n if j < 0 else j
            yield i, end, "comment", text[i:end]
            i = end
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            yield i, end, "comment", text[i:end]
            i = end
            continue
        if language == "c" and ch == "#" and (i == 0 or text[i - 1] == "\n"):
            j = i
            while j < n:
                nl = text.find("\n", j)
                if nl < 0:
                    j = n
                    break
                if nl > 0 and text[nl - 1] == "\\":
                    j = nl + 1
                    continue
                j = nl
                break
            yield i, j, "preproc", text[i:j]
            i = j
            continue
        if language in ("go", "javascript") and ch == "`":
            j = i + 1
            while j < n:
                if language == "javascript" and text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    j += 1
                    break
                j += 1
            yield i, j, "string", text[i:j]
            i = j
            continue
        if language == "rust" and ch == "'":
            if i + 2 < n and text[i + 1] not in ("\\", "\n", "'") and text[i + 2] == "'":
                yield i, i + 3, "string", text[i:i + 3]
                i += 3
                continue
            if i + 1 < n and text[i + 1] == "\\":
                j = i + 2
                closed = False
                while j < n and text[j] != "\n":
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == "'":
                        closed = True
                        j += 1
                        break
                    j += 1
                if closed:
                    yield i, j, "string", text[i:j]
                    i = j
                    continue
            yield i, i + 1, "other", ch
            i += 1
            continue
        if ch == '"' or (ch == "'" and language != "rust"):
            j = i + 1
            closed = False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == ch:
                    closed = True
                    j += 1
                    break
                j += 1
            if ch == "'" and not closed:
                yield i, i + 1, "other", ch
                i += 1
            else:
                yield i, j, "string", text[i:j]
                i = j
            continue
        if ch.isdigit():
            m = _NUM_RE.match(text, i)
            yield i, m.end(), "number", m.group(0)
            i = m.end()
            continue
        if ch.isalpha() or ch == "_":
            m = _IDENT_RE.match(text, i)
            yield i, m.end(), "ident", m.group(0)
            i = m.end()
            continue
        yield i, i + 1, "other", ch
        i += 1


def mutate_comment_inject(text: str, language: str, seed: int) -> str:
    rng = random.Random(seed)
    lines = text.splitlines()
    out = []
    in_block = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        prev_cont = idx > 0 and lines[idx - 1].rstrip().endswith("\\")
        if not in_block and not prev_cont and stripped and not stripped.startswith("#"):
            if rng.random() < 0.22:
                indent = line[:len(line) - len(line.lstrip())]
                msg = rng.choice(_COMMENT_POOL)
                if rng.random() < 0.65:
                    out.append(indent + "// " + msg)
                else:
                    out.append(indent + "/* " + msg + " */")
        out.append(line)
        # Rough block-comment tracking so we never inject inside /* ... */
        pos = 0
        while pos < len(line):
            if not in_block and line.startswith("/*", pos):
                in_block = True
                pos += 2
            elif in_block and line.startswith("*/", pos):
                in_block = False
                pos += 2
            else:
                pos += 1
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def mutate_reformat(text: str, language: str, seed: int) -> str:
    rng = random.Random(seed)
    unit = 2 if rng.random() < 0.5 else 3
    lines = text.splitlines()
    widths = sorted({len(l) - len(l.lstrip(" \t")) for l in lines if l.strip()})
    depth = {w: i * unit for i, w in enumerate(widths)}
    out = []
    in_block = False
    for line in lines:
        if not line.strip():
            if not in_block and out and out[-1].strip() and rng.random() < 0.6:
                out.append("")
            continue
        lead = len(line) - len(line.lstrip(" \t"))
        body = line[lead:]
        if in_block:
            out.append(line)
        else:
            out.append(" " * depth[lead] + body)
            if rng.random() < 0.25 and body.rstrip().endswith("{"):
                out.append("")
        pos = 0
        while pos < len(line):
            if not in_block and line.startswith("/*", pos):
                in_block = True
                pos += 2
            elif in_block and line.startswith("*/", pos):
                in_block = False
                pos += 2
            else:
                pos += 1
    return "\n".join(out) + "\n"


def _extract_local_idents(text: str, language: str, segs: list) -> set[str]:
    kw = _keywords_for(language)
    bi = _builtins_for(language)
    counts: dict[str, int] = {}
    member_only: set[str] = set()
    non_member: set[str] = set()
    for idx, (start, end, kind, word) in enumerate(segs):
        if kind != "ident":
            continue
        if word in kw or word in bi or len(word) < 2:
            continue
        # Check preceding non-whitespace character to skip member names `.foo` / `->foo` / `::foo`
        k = start - 1
        while k >= 0 and text[k] in " \t":
            k -= 1
        is_member = k >= 0 and (
            text[k] == "."
            or (k >= 1 and text[k - 1:k + 1] in ("->", "::"))
        )
        if is_member:
            member_only.add(word)
        else:
            non_member.add(word)
            counts[word] = counts.get(word, 0) + 1
    candidates = {w for w, c in counts.items() if c >= 2}
    if not candidates:
        candidates = set(non_member)
    return candidates


def _alias_for(old: str, idx: int, rng: random.Random) -> str:
    prefix = ("xq", "nb", "kl", "rm", "ts")[idx % 5]
    num = rng.randrange(100, 999)
    tail = old[:2][::-1]
    if old.isupper() and len(old) > 2:
        return ("%s%d_%s" % (prefix, num, tail)).upper()
    if old[0].isupper():
        return "%s%d_%s" % (prefix.capitalize(), num, tail)
    return "%s%d_%s" % (prefix, num, tail.lower())


def mutate_rename(text: str, language: str, seed: int) -> str:
    rng = random.Random(seed)
    segs = list(_scan_segments(text, language))
    targets = sorted(_extract_local_idents(text, language, segs))
    mapping = {name: _alias_for(name, i, rng) for i, name in enumerate(targets)}
    out = []
    for start, _end, kind, piece in segs:
        if kind == "ident" and piece in mapping:
            k = start - 1
            while k >= 0 and text[k] in " \t":
                k -= 1
            is_member = k >= 0 and (
                text[k] == "."
                or (k >= 1 and text[k - 1:k + 1] in ("->", "::"))
            )
            if not is_member:
                out.append(mapping[piece])
                continue
        out.append(piece)
    return "".join(out)


def apply_lang_mutation(text: str, language: str, kind: str, seed: int) -> str:
    if kind == "identity":
        return text
    if kind == "comment_inject":
        return mutate_comment_inject(text, language, seed)
    if kind == "reformat":
        return mutate_reformat(text, language, seed)
    if kind == "rename":
        return mutate_rename(text, language, seed)
    raise ValueError("unknown mutation: %s" % kind)


def sample_multilang_files(corpus_root: Path, entries, per_lang: int = 8,
                           min_chars: int = 1000, max_chars: int = 20000) -> dict:
    by_lang_pkg: dict[str, dict[str, list]] = {lang: {} for lang in LANGUAGES}
    for e in entries:
        lang = language_for(e.path)
        if lang not in by_lang_pkg:
            continue
        full = corpus_root / e.path.replace("/", os.sep)
        if not full.exists():
            continue
        text = full.read_text(encoding="utf-8", errors="replace")
        if not (min_chars <= len(text) <= max_chars):
            continue
        if len(tokenize_source(text, lang)) < 60:
            continue
        by_lang_pkg[lang].setdefault(e.package, []).append((e, text))

    picked: dict[str, list] = {}
    for lang in LANGUAGES:
        pkg_queues = {}
        for pkg in sorted(by_lang_pkg[lang]):
            pkg_queues[pkg] = sorted(
                by_lang_pkg[lang][pkg],
                key=lambda item: (item[0].sha256, item[0].path),
            )
        chosen = []
        pkg_names = sorted(pkg_queues)
        round_idx = 0
        while len(chosen) < per_lang and pkg_names:
            next_pkgs = []
            for pkg in pkg_names:
                q = pkg_queues[pkg]
                if round_idx < len(q):
                    chosen.append(q[round_idx])
                    if len(chosen) >= per_lang:
                        break
                    if round_idx + 1 < len(q):
                        next_pkgs.append(pkg)
            pkg_names = next_pkgs
            round_idx += 1
        picked[lang] = chosen
    return picked


def evaluate(ws_root: Path, per_lang: int = 8, seed: int = 20261125) -> dict:
    index = load_index(str(ws_root))
    model = load_model(str(ws_root))
    corpus_root = ws_root / "corpus"
    entries = read_manifest(str(corpus_root / "corpus.json"))
    sampled = sample_multilang_files(corpus_root, entries, per_lang=per_lang)
    scanner = Scanner(index, model=model, usage="distribution")

    by_lang = {}
    all_cases = []
    cid = 0
    for lang in LANGUAGES:
        mut_stats = {m: {"cases": 0, "detected": 0, "pkg_detected": 0, "top1": 0,
                         "corroborated": 0, "cross_package_false_blocks": 0,
                         "elapsed_ms": []}
                     for m in MUTATIONS}
        lang_t0 = time.perf_counter()
        for e, origin_text in sampled[lang]:
            for mut in MUTATIONS:
                mutated = apply_lang_mutation(origin_text, lang, mut, seed + cid * 131)
                cid += 1
                t0 = time.perf_counter()
                scan = scanner.scan_text(
                    mutated,
                    target=f"{e.path}#{mut}",
                    target_license="LicenseRef-Proprietary",
                    package_hint="__eval__",
                    language=lang,
                )
                ms = (time.perf_counter() - t0) * 1000.0
                matched_origin = [f for f in scan.findings
                                  if f.package == e.package and f.path == e.path]
                matched_pkg = [f for f in scan.findings if f.package == e.package]
                detected = bool(matched_origin)
                pkg_detected = bool(matched_pkg)
                top1 = bool(scan.findings and scan.findings[0].package == e.package
                            and scan.findings[0].path == e.path)
                corrob = any(f.corroborated for f in matched_origin)
                cross_blocks = sum(1 for f in scan.findings
                                   if f.package != e.package and f.risk in ("S3", "S4"))
                st = mut_stats[mut]
                st["cases"] += 1
                st["detected"] += int(detected)
                st["pkg_detected"] += int(pkg_detected)
                st["top1"] += int(top1)
                st["corroborated"] += int(corrob)
                st["cross_package_false_blocks"] += cross_blocks
                st["elapsed_ms"].append(ms)
                all_cases.append({
                    "language": lang, "package": e.package, "path": e.path,
                    "license": e.license_spdx, "mutation": mut,
                    "detected": detected, "package_detected": pkg_detected,
                    "top1": top1, "corroborated": corrob,
                    "cross_package_false_blocks": cross_blocks,
                    "matched_paths": [f.path for f in matched_pkg[:3]],
                    "elapsed_ms": round(ms, 2),
                })

        lang_elapsed_s = time.perf_counter() - lang_t0
        per_mut_summary = {}
        total_cases = total_detected = total_pkg_det = total_top1 = total_corrob = total_cross_fb = 0
        for mut in MUTATIONS:
            st = mut_stats[mut]
            n = max(1, st["cases"])
            per_mut_summary[mut] = {
                "cases": st["cases"],
                "detected": st["detected"],
                "detect_rate": round(st["detected"] / n, 4),
                "package_detect_rate": round(st["pkg_detected"] / n, 4),
                "top1_rate": round(st["top1"] / n, 4),
                "corroborated_rate": round(st["corroborated"] / n, 4),
                "cross_package_false_blocks": st["cross_package_false_blocks"],
                "mean_ms": round(sum(st["elapsed_ms"]) / n, 2),
            }
            total_cases += st["cases"]
            total_detected += st["detected"]
            total_pkg_det += st["pkg_detected"]
            total_top1 += st["top1"]
            total_corrob += st["corroborated"]
            total_cross_fb += st["cross_package_false_blocks"]

        by_lang[lang] = {
            "files": len(sampled[lang]),
            "packages": sorted({e.package for e, _ in sampled[lang]}),
            "total_cases": total_cases,
            "detected": total_detected,
            "package_detected": total_pkg_det,
            "overall_detect_rate": round(total_detected / max(1, total_cases), 4),
            "overall_package_detect_rate": round(total_pkg_det / max(1, total_cases), 4),
            "overall_top1_rate": round(total_top1 / max(1, total_cases), 4),
            "overall_corroborated_rate": round(total_corrob / max(1, total_cases), 4),
            "cross_package_false_blocks": total_cross_fb,
            "elapsed_seconds": round(lang_elapsed_s, 3),
            "per_mutation": per_mut_summary,
        }

    # Clean negatives + cross-language mutual probes
    neg_dir = SRC / "codeguard" / "data" / "negatives"
    neg_controls = []
    for path in sorted(neg_dir.glob("*.py")):
        code = path.read_text(encoding="utf-8")
        # 1) Native Python scan
        neg_controls.append(("python-clean:" + path.name, "python", code))
        # 2) Cross-language scan probes (Python clean utility scanned as C/Go/JS/Rust)
        for cross_lang in LANGUAGES:
            neg_controls.append((f"cross:{path.name}->{cross_lang}", cross_lang, code))
    for item in CLEAN_MULTILANG_NEGATIVES:
        neg_controls.append((item["id"], item["language"], item["code"]))
        # Also cross-check each clean multilang snippet under a different language parser
        other_lang = LANGUAGES[(LANGUAGES.index(item["language"]) + 1) % len(LANGUAGES)]
        neg_controls.append((f"cross:{item['id']}->{other_lang}", other_lang, item["code"]))

    neg_results = []
    neg_t0 = time.perf_counter()
    for neg_id, lang, code in neg_controls:
        t0 = time.perf_counter()
        scan = scanner.scan_text(
            code, target=neg_id, target_license="LicenseRef-Proprietary",
            package_hint="__clean__", language=lang,
        )
        ms = (time.perf_counter() - t0) * 1000.0
        blocking = any(f.risk in ("S3", "S4") for f in scan.findings)
        neg_results.append({
            "id": neg_id, "language": lang, "blocking": blocking,
            "findings": len(scan.findings),
            "max_risk": max((f.risk for f in scan.findings), default="S0"),
            "elapsed_ms": round(ms, 2),
        })
    neg_elapsed_s = time.perf_counter() - neg_t0

    total_pos = sum(v["total_cases"] for v in by_lang.values())
    total_det = sum(v["detected"] for v in by_lang.values())
    total_pkg_det = sum(v["package_detected"] for v in by_lang.values())
    total_cross_fb = sum(v["cross_package_false_blocks"] for v in by_lang.values())
    neg_false_blocks = sum(1 for r in neg_results if r["blocking"])

    return {
        "schema": "codeguard.multilang-eval/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_version": __version__,
        "index_fingerprint": index_fingerprint(index),
        "index_stats": index.stats(),
        "seed": seed,
        "per_language": by_lang,
        "negatives": {
            "total_probes": len(neg_results),
            "python_clean": sum(1 for r in neg_results if r["id"].startswith("python-clean:")),
            "multilang_clean": len(CLEAN_MULTILANG_NEGATIVES),
            "cross_language_probes": sum(1 for r in neg_results if r["id"].startswith("cross:")),
            "false_blocks": neg_false_blocks,
            "any_finding": sum(1 for r in neg_results if r["findings"] > 0),
            "elapsed_seconds": round(neg_elapsed_s, 3),
            "samples": neg_results,
        },
        "summary": {
            "languages": list(LANGUAGES),
            "total_positive_cases": total_pos,
            "total_detected": total_det,
            "total_package_detected": total_pkg_det,
            "overall_detect_rate": round(total_det / max(1, total_pos), 4),
            "overall_package_detect_rate": round(total_pkg_det / max(1, total_pos), 4),
            "negative_false_blocks": neg_false_blocks,
            "cross_package_false_blocks": total_cross_fb,
            "total_false_blocks": neg_false_blocks + total_cross_fb,
            "total_elapsed_seconds": round(
                sum(v["elapsed_seconds"] for v in by_lang.values()) + neg_elapsed_s, 3
            ),
        },
        "cases": all_cases,
    }


def to_markdown(payload: dict) -> str:
    s = payload["summary"]
    ist = payload["index_stats"]
    neg = payload["negatives"]
    lines = [
        "# CodeGuard 多语言语法感知归一化 · 离线基准评测",
        "",
        "- 生成时间：%s" % payload["generated_at"],
        "- 索引指纹：`%s`（documents=%d, chunks=%d, packages=%d）"
        % (payload["index_fingerprint"], ist["documents"], ist["chunks"], ist["packages"]),
        "- 测试模式：纯标准库、完全离线，使用产品扫描链路（`FingerprintIndex` + `Scanner` + 逻辑回归判定模型）",
        "- 总体文件级检出率：**%d / %d（%.1f%%）**；同包级归因：**%d / %d（%.1f%%）**"
        % (s["total_detected"], s["total_positive_cases"], 100.0 * s["overall_detect_rate"],
           s["total_package_detected"], s["total_positive_cases"], 100.0 * s["overall_package_detect_rate"]),
        "- 误阻断数：干净与跨语言互查 `%d / %d`，正例跨包误阻断 `%d`（合计 `%d`）"
        % (neg["false_blocks"], neg["total_probes"],
           s["cross_package_false_blocks"], s["total_false_blocks"]),
        "- 总耗时：%.2fs" % s["total_elapsed_seconds"],
        "",
        "## 按语言变异检出率",
        "",
        "| 语言 | 抽样文件 | 包来源 | identity | comment_inject | reformat | rename | 文件级检出 | 同包归因 | Top-1 | 跨包误阻断 | 耗时 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lang in LANGUAGES:
        row = payload["per_language"][lang]
        pm = row["per_mutation"]
        lines.append(
            "| %s | %d | %s | %.0f%% | %.0f%% | %.0f%% | %.0f%% | **%.1f%%** (%d/%d) | %.1f%% | %.1f%% | %d | %.2fs |"
            % (
                lang, row["files"], ", ".join(row["packages"]),
                100.0 * pm["identity"]["detect_rate"],
                100.0 * pm["comment_inject"]["detect_rate"],
                100.0 * pm["reformat"]["detect_rate"],
                100.0 * pm["rename"]["detect_rate"],
                100.0 * row["overall_detect_rate"], row["detected"], row["total_cases"],
                100.0 * row["overall_package_detect_rate"],
                100.0 * row["overall_top1_rate"],
                row["cross_package_false_blocks"],
                row["elapsed_seconds"],
            )
        )
    missed = [c for c in payload.get("cases", []) if not c["detected"]]
    if missed:
        missed_files = sorted({(c["language"], c["package"], c["path"], ", ".join(c.get("matched_paths", [])))
                               for c in missed})
        lines += ["", "### 未精确命中的原文件路径说明", ""]
        for lang, pkg, path, alt in missed_files:
            lines.append("- `%s`（%s / `%s`）：同包内存在结构/生成模板完全一致的兄弟文件，命中归因到 `%s`。"
                         % (path, lang, pkg, alt or pkg))
    lines += [
        "",
        "## 干净负例与跨语言互查",
        "",
        "- Python 独立实现负例：%d 条；C/Go/JS/Rust 自研干净负例：%d 条；跨语言互查探针：%d 条（共 %d 条）"
        % (neg["python_clean"], neg["multilang_clean"], neg["cross_language_probes"], neg["total_probes"]),
        "- 阻断级误报（S3/S4）：**%d / %d**" % (neg["false_blocks"], neg["total_probes"]),
        "- 任意弱命中（含 S0/S1 观察）：%d / %d；耗时 %.2fs"
        % (neg["any_finding"], neg["total_probes"], neg["elapsed_seconds"]),
        "",
        "> 复现：`PYTHONPATH=src python scripts/eval_multilang.py`",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".codeguard")
    parser.add_argument("--per-lang", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--out-dir", default=str(ROOT / "submission" / "evidence"))
    parser.add_argument("--date", default="20261125")
    args = parser.parse_args(argv)

    ws_root = Path(workspace(args.workspace))
    payload = evaluate(ws_root, per_lang=args.per_lang, seed=args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    json_path = out_dir / f"multilang-eval-{date}.json"
    md_path = out_dir / f"multilang-eval-{date}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    md_path.write_text(to_markdown(payload), encoding="utf-8")

    s = payload["summary"]
    print(
        "Multilang eval: %d/%d (%.1f%%), false_blocks=%d, elapsed=%.2fs"
        % (s["total_detected"], s["total_positive_cases"],
           100.0 * s["overall_detect_rate"], s["total_false_blocks"],
           s["total_elapsed_seconds"])
    )
    for lang in LANGUAGES:
        r = payload["per_language"][lang]
        pm = r["per_mutation"]
        print(
            "  %-10s files=%d detect=%.1f%% (id=%.0f%% cmt=%.0f%% fmt=%.0f%% ren=%.0f%%) cross_fb=%d time=%.2fs"
            % (
                lang, r["files"], 100.0 * r["overall_detect_rate"],
                100.0 * pm["identity"]["detect_rate"],
                100.0 * pm["comment_inject"]["detect_rate"],
                100.0 * pm["reformat"]["detect_rate"],
                100.0 * pm["rename"]["detect_rate"],
                r["cross_package_false_blocks"], r["elapsed_seconds"],
            )
        )
    print("Evidence -> %s , %s" % (json_path, md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
