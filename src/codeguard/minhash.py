"""Deterministic hashing, MinHash sketches and banding LSH (stdlib only).

No third-party dependency so that any reviewer can reproduce the numbers on a
plain Python install, and so that results are bit-stable across runs.
"""

from __future__ import annotations

import hashlib
import struct

MERINNE = (1 << 61) - 1
_MASK64 = (1 << 64) - 1


def h64(data) -> int:
    """Stable 64-bit hash of a str/bytes value (blake2b, platform independent)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return struct.unpack("<Q", hashlib.blake2b(data, digest_size=8).digest())[0]


def _perm_params(seed: str, count: int):
    """Pairwise-independent (a, b) over GF(MERINNE), generated from ``seed``."""
    out = []
    counter = 0
    while len(out) < count:
        digest = hashlib.blake2b(("%s#%d" % (seed, counter)).encode(),
                                 digest_size=16).digest()
        a = struct.unpack("<Q", digest[:8])[0] % (MERINNE - 1) + 1
        b = struct.unpack("<Q", digest[8:])[0] % MERINNE
        out.append((a, b))
        counter += 1
    return out


class Sketch:
    """MinHash sketch over a set of 64-bit hashes."""

    __slots__ = ("perm", "values", "size")

    def __init__(self, seed: str, size: int = 64):
        self.perm = _perm_params(seed, size)
        self.size = size
        self.values = [MERINNE] * size

    def update(self, hashes):
        perm = self.perm
        values = self.values
        for x in hashes:
            x &= _MASK64
            for i, (a, b) in enumerate(perm):
                v = (a * x + b) % MERINNE
                if v < values[i]:
                    values[i] = v

    @property
    def signature(self) -> list:
        return self.values

    def agreement(self, other) -> float:
        """Fraction of equal positions: unbiased Jaccard estimator."""
        if self.size != other.size:
            raise ValueError("sketch size mismatch")
        same = sum(1 for a, b in zip(self.values, other.values) if a == b)
        return same / self.size

    def to_bytes(self) -> bytes:
        return struct.pack("<%dQ" % self.size, *self.values)

    @classmethod
    def from_bytes(cls, data: bytes, seed: str) -> "Sketch":
        size = len(data) // 8
        obj = cls(seed, size)
        obj.values = list(struct.unpack("<%dQ" % size, data[:size * 8]))
        return obj


def band_keys(signature, bands: int, seed: str):
    """Return one hash key per band for LSH bucketing."""
    rows = len(signature) // bands
    return [h64("%s|%d|%s" % (seed, b,
                              ",".join(map(str, signature[b * rows:(b + 1) * rows]))))
            for b in range(bands)]


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def containment(a: set, b: set) -> float:
    """How much of ``a`` is inside ``b`` — asymmetric, fragment friendly."""
    if not a:
        return 0.0
    return len(a & b) / len(a)
