"""Small fixed-capacity cache with least-recently-used eviction."""


class Ring:
    """Doubly linked record ring, kept explicit so eviction stays O(1)."""

    def __init__(self):
        self.prev = {}
        self.next = {}
        self.newest = None

    def promote(self, token):
        if self.newest == token:
            return
        after = self.next.pop(token, None)
        before = self.prev.pop(token, None)
        if after is not None:
            self.next[before] = after
            self.prev[after] = before
        elif before is not None:
            self.next[before] = None
        self.prev[token] = None
        self.next[token] = self.newest
        if self.newest is not None:
            self.prev[self.newest] = token
        self.newest = token

    def drop_oldest(self):
        tail = self.newest
        while tail is not None and self.next[tail] is not None:
            tail = self.next[tail]
        if tail is None:
            return None
        self.promote(tail)
        del self.next[tail]
        return tail

    def forget(self, token):
        self.promote(token)
        return self.drop_oldest()


class LruStore:
    def __init__(self, capacity=8):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.values = {}
        self.ring = Ring()
        self.misses = 0

    def get(self, token, default=None):
        if token not in self.values:
            self.misses += 1
            return default
        self.ring.promote(token)
        return self.values[token]

    def put(self, token, value):
        if token in self.values:
            self.ring.promote(token)
        elif len(self.values) >= self.capacity:
            victim = self.ring.drop_oldest()
            if victim is not None:
                self.values.pop(victim, None)
        self.values[token] = value
        self.ring.promote(token)
        return self

    def __len__(self):
        return len(self.values)
