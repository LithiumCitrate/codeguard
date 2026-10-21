"""Count-Min frequency oracle for inverse-document-frequency weighting.

Structurally generic shingles (``call.arity|1``, ``bind|L|L`` and friends) occur
in almost every Python file, so an unweighted Jaccard over them produces noisy
matches. The index therefore records how often each shingle appears across
chunks and down-weights it during verification, while keeping the stored index
size independent of corpus vocabulary growth.
"""

from __future__ import annotations

import array
import base64
import hashlib
import struct
import zlib

_ROWS = 4
_WIDTH = 1 << 16
_MAX_COUNTER = (1 << 32) - 1


class CountMin:
    __slots__ = ("rows", "width", "table", "total")

    def __init__(self, rows=_ROWS, width=_WIDTH):
        self.rows = rows
        self.width = width
        self.table = array.array("I", bytes(4 * rows * width))
        self.total = 0

    def _positions(self, key: int):
        for r in range(self.rows):
            digest = hashlib.blake2b(
                struct.pack("<Q", key), digest_size=8, key=bytes([r]) * 8).digest()
            yield r, struct.unpack("<I", digest[:4])[0] % self.width

    def add(self, key: int, n: int = 1):
        for r, c in self._positions(key):
            idx = r * self.width + c
            cur = self.table[idx]
            if cur + n < _MAX_COUNTER:
                self.table[idx] = cur + n
        self.total += n

    def estimate(self, key: int) -> int:
        return min(self.table[r * self.width + c] for r, c in self._positions(key))

    def to_base64(self) -> str:
        raw = zlib.compress(self.table.tobytes(), 6)
        return base64.b64encode(raw).decode("ascii")

    @classmethod
    def from_base64(cls, payload: str, rows=_ROWS, width=_WIDTH) -> "CountMin":
        obj = cls(rows, width)
        obj.table = array.array("I")
        obj.table.frombytes(zlib.decompress(base64.b64decode(payload)))
        return obj
