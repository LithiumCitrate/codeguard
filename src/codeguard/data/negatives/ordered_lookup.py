"""Iterative ordered-search helpers (clean-room implementation)."""


def lower_bound(items, wanted, key=None):
    lo, hi = 0, len(items)
    while lo < hi:
        mid = (lo + hi) // 2
        value = items[mid] if key is None else key(items[mid])
        if value < wanted:
            lo = mid + 1
        else:
            hi = mid
    return lo


def contains(items, wanted):
    if not items:
        return False
    return items[lower_bound(items, wanted)] == wanted


def insert_sorted(items, value):
    at = lower_bound(items, value)
    items.insert(at, value)
    return at


def merge_runs(runs):
    """Fold sorted runs into one sorted list without recursion."""
    result = []
    for run in runs:
        for value in run:
            insert_sorted(result, value)
    return result
