"""Token frequency tables and top-k ranking over plain text."""

import re

_WORD = re.compile(r"[0-9A-Za-z\u00c0-\uffff']{2,}")


def words(text):
    return [m.group(0).lower() for m in _WORD.finditer(text)]


def tally(tokens):
    counts = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def rank(counts, limit=10):
    """Stable ordering: frequency first, then the token itself."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def hapax(counts):
    return sorted(k for k, v in counts.items() if v == 1)


def entropy(counts):
    total = sum(counts.values())
    if not total:
        return 0.0
    import math
    return -sum((v / total) * math.log2(v / total) for v in counts.values() if v)


def summarise(text, limit=5):
    counts = tally(words(text))
    return {"tokens": sum(counts.values()), "distinct": len(counts),
            "top": rank(counts, limit), "entropy": round(entropy(counts), 3)}
