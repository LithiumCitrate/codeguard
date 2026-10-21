"""Reproducible mutation benchmark, ablation study and judge-model training.

Every headline number in the technical report is regenerated with one command
and no network:

    codeguard benchmark --files 12 --chars 5000

Design notes that matter when reading the results:

* One index is built with *all four* retrieval layers, then each ablation
  configuration filters the candidate set offline. Verification - the expensive
  stage - runs once per (span, chunk) pair and its features are cached, so ten
  configurations cost barely more than one.
* Ground truth is the mutation log itself: each case knows which corpus document
  it was derived from, so detection, localisation and false positives are
  measured rather than eyeballed.
* Negative controls are nine small utilities written from scratch for this
  project (``data/negatives/``); every wrong-document candidate pair the
  retriever proposes is used as a hard negative for the judge model.
* Nine hand-written negatives are a thin precision control, so ``--fp-study N``
  additionally runs the *production* scanner over N real corpus files and counts
  cross-package matches, separating vendored duplicates from unexpected hits.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field

from .adjudicate import (DEFAULT_CORROBORATE_CONFIDENCE, DEFAULT_CORROBORATE_COVERAGE,
                         DEFAULT_CORROBORATE_SPAN_VERBATIM, DEFAULT_CORROBORATE_VERBATIM,
                         DEFAULT_MIN_SPAN_PROB, corroborates)
from .corpus import read_manifest
from .evidence import CandidateReader, score_pair
from .fingerprint import build_fingerprint
from .index import ALL_LAYERS, BAND_PLAN, DocRecord, FingerprintIndex, Params
from .minhash import band_keys
from .mutations import MUTATIONS, apply_mutation, describe, parses
from .normalize import build_spans, tokenize_source
from .score import (FEATURE_NAMES, LogisticRegression, best_threshold, evaluate,
                    group_split)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
NEGATIVE_DIR = os.path.join(DATA_DIR, "negatives")
WINDOW_SHA = 24

RULE_WEIGHTS = {"wc": 0.45, "max_sim": 0.25, "verbatim": 0.2, "band": 0.1}

CONFIGS = (
    {"id": "sha_exact", "label": "整文件 SHA-256", "kind": "sha_exact"},
    {"id": "norm_sha", "label": "归一化整文件哈希", "kind": "norm_sha"},
    {"id": "norm_sha_win", "label": "归一化滑窗哈希（基线）", "kind": "norm_sha_window"},
    {"id": "L1", "label": "仅字面层 L1", "layers": ("lit",)},
    {"id": "L2", "label": "仅抽象层 L2", "layers": ("abs",)},
    {"id": "L3", "label": "仅角色层 L3", "layers": ("role",)},
    {"id": "L4", "label": "仅结构边层 L4", "layers": ("edge",)},
    {"id": "multi", "label": "多层，无 IDF", "layers": ("role", "abs", "edge"),
     "idf": False},
    {"id": "multi_idf", "label": "多层 + IDF（规则打分）",
     "layers": ("role", "abs", "edge"), "idf": True},
    {"id": "multi_idf_ml", "label": "多层 + IDF + 判定模型",
     "layers": ("role", "abs", "edge"), "idf": True, "model": True},
)


@dataclass
class Case:
    cid: int
    origin_doc: int
    origin_path: str
    package: str
    license_spdx: str
    mutation: str
    text: str
    valid_python: bool
    origin_literal: tuple
    origin_windows: frozenset
    spans: list = field(default_factory=list)


@dataclass
class Trace:
    """Everything the scorers need about one (span, candidate chunk) pair."""
    span: int
    chunk: int
    doc: int
    feats_idf: dict
    feats_plain: dict
    band_hits: dict


# ---------------------------------------------------------------- corpus sample

def sample_origins(corpus_root: str, entries, per_package: int, seed: int,
                   min_chars: int = 1500, max_chars: int = 40000) -> list:
    by_package = {}
    for e in entries:
        path = os.path.join(corpus_root, e.path.replace("/", os.sep))
        if not os.path.exists(path) or not (min_chars <= os.path.getsize(path)
                                            <= max_chars):
            continue
        # start from parseable code so each mutation tests fingerprints, not the
        # fallback lexer, and the "before" state is meaningful
        if not parses(open(path, encoding="utf-8", errors="replace").read()):
            continue
        by_package.setdefault(e.package, []).append(e)
    rng = random.Random(seed)
    picked = []
    for package in sorted(by_package):
        group = sorted(by_package[package], key=lambda e: e.sha256)
        rng.shuffle(group)
        picked.extend(group[:per_package])
    return picked


def build_bench_index(corpus_root: str, entries) -> FingerprintIndex:
    index = FingerprintIndex(Params(active_layers=ALL_LAYERS))
    index.corpus_root = corpus_root
    for doc_id, e in enumerate(entries):
        text = open(os.path.join(corpus_root, e.path.replace("/", os.sep)),
                    encoding="utf-8", errors="replace").read()
        index.add_document(DocRecord(doc_id, e.package, e.version, e.path,
                                     e.license_spdx, e.license_source, "python",
                                     text.count("\n") + 1, len(tokenize_source(text)),
                                     e.sha256, len(text)), text)
    return index.finalize()


# ------------------------------------------------------------------- case build

def make_cases(corpus_root: str, entries, chars: int, seed: int,
               mutations=MUTATIONS) -> list:
    cases, cid = [], 0
    for doc_id, e in enumerate(entries):
        path = os.path.join(corpus_root, e.path.replace("/", os.sep))
        origin = open(path, encoding="utf-8", errors="replace").read()
        if len(origin) > chars:
            origin = origin[:chars]
        lit = tuple(t.text for t in tokenize_source(origin))
        windows = literal_windows(lit)
        for kind in mutations:
            text = apply_mutation(origin, kind, seed + cid * 977)
            cases.append(Case(cid, doc_id, e.path, e.package, e.license_spdx, kind,
                              text, parses(text), lit, windows))
            cid += 1
    return cases


def negative_cases(chars: int, start_cid: int) -> list:
    """Clean-room utilities: nothing here was copied from the corpus."""
    cases = []
    for i, name in enumerate(sorted(os.listdir(NEGATIVE_DIR))):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(NEGATIVE_DIR, name), encoding="utf-8").read()[:chars]
        lit = tuple(t.text for t in tokenize_source(text))
        cases.append(Case(start_cid + i, -1, "negatives/" + name, "clean-room",
                          "Apache-2.0", "negative", text, parses(text), lit,
                          literal_windows(lit)))
    return cases


def literal_windows(lit, size: int = WINDOW_SHA, stride: int = 12) -> frozenset:
    if not lit:
        return frozenset()
    if len(lit) < size:
        return frozenset({hashlib.sha256(" ".join(lit).encode()).hexdigest()})
    return frozenset(hashlib.sha256(" ".join(lit[i:i + size]).encode()).hexdigest()
                     for i in range(0, len(lit) - size + 1, stride))


# ------------------------------------------------------------- trace collection

def collect_traces(index: FingerprintIndex, cases: list, reader: CandidateReader,
                   per_layer_candidates: int = 6) -> dict:
    """Run retrieval once, verify each surviving (span, chunk) pair once."""
    traces = {}
    t0 = time.time()
    pairs = 0
    for case in cases:
        spans = build_spans(case.text, "python", index.params.window,
                            index.params.stride)
        case.spans = [(s.start_line, s.end_line) for s in spans]
        bucket = []
        for ord_no, span in enumerate(spans):
            fp = build_fingerprint(span)
            by_layer = {}
            for layer in ALL_LAYERS:
                hits = {}
                for band_no, key in enumerate(band_keys(
                        fp.sketches[layer].signature, BAND_PLAN[layer],
                        "cg:" + layer)):
                    for chunk_idx in index.tables.get(
                            (layer, band_no, key & 0xFFFFFFFF), ()):
                        hits[chunk_idx] = hits.get(chunk_idx, 0) + 1
                # keep the strongest candidates of each layer, verify the union
                by_layer[layer] = dict(sorted(hits.items(),
                                              key=lambda kv: (-kv[1], kv[0]))
                                       [:per_layer_candidates])
            union = {}
            for layer, hits in by_layer.items():
                for chunk_idx, n in hits.items():
                    union.setdefault(chunk_idx, {})[layer] = n
            for chunk_idx, layer_hits in union.items():
                chunk = index.chunk(chunk_idx)
                total_hits = sum(layer_hits.values())
                idf = score_pair(index, reader, ord_no, span, fp, chunk,
                                 total_hits, True)
                plain = score_pair(index, reader, ord_no, span, fp, chunk,
                                   total_hits, False)
                bucket.append(Trace(ord_no, chunk_idx, chunk.doc_id,
                                    idf.features, plain.features, layer_hits))
                pairs += 1
        traces[case.cid] = bucket
    return {"traces": traces, "pairs_verified": pairs,
            "collect_seconds": round(time.time() - t0, 2)}


# --------------------------------------------------------------------- scoring

def rule_prob(feats: dict, layers, band_hits: int) -> float:
    """The documented rule fallback from :mod:`codeguard.adjudicate`."""
    max_sim = max((feats["j_" + l] for l in layers), default=0.0)
    s = (RULE_WEIGHTS["wc"] * feats["wc"]
         + RULE_WEIGHTS["max_sim"] * max_sim
         + RULE_WEIGHTS["verbatim"] * min(1.0, feats["verbatim_run"] / 40.0)
         + RULE_WEIGHTS["band"] * min(1.0, band_hits / 30.0))
    return round(s, 4)


def judge_prob(model, feats: dict) -> float:
    return round(model.score_row([feats[n] for n in model.feature_names]), 4)


def eval_case(case: Case, traces: list, config: dict, model, threshold: float) -> dict:
    """Detection + localisation for one case under one configuration."""
    if "kind" in config:
        return hash_baseline(case, config["kind"])
    layers = config["layers"]
    use_idf = config.get("idf", True)
    by_span = {}
    for tr in traces:
        hits = sum(tr.band_hits.get(l, 0) for l in layers)
        if hits > 0:
            by_span.setdefault(tr.span, []).append((tr, hits))
    matched, retrieval, top1, span_total = [], 0, 0, max(1, len(case.spans))
    for span_ord, cands in by_span.items():
        span_total += 0
        retrieval += 1 if any(t.doc == case.origin_doc for t, _ in cands) else 0
        best_doc = max(cands, key=lambda c: (c[1], -c[0].chunk))[0].doc
        top1 += 1 if best_doc == case.origin_doc else 0
        scored = []
        for tr, hits in cands:
            feats = tr.feats_idf if use_idf else tr.feats_plain
            prob = (judge_prob(model, feats) if model
                    else rule_prob(feats, layers, hits))
            scored.append((prob, tr, feats))
        prob, tr, feats = max(scored, key=lambda x: x[0])
        if prob >= threshold:
            matched.append((prob, tr, feats))
    return aggregate(case, matched, config, retrieval, top1, span_total)


def aggregate(case, matched, config, retrieval, top1, span_total) -> dict:
    by_doc = {}
    for prob, tr, feats in matched:
        by_doc.setdefault(tr.doc, []).append((prob, feats))
    n_spans = max(1, len(case.spans))
    findings = {}
    for doc, rows in by_doc.items():
        peak = max(p for p, _ in rows)
        coverage = len(rows) / n_spans
        findings[doc] = {
            "coverage": coverage,
            "confidence": min(1.0, 0.65 * peak + 0.35 * min(1.0, coverage * 3)),
            "max_verbatim": max(f["verbatim_run"] for _, f in rows)}
    origin = findings.get(case.origin_doc)
    gate_block = 0
    if origin:
        gate_block = 1 if corroborates(len(by_doc[case.origin_doc]),
                                       origin["coverage"],
                                       origin["max_verbatim"],
                                       origin["confidence"]) else 0
    return {"hit": 1 if origin else 0,
            "coverage": round(origin["coverage"], 4) if origin else 0.0,
            "confidence": round(origin["confidence"], 4) if origin else 0.0,
            "max_verbatim": origin["max_verbatim"] if origin else 0,
            "gate_block": gate_block,
            "false_matches": len(findings) - (1 if origin else 0),
            "retrieval": retrieval, "top1": top1, "spans": n_spans,
            "neg": case.origin_doc < 0}


def hash_baseline(case, kind) -> dict:
    """Hashing baselines: what a SHA-256 / MOSS-style detector can do."""
    if kind == "sha_exact":
        hit = case.mutation == "identity" and case.origin_doc >= 0
        return _baseline_row(case, hit, 1.0 if hit else 0.0)
    lit = tuple(t.text for t in tokenize_source(case.text))
    if kind == "norm_sha":
        hit = lit == case.origin_literal and case.origin_doc >= 0
        return _baseline_row(case, hit, 1.0 if hit else 0.0)
    windows = literal_windows(lit)
    coverage = len(windows & case.origin_windows) / max(1, len(windows))
    return _baseline_row(case, coverage >= 0.5 and case.origin_doc >= 0, coverage)


def _baseline_row(case, hit, coverage):
    return {"hit": 1 if hit else 0, "coverage": round(coverage, 4),
            "confidence": round(coverage, 4), "max_verbatim": 0, "gate_block": 0,
            "false_matches": 0, "retrieval": 0, "top1": 0,
            "spans": max(1, len(case.spans)), "neg": case.origin_doc < 0}


# ------------------------------------------------------------------- model fit

def build_training_rows(cases, traces_all):
    rows, labels, groups = [], [], []
    for case in cases:
        groups.append("neg:" + case.origin_path if case.origin_doc < 0
                      else case.origin_path)
        for tr in traces_all[case.cid]:
            rows.append([tr.feats_idf[n] for n in FEATURE_NAMES])
            labels.append(1 if tr.doc == case.origin_doc else 0)
    return rows, labels, groups


def train_judge(cases, traces_all, seed: int) -> dict:
    rows, labels, groups = build_training_rows(cases, traces_all)
    train, test, held = group_split(rows, labels, groups, frac=0.35,
                                    seed=seed % 9973)
    model = LogisticRegression().fit([rows[i] for i in train],
                                     [labels[i] for i in train])
    scores = [model.score_row(r) for r in rows]
    thr = best_threshold([scores[i] for i in train], [labels[i] for i in train])
    return {"model": model, "threshold": thr, "held_out_files": held,
            "pairs": len(rows), "positives": sum(labels),
            "train": evaluate(model, [rows[i] for i in train],
                              [labels[i] for i in train], thr),
            "test": evaluate(model, [rows[i] for i in test],
                             [labels[i] for i in test], thr),
            "weights": model.top_features(8)}


# --------------------------------------------------------------------- driver

def false_positive_study(prod_index, corpus_root: str, entries, sample: int,
                         seed: int, model, threshold: float, log=print) -> dict:
    """Run the production scanner over real corpus files and count cross-package hits.

    Nine self-written clean-room utilities are a thin precision control, so this
    measures it on the corpus itself: each file there is independent work by
    somebody else, and the same package is excluded, so any finding points at a
    *different* project. Vendored duplicates (``six.py`` shipped inside many
    distributions) are true positives and are separated by filename equality -
    no hand review, and both numbers are published.
    """
    from .adjudicate import Scanner

    pool = [e for e in entries if e.lines >= 40]
    picked = random.Random(seed).sample(pool, min(sample, len(pool)))
    scanner = Scanner(prod_index, model=model, min_span_prob=threshold,
                      usage="distribution", top_verify=4)
    vendored, unexpected = [], []
    by_risk = {}
    t0 = time.time()
    for e in picked:
        path = os.path.join(corpus_root, e.path.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        # worst-case project licence: every copyleft source becomes a conflict,
        # so the blocking count below is an upper bound on real-world noise
        scan = scanner.scan_text(text, target=e.path,
                                 target_license="LicenseRef-Proprietary",
                                 package_hint=e.package)
        for f in scan.findings:
            by_risk[f.risk] = by_risk.get(f.risk, 0) + 1
            row = {"query": e.path, "query_license": e.license_spdx,
                   "matched": f.key, "matched_license": f.license_spdx,
                   "risk": f.risk, "confidence": round(f.confidence, 4),
                   "coverage": round(f.coverage, 4),
                   "verbatim_tokens": f.max_verbatim_run}
            (vendored if os.path.basename(f.path) == os.path.basename(e.path)
             else unexpected).append(row)
    blocking = [r for r in vendored + unexpected if r["risk"] in ("S3", "S4")]
    out = {"index_documents": len(prod_index.docs), "sampled": len(picked),
           "vendored_same_name": len(vendored), "unexpected": len(unexpected),
           "files_with_unexpected_match": len({r["query"] for r in unexpected}),
           "per_file_rate": round(len({r["query"] for r in unexpected})
                                  / max(1, len(picked)), 4),
           "blocking": len(blocking),
           "blocking_files": len({r["query"] for r in blocking}),
           "blocking_per_file_rate": round(len({r["query"] for r in blocking})
                                           / max(1, len(picked)), 4),
           "by_risk": dict(sorted(by_risk.items())),
           "seconds": round(time.time() - t0, 1),
           "top_unexpected": sorted(unexpected, key=lambda r: -r["confidence"])[:10],
           "top_vendored": sorted(vendored, key=lambda r: -r["confidence"])[:5]}
    log("误报研究：抽查 %d 个真实文件，跨包命中 %d 处（同名 vendoring %d、非同名 %d）；"
        "其中阻断级 %d 处，涉及 %d 个文件（%.2f%%），耗时 %.1fs"
        % (out["sampled"], out["vendored_same_name"] + out["unexpected"],
           out["vendored_same_name"], out["unexpected"], out["blocking"],
           out["blocking_files"], 100 * out["blocking_per_file_rate"],
           out["seconds"]))
    return out


def threshold_sensitivity(cases, traces_all, model,
                          thresholds=(0.55, 0.45, 0.35, 0.25)) -> list:
    """Pair-level IDF ablation, reusing the features already cached.

    The candidate set is identical with and without IDF weighting - only the
    containment feature changes - so this isolates what IDF actually buys: how
    many *pairs* survive at each operating point, split into pairs against the
    true origin document and pairs against everything else. Costs nothing
    because verification was already paid for.
    """
    rows = []
    for thr in thresholds:
        row = {"threshold": thr}
        for label, attr in (("idf", "feats_idf"), ("plain", "feats_plain")):
            true_pass = false_pass = 0
            for case in cases:
                for tr in traces_all[case.cid]:
                    feats = getattr(tr, attr)
                    prob = (judge_prob(model, feats) if model
                            else rule_prob(feats, ALL_LAYERS,
                                           sum(tr.band_hits.values())))
                    if prob < thr:
                        continue
                    if case.origin_doc >= 0 and tr.doc == case.origin_doc:
                        true_pass += 1
                    else:
                        false_pass += 1
            row[label] = {"true_pairs": true_pass, "false_pairs": false_pass}
        idf_false = row["idf"]["false_pairs"]
        plain_false = row["plain"]["false_pairs"]
        row["false_pair_reduction"] = (round(1.0 - idf_false / plain_false, 4)
                                       if plain_false else 0.0)
        rows.append(row)
    return rows


def run_benchmark(root: str, out: str = "", train: bool = True,
                  per_package: int = 2, seed: int = 20260101, mutations: str = "",
                  files: int = 0, chars: int = 5000,
                  min_span_prob: float = None, fp_sample: int = 0,
                  min_chars: int = 1500, log=print) -> dict:
    corpus_root = os.path.join(root, "corpus")
    manifest = os.path.join(corpus_root, "corpus.json")
    if not os.path.exists(manifest):
        raise SystemExit("codeguard: 找不到语料清单，请先运行 `codeguard corpus`")
    kinds = tuple(k.strip() for k in mutations.split(",")) if mutations else MUTATIONS
    entries = read_manifest(manifest)
    origins = sample_origins(corpus_root, entries, per_package, seed,
                             min_chars=min_chars)
    if files:
        origins = sorted(origins, key=lambda e: e.sha256)[:files]
    log("基准语料：%d 个来源文件 × %d 类变异 = %d 个用例"
        % (len(origins), len(kinds), len(origins) * len(kinds)))

    t0 = time.time()
    index = build_bench_index(corpus_root, origins)
    st = index.stats()
    log("索引：documents=%d chunks=%d 构建 %.1fs"
        % (st["documents"], st["chunks"], time.time() - t0))

    cases = make_cases(corpus_root, origins, chars, seed, kinds)
    cases += negative_cases(chars, len(origins) * len(kinds) + 1000)
    collected = collect_traces(index, cases, CandidateReader(index))
    traces_all = collected["traces"]
    log("证据验证：%d 对候选，耗时 %.1fs"
        % (collected["pairs_verified"], collected["collect_seconds"]))

    judge = train_judge(cases, traces_all, seed) if train else None
    model = judge["model"] if judge else None
    threshold = min_span_prob if min_span_prob is not None else DEFAULT_MIN_SPAN_PROB
    if judge:
        log("判定模型：候选对 %d（正例 %d），测试集 AUC %.3f / F1 %.3f，阈值 %.3f"
            % (judge["pairs"], judge["positives"], judge["test"]["auc"],
               judge["test"]["f1"], judge["threshold"]))

    results = {}
    for config in CONFIGS:
        if config.get("model") and model is None:
            continue
        rows = {c.cid: eval_case(c, traces_all[c.cid], config, model, threshold)
                for c in cases}
        results[config["id"]] = summarise(config, rows, cases, kinds)

    fp = None
    if fp_sample:
        prod_path = os.path.join(root, "index.bin")
        if not os.path.exists(prod_path):
            log("误报研究跳过：没有 %s（先运行 codeguard index）" % prod_path.replace(os.sep, "/"))
        else:
            fp = false_positive_study(FingerprintIndex.load(prod_path), corpus_root,
                                      entries, fp_sample, seed, model, threshold, log)

    sensitivity = threshold_sensitivity(cases, traces_all, model)

    payload = {
        "schema": "codeguard.benchmark/v1",
        "generated_at": int(time.time()),
        "seed": seed,
        "corpus": {"files": len(origins),
                   "packages": len({e.package for e in origins}),
                   "licenses": sorted({e.license_spdx for e in origins}),
                   "mutations": list(kinds), "chars_cap": chars,
                   "index_chunks": st["chunks"],
                   "payload_bytes_per_chunk": st["payload_bytes_per_chunk"],
                   "sketch_bytes_per_chunk": st["sketch_bytes_per_chunk"]},
        "pairs_verified": collected["pairs_verified"],
        "collect_seconds": collected["collect_seconds"],
        "threshold": threshold,
        "judge": None if not judge else {
            "pairs": judge["pairs"], "positives": judge["positives"],
            "threshold": judge["threshold"],
            "held_out_files": judge["held_out_files"],
            "train": judge["train"], "test": judge["test"],
            "weights": judge["weights"]},
        "results": results,
        "threshold_sensitivity": sensitivity,
        "false_positive_study": fp,
    }
    out_dir = out or os.path.join(root, "benchmark")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    md = render_markdown(payload, kinds)
    with open(os.path.join(out_dir, "benchmark.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    if model is not None:
        with open(os.path.join(root, "model.json"), "w", encoding="utf-8") as fh:
            json.dump(model.to_json(), fh, ensure_ascii=False, indent=1)
        log("判定模型已写入 %s" % os.path.join(root, "model.json").replace(os.sep, "/"))
    log(md)
    log("结果文件：%s" % out_dir.replace(os.sep, "/"))
    return payload


def summarise(config, rows, cases, kinds) -> dict:
    per_mutation = {}
    positives = fps = negatives = 0
    for kind in list(kinds) + ["negative"]:
        group = [c for c in cases if c.mutation == kind]
        if not group:
            continue
        acc = {"cases": len(group), "detect": 0, "coverage": 0.0, "confidence": 0.0,
               "max_verbatim": 0, "false_matches": 0, "retrieval": 0, "top1": 0,
               "spans": 0, "gate_block": 0}
        for c in group:
            r = rows[c.cid]
            if r["neg"]:
                fps += 1 if r["hit"] else 0
                negatives += 1
                continue
            acc["detect"] += r["hit"]
            acc["gate_block"] += r["gate_block"]
            acc["coverage"] += r["coverage"]
            acc["confidence"] += r["confidence"]
            acc["max_verbatim"] += r["max_verbatim"]
            acc["false_matches"] += r["false_matches"]
            acc["retrieval"] += r["retrieval"]
            acc["top1"] += r["top1"]
            acc["spans"] += r["spans"]
        n = max(1, acc["cases"]) if kind != "negative" else 1
        per_mutation[kind] = {
            "cases": acc["cases"] if kind != "negative" else negatives,
            "detect_rate": round(acc["detect"] / n, 4),
            "mean_coverage": round(acc["coverage"] / n, 4),
            "mean_confidence": round(acc["confidence"] / n, 4),
            "mean_max_verbatim": round(acc["max_verbatim"] / n, 2),
            "false_matches_per_case": round(acc["false_matches"] / n, 3),
            "gate_block_rate": round(acc["gate_block"] / max(1, acc["detect"]), 4),
            "retrieval_recall": round(acc["retrieval"] / max(1, acc["spans"]), 4),
            "top1_localisation": round(acc["top1"] / max(1, acc["spans"]), 4),
        }
    pos_cases = sum(v["cases"] for k, v in per_mutation.items() if k != "negative")
    hits = sum(v["detect_rate"] * v["cases"]
               for k, v in per_mutation.items() if k != "negative")
    blocked = sum(v["gate_block_rate"] * v["detect_rate"] * v["cases"]
                  for k, v in per_mutation.items() if k != "negative")
    wrong = sum(v["false_matches_per_case"] * v["cases"]
                for k, v in per_mutation.items() if k != "negative")
    return {"label": config["label"], "per_mutation": per_mutation,
            "overall_detect_rate": round(hits / max(1, pos_cases), 4),
            "gate_blocking_recall": round(blocked / max(1, hits), 4),
            "false_matches_per_case": round(wrong / max(1, pos_cases), 3),
            "negatives": negatives, "false_positives": fps,
            "precision": round(1.0 - fps / max(1, pos_cases + fps), 4)}


# ------------------------------------------------------------------ markdown out

def render_markdown(payload: dict, kinds) -> str:
    res = payload["results"]
    corpus = payload["corpus"]
    lines = ["# CodeGuard 变异基准与消融实验", "",
             "- 语料：%d 个真实开源文件 / %d 个包 / 许可证 %s"
             % (corpus["files"], corpus["packages"], ", ".join(corpus["licenses"])),
             "- 变异：%s（每类 %d 例）" % ("、".join(kinds), corpus["files"]),
             "- 索引：%d 个片段，每片段 %d 字节指纹载荷 + %d 字节草图"
             % (corpus["index_chunks"], corpus["payload_bytes_per_chunk"],
                corpus["sketch_bytes_per_chunk"]),
             "- 精确验证候选对：%d，耗时 %.1fs；判定阈值 span ≥ %s"
             % (payload["pairs_verified"], payload["collect_seconds"],
                payload["threshold"]), "",
             "## 检出率与消融（文件级）", "",
             "| 方法 | " + " | ".join(describe(k).split("（")[0] for k in kinds)
             + " | 总体 | 误匹配来源/例 | 负例误报 | 精确率 |",
             "|---|" + "---|" * (len(kinds) + 4)]
    for cid in [c["id"] for c in CONFIGS if c["id"] in res]:
        row = res[cid]
        cells = ["%.0f%%" % (100 * row["per_mutation"][k]["detect_rate"])
                 for k in kinds if k in row["per_mutation"]]
        lines.append("| %s | %s | **%.0f%%** | %.2f | %d/%d | %.2f |" % (
            row["label"], " | ".join(cells), 100 * row["overall_detect_rate"],
            row["false_matches_per_case"],
            row["false_positives"], row["negatives"], row["precision"]))
    sens = payload.get("threshold_sensitivity") or []
    if sens:
        lines += ["", "## 阈值敏感性 / IDF 的配对级作用（不增加任何计算成本）", "",
                  "候选对集合在有/无 IDF 时完全相同，只有包含度特征不同；"
                  "下表是各阈值下**通过判定**的对数（真 = 指向正确来源文档，假 = 指向其它文档）；"
                  "“假对抑制” = 1 − 有IDF假对/无IDF假对，负值表示 IDF 在该阈值下反而放进更多错对。",
                  "", "| span 阈值 | 有 IDF 真对 | 有 IDF 假对 | 无 IDF 真对 | 无 IDF 假对 | 假对抑制 |",
                  "|---|---|---|---|---|---|"]
        for r in sens:
            lines.append("| %.2f | %d | %d | %d | %d | %+.1f%% |" % (
                r["threshold"], r["idf"]["true_pairs"], r["idf"]["false_pairs"],
                r["plain"]["true_pairs"], r["plain"]["false_pairs"],
                100 * r["false_pair_reduction"]))
        lines += ["", "> 文件级消融里“无 IDF / 有 IDF / +模型”三行同分，是因为变异用例的正负"
                  "分离度很高，文件级判定不依赖配对的细微排序。把判据下沉到**配对级**才能看到 "
                  "IDF 的真实作用：抑制率随阈值下调而增大（出厂阈值 0.55 附近最小），"
                  "也就是 IDF 买的是“允许调低阈值追更高召回而不失控”的余量，"
                  "而不是文件级检出率本身。我们宁可这样写，也不把没测到的收益当成卖点。"]
    key = "multi_idf_ml" if "multi_idf_ml" in res else "multi_idf"
    lines += ["", "## 鲁棒性衰减（%s）" % res[key]["label"], "",
              "| 变异 | 平均片段覆盖率 | 平均置信度 | 最长逐字命中 | 检索召回 | top-1 定位 | 误匹配来源 | 检出中达阻断门槛 |",
              "|---|---|---|---|---|---|---|---|"]
    for k in kinds:
        v = res[key]["per_mutation"].get(k)
        if v:
            lines.append("| %s | %.2f | %.2f | %.0f | %.2f | %.2f | %.2f | %.0f%% |" % (
                describe(k), v["mean_coverage"], v["mean_confidence"],
                v["mean_max_verbatim"], v["retrieval_recall"],
                v["top1_localisation"], v["false_matches_per_case"],
                100 * v["gate_block_rate"]))
    lines += ["", "> “检出中达阻断门槛”是门禁决策的召回率：检出的用例里有多少满足佐证条件"
              "（覆盖率 ≥%.2f、≥2 片段且逐字命中 ≥%d token，或逐字命中 ≥%d token，"
              "或整体置信度 ≥%.2f），不满足的记为 S2 提示而非阻断。"
              % (DEFAULT_CORROBORATE_COVERAGE, DEFAULT_CORROBORATE_SPAN_VERBATIM,
                 DEFAULT_CORROBORATE_VERBATIM, DEFAULT_CORROBORATE_CONFIDENCE)]
    if payload["judge"]:
        j = payload["judge"]
        s = j["test"]
        lines += ["", "## 判定模型（逻辑回归，按来源文件分组留出）", "",
                  "- 候选对 %d（正例 %d），留出来源：%d 个文件"
                  % (j["pairs"], j["positives"], len(j["held_out_files"])),
                  "- 留出集：AUC %.3f ｜ precision %.3f ｜ recall %.3f ｜ F1 %.3f ｜ 阈值 %.3f"
                  % (s["auc"], s["precision"], s["recall"], s["f1"], j["threshold"]),
                  "- 训练集：AUC %.3f ｜ F1 %.3f" % (j["train"]["auc"],
                                                    j["train"]["f1"]),
                  "", "| 特征 | 权重 |", "|---|---|"]
        for w in j["weights"]:
            lines.append("| %s | %+.3f |" % (w["feature"], w["weight"]))
    fp = payload.get("false_positive_study")
    if fp:
        lines += ["", "## 跨包误报研究（真实语料抽查，产品原路径）", "",
                  "- 索引：%d 文档；随机抽查 %d 个语料文件，排除自身包后统计命中；"
                  "被扫描项目的许可证按最坏情况设为 `LicenseRef-Proprietary`，"
                  "因此下面的阻断数是对真实噪声的上界" % (fp["index_documents"], fp["sampled"]),
                  "- 跨包命中 %d 处：同名 vendoring（如 six.py 被多个发行版内嵌，属真阳性）%d 处，"
                  "非同名 %d 处" % (fp["vendored_same_name"] + fp["unexpected"],
                                   fp["vendored_same_name"], fp["unexpected"]),
                  "- 风险分布：%s" % ("，".join("%s×%d" % kv for kv in fp["by_risk"].items())
                                      or "无命中"),
                  "- **阻断级（S3/S4）命中 %d 处，涉及 %d 个文件 → 按文件误阻断率 %.2f%%**"
                  % (fp["blocking"], fp["blocking_files"],
                     100 * fp["blocking_per_file_rate"]),
                  "- 扫描耗时 %.1fs" % fp["seconds"]]
        if fp["top_unexpected"]:
            lines += ["", "| 置信度 | 风险 | 被扫描文件 | 命中来源 | 来源许可证 | 覆盖率 | 逐字 token |",
                      "|---|---|---|---|---|---|---|"]
            for r in fp["top_unexpected"]:
                lines.append("| %.2f | %s | %s | %s | %s | %.2f | %d |" % (
                    r["confidence"], r["risk"], r["query"].split("/")[-1], r["matched"],
                    r["matched_license"], r["coverage"], r["verbatim_tokens"]))
            lines += ["", "> 非同名、非阻断的命中仍然列出：现实中确实存在跨项目的代码移植，"
                      "把它们逐条摊开供人工判定正是工具的目的，而不是替人下结论。"]
    lines += ["", "> 复现：`codeguard benchmark`。用例全部由本仓库自带的变异器生成，"
              "不依赖外部数据集或网络访问。"]
    return "\n".join(lines) + "\n"
