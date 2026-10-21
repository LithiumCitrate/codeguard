"""Merge overlapping time intervals and answer coverage questions."""


def normalise(pairs):
    out = []
    for start, end in pairs:
        if end < start:
            start, end = end, start
        out.append((start, end))
    return out


def merge(pairs, gap=0):
    """Collapse touching ranges; ``gap`` allows near-touching ones too."""
    ordered = sorted(normalise(pairs))
    result = []
    for start, end in ordered:
        if result and start - result[-1][1] <= gap:
            tail_start, tail_end = result[-1]
            result[-1] = (tail_start, max(tail_end, end))
        else:
            result.append((start, end))
    return result


def covered_length(pairs):
    return sum(end - start for start, end in merge(pairs))


def holes(pairs, window):
    """Free ranges inside ``window`` that the pairs do not cover."""
    busy = merge(pairs)
    free, cursor = [], window[0]
    for start, end in busy:
        if start > cursor:
            free.append((cursor, min(start, window[1])))
        cursor = max(cursor, end)
    if cursor < window[1]:
        free.append((cursor, window[1]))
    return free


def overlaps_any(pairs, point):
    return any(start <= point <= end for start, end in normalise(pairs))
