"""Call-once-and-maybe-again helpers with linear backoff."""

import time


class Budget:
    """How many attempts remain, and how long to wait before the next one."""

    def __init__(self, attempts=3, base_delay=0.05, growth=2.0, ceiling=1.0):
        self.attempts = attempts
        self.base_delay = base_delay
        self.growth = growth
        self.ceiling = ceiling
        self.used = 0

    def delay(self):
        wait = self.base_delay * (self.growth ** self.used)
        return min(wait, self.ceiling)

    def spend(self):
        self.used += 1
        return self.delay()

    def exhausted(self):
        return self.used >= self.attempts


def call_with_retry(action, predicate=None, sleep=time.sleep, budget=None):
    """Run ``action`` until ``predicate`` accepts the result or budget is spent."""
    budget = budget or Budget()
    last = None
    while True:
        try:
            last = action()
            if predicate is None or predicate(last):
                return last
        except Exception:
            if predicate is not None:
                raise
        if budget.exhausted():
            return last
        sleep(budget.spend())


def until_stable(read_value, rounds=4, tolerance=1e-9):
    seen = [read_value()]
    for _ in range(rounds - 1):
        nxt = read_value()
        if abs(nxt - seen[-1]) <= tolerance:
            return nxt
        seen.append(nxt)
    return seen[-1]
