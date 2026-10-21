"""Multi-layer code fingerprints.

Each span yields four shingle sets at different invariance levels; retrieval
uses the rename-invariant layers, verification re-checks exact overlap so that
false positives from structural coincidence can be suppressed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .minhash import Sketch, h64

LAYER_SIZES = {"role": 64, "abs": 64, "edge": 32, "lit": 32}
BANDS = {"role": 16, "abs": 8}
GRAM_K = {"abs": 5, "role": 5, "lit": 6}
SAMPLE_K = {"role": 32, "abs": 24, "lit": 24, "edge": 24}


def _ngrams(tokens, k: int):
    n = len(tokens)
    if n == 0:
        return
    if n < k:
        yield " ".join(tokens)
        return
    for i in range(n - k + 1):
        yield " ".join(tokens[i:i + k])


def shingle_set(tokens, k: int, tag: str):
    return {h64("%s#%s" % (tag, g)) for g in _ngrams(tokens, k)}


def edge_set(edges, tag: str):
    return {h64("%s#%s" % (tag, e)) for e in edges}


def span_shingles(span) -> dict:
    """Hashed shingle sets for every invariance layer of one span."""
    return {
        "lit": shingle_set(span.literal, GRAM_K["lit"], "L1"),
        "abs": shingle_set(span.abstract, GRAM_K["abs"], "L2"),
        "role": shingle_set(span.role, GRAM_K["role"], "L3"),
        "edge": edge_set(span.edges, "L4"),
    }


def bottom_k(hashes, k: int):
    """Deterministic min-list sample, used for exact overlap verification."""
    return sorted(sorted(hashes)[:k])


@dataclass
class Fingerprint:
    shingles: dict
    sketches: dict
    samples: dict

    def to_record(self) -> dict:
        return {"sketches": {name: sk.signature for name, sk in self.sketches.items()},
                "samples": {name: list(vals) for name, vals in self.samples.items()}}


def build_fingerprint(span) -> Fingerprint:
    sh = span_shingles(span)
    sketches = {}
    for layer, size in LAYER_SIZES.items():
        sk = Sketch("cg:" + layer, size)
        sk.update(sh[layer])
        sketches[layer] = sk
    samples = {layer: bottom_k(sh[layer], SAMPLE_K[layer]) for layer in sh}
    return Fingerprint(sh, sketches, samples)
