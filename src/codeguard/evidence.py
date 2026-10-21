"""Second-stage verification: exact scoring and human-readable evidence.

LSH proposes candidates; this module confirms them against the corpus source on
disk, which yields (a) exact per-layer Jaccard instead of a sketch estimate,
(b) IDF-weighted containment that ignores structurally generic shingles, and
(c) the longest verbatim token run, the single most persuasive number in a
compliance report.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .fingerprint import span_shingles
from .minhash import containment, jaccard
from .normalize import build_spans

@dataclass
class PairScore:
    span_ordinal: int
    chunk_index: int
    doc_id: int
    line_start: int
    line_end: int
    band_hits: int
    estimates: dict
    exact: dict
    weighted_containment: float
    verbatim_run: int
    matched_lines: int
    features: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"span": self.span_ordinal, "chunk": self.chunk_index,
                "doc": self.doc_id, "lines": [self.line_start, self.line_end],
                "band_hits": self.band_hits, "exact": self.exact,
                "estimates": self.estimates,
                "weighted_containment": round(self.weighted_containment, 4),
                "verbatim_run": self.verbatim_run,
                "matched_lines": self.matched_lines}


class CandidateReader:
    """Cache corpus files and their spans for exact verification."""

    def __init__(self, index):
        self.index = index
        self._spans = {}
        self._shingles = {}

    def spans_for(self, doc_id: int):
        if doc_id not in self._spans:
            path = self.index.corpus_file(self.index.doc_for(doc_id))
            text = read_source(path)
            self._spans[doc_id] = build_spans(
                text, self.index.doc_for(doc_id).language,
                self.index.params.window, self.index.params.stride) if text else []
            self._shingles[doc_id] = [span_shingles(s) for s in self._spans[doc_id]]
        return self._spans[doc_id], self._shingles[doc_id]

    def overlapping(self, doc_id: int, line_start: int, line_end: int):
        spans, shingles = self.spans_for(doc_id)
        picked = [(s, sh) for s, sh in zip(spans, shingles)
                  if not (s.end_line < line_start or s.start_line > line_end)]
        if not picked and spans:
            mid = (line_start + line_end) // 2
            picked = sorted(zip(spans, shingles),
                            key=lambda p: abs(p[0].start_line - mid))[:1]
        return picked


def read_source(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def union_shingles(shingle_list, layer: str) -> set:
    out = set()
    for sh in shingle_list:
        out |= sh[layer]
    return out


def longest_common_run(a_tokens, b_tokens, max_run: int = 120) -> int:
    """Largest number of consecutive code tokens shared by both fragments.

    Found by binary searching the n-gram length, so it costs O(n log n) rather
    than the O(n^2) of a suffix-table approach.
    """
    a, b = list(a_tokens), list(b_tokens)
    if not a or not b:
        return 0
    b_cache = {}

    def grams(tokens, k):
        if k <= 1:
            return set(tokens)
        return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}

    def shared(k):
        if k not in b_cache:
            b_cache[k] = grams(b, k)
        return not b_cache[k].isdisjoint(grams(a, k))

    lo, hi, best = 1, min(max_run, len(a), len(b)), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if shared(mid):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def containment_of(query: set, target: set) -> float:
    return containment(query, target)


def weighted_containment(index, query: set, target: set) -> float:
    """IDF-weighted share of the query that is present in the target."""
    if not query:
        return 0.0
    total = 0.0
    hit = 0.0
    for sh in query:
        w = index.idf_weight(sh)
        total += w
        if sh in target:
            hit += w
    return hit / total if total else 0.0


def score_pair(index, reader: CandidateReader, ord_no: int, span, fp,
               chunk, band_hits: int, use_idf: bool = True) -> PairScore:
    picked = reader.overlapping(chunk.doc_id, chunk.line_start, chunk.line_end)
    exact = {}
    for layer in ("role", "abs", "edge", "lit"):
        target = union_shingles([sh for _, sh in picked], layer)
        exact[layer] = round(jaccard(fp.shingles[layer], target), 4)
    query_key = fp.shingles["role"] | fp.shingles["abs"]
    target_key = union_shingles([sh for _, sh in picked], "role") | \
        union_shingles([sh for _, sh in picked], "abs")
    wc = (weighted_containment(index, query_key, target_key) if use_idf
          else containment_of(query_key, target_key))
    verbatim = longest_common_run(list(span.literal),
                                  [t for s, _ in picked for t in s.literal])
    estimates = {layer: (index.sketch_estimate(chunk, fp, layer)
                         if layer in index.params.active_layers else 0.0)
                 for layer in ("role", "abs", "edge")}
    matched_lines = (max(s.end_line for s, _ in picked)
                     - min(s.start_line for s, _ in picked) + 1) if picked else 0
    feats = pair_features(exact, estimates, wc, verbatim, span, picked, band_hits)
    return PairScore(ord_no, chunk.index, chunk.doc_id,
                     min([s.start_line for s, _ in picked], default=chunk.line_start),
                     max([s.end_line for s, _ in picked], default=chunk.line_end),
                     band_hits, estimates, exact, wc, verbatim, matched_lines, feats)


def pair_features(exact, estimates, weighted_containment, verbatim_run, span,
                  picked, band_hits) -> dict:
    """Feature vector consumed by the classifier in :mod:`codeguard.score`."""
    cand_tokens = sum(len(s.abstract) for s, _ in picked) or 1
    ratio = min(len(span.abstract), cand_tokens) / max(len(span.abstract), cand_tokens)
    return {
        "j_role": exact["role"],
        "j_abs": exact["abs"],
        "j_edge": exact["edge"],
        "j_lit": exact["lit"],
        "est_role": round(estimates["role"], 4),
        "wc": round(weighted_containment, 4),
        "verbatim_norm": round(min(1.0, verbatim_run / 60.0), 4),
        "verbatim_run": verbatim_run,
        "len_ratio": round(ratio, 4),
        "band_hits_norm": round(band_hits / 30.0, 4),
        "lit_minus_role": round(exact["lit"] - exact["role"], 4),
        "max_sim": round(max(exact["role"], exact["abs"], exact["edge"]), 4),
        "mean_sim": round((exact["role"] + exact["abs"] + exact["edge"]) / 3.0, 4),
    }
