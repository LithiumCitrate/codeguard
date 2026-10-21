"""A small, explainable classifier: logistic regression trained by SGD.

Deliberately hand-rolled and dependency-free:

* reviewers reproduce training on any machine in well under a second;
* the weights are the explanation, so a match report can say *why* a pair was
  scored the way it was instead of trusting a black box;
* the competition rules explicitly do not reward model size or compute.

Splits are grouped by source file so that near-identical chunks of the same file
cannot appear in both train and test.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field

FEATURE_NAMES = ["j_role", "j_abs", "j_edge", "j_lit", "est_role", "wc",
                 "verbatim_norm", "len_ratio", "band_hits_norm", "lit_minus_role",
                 "max_sim", "mean_sim"]


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


@dataclass
class Standardizer:
    mean: list = field(default_factory=list)
    std: list = field(default_factory=list)

    def fit(self, rows):
        n = len(rows)
        d = len(rows[0]) if n else 0
        self.mean = [sum(r[j] for r in rows) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((r[j] - self.mean[j]) ** 2 for r in rows) / n
            self.std.append(math.sqrt(var) or 1.0)
        return self

    def transform(self, row):
        return [(row[j] - self.mean[j]) / self.std[j] for j in range(len(row))]


@dataclass
class LogisticRegression:
    weights: list = field(default_factory=list)
    bias: float = 0.0
    scaler: Standardizer = field(default_factory=Standardizer)
    feature_names: list = field(default_factory=lambda: list(FEATURE_NAMES))

    def fit(self, rows, labels, epochs: int = 400, lr: float = 0.3,
            l2: float = 1e-3, seed: int = 20260101):
        self.scaler = Standardizer().fit(rows)
        x = [self.scaler.transform(r) for r in rows]
        d = len(x[0])
        rng = random.Random(seed)
        order = list(range(len(x)))
        self.weights = [0.0] * d
        self.bias = 0.0
        n = len(x)
        for epoch in range(epochs):
            rng.shuffle(order)
            total = 0.0
            for i in order:
                row, y = x[i], labels[i]
                p = sigmoid(self.bias + sum(w * v for w, v in zip(self.weights, row)))
                err = p - y
                for j in range(d):
                    self.weights[j] -= lr * (err * row[j] / n + l2 * self.weights[j])
                self.bias -= lr * err / n
                total += -(y * math.log(max(p, 1e-12))
                          + (1 - y) * math.log(max(1 - p, 1e-12)))
        self.train_log_loss = total / max(1, n)
        return self

    def score_row(self, row) -> float:
        z = self.bias + sum(w * v for w, v in zip(self.weights,
                                                   self.scaler.transform(row)))
        return sigmoid(z)

    def top_features(self, k: int = 6):
        pairs = sorted(zip(self.weights, self.feature_names), reverse=True)[:k]
        return [{"feature": name, "weight": round(w, 4)} for w, name in pairs]

    def to_json(self) -> dict:
        return {"model": "logistic-regression-sgd", "features": self.feature_names,
                "weights": [round(w, 6) for w in self.weights],
                "bias": round(self.bias, 6),
                "scaler": {"mean": [round(v, 6) for v in self.scaler.mean],
                           "std": [round(v, 6) for v in self.scaler.std]}}

    @classmethod
    def from_json(cls, payload: dict) -> "LogisticRegression":
        obj = cls()
        obj.feature_names = payload["features"]
        obj.weights = list(payload["weights"])
        obj.bias = payload["bias"]
        obj.scaler = Standardizer(list(payload["scaler"]["mean"]),
                                  list(payload["scaler"]["std"]))
        return obj


def rank_auc(scores, labels) -> float:
    """Mann-Whitney AUC with tie averaging; no scipy needed."""
    pos = [(i, s) for i, s in enumerate(scores) if labels[i] == 1]
    neg = [(i, s) for i, s in enumerate(scores) if labels[i] == 0]
    if not pos or not neg:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    sum_pos = sum(ranks[i] for i, _ in pos)
    return (sum_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg))


def confusion(scores, labels, threshold: float):
    tp = fp = tn = fn = 0
    for s, y in zip(scores, labels):
        pred = 1 if s >= threshold else 0
        if pred and y:
            tp += 1
        elif pred and not y:
            fp += 1
        elif not pred and y:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "specificity": round(specificity, 4)}


def best_threshold(scores, labels):
    """Pick the threshold maximising Youden's J on the supplied data."""
    best, cand = (-1.0, 0.5), sorted(set(scores))
    for t in cand:
        cm = confusion(scores, labels, t)
        j = cm["recall"] + cm["specificity"] - 1.0
        if j > best[0]:
            best = (j, t)
    return round(best[1], 4)


def group_split(rows, labels, groups, frac: float = 0.35, seed: int = 7):
    """Hold out whole groups (source files) for testing."""
    uniq = sorted(set(groups))
    random.Random(seed).shuffle(uniq)
    cut = max(1, int(len(uniq) * frac))
    test_groups = set(uniq[:cut])
    train = [i for i, g in enumerate(groups) if g not in test_groups]
    test = [i for i, g in enumerate(groups) if g in test_groups]
    return train, test, sorted(test_groups)


def evaluate(model, rows, labels, threshold: float) -> dict:
    scores = [model.score_row(r) for r in rows]
    out = confusion(scores, labels, threshold)
    out["auc"] = round(rank_auc(scores, labels), 4)
    out["n"] = len(labels)
    return out
