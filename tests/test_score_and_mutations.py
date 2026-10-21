"""The judge model and the mutation generator are both part of the claim.

AUC, thresholds and reproducibility of the benchmark are checkable here without
touching the corpus, so a reviewer can re-derive every number in the report.
"""

import random
import unittest

from codeguard.mutations import (MUTATIONS, apply_mutation, defined_names,
                                 describe, parses, rename)
from codeguard.score import (FEATURE_NAMES, LogisticRegression, Standardizer,
                             best_threshold, confusion, evaluate, group_split,
                             rank_auc)

SRC = '''"""Docstring."""

INDEX = {}


def fetch(key, default=None):
    value = INDEX.get(key)
    if value is None:
        return default
    return value


class Store:
    def __init__(self, capacity=4):
        self.capacity = capacity
        self.items = []

    def add(self, item):
        self.items.append(item)
        if len(self.items) > self.capacity:
            self.items.pop(0)
        return self.items
'''

# reorder only shuffles *independent simple statements*, so the sample used for
# that family needs a run of plain assignments rather than attribute writes
ASSIGN_RUN = '''"""Sums."""

first = 1
second = 2
third = 3
fourth = 4
fifth = 5


def combine(left, right):
    total = left + right
    scaled = right * 3
    offset = total - 1
    return total + scaled + offset


def other(a, b):
    x = a + b
    y = a - b
    return x * y


def third_one(c):
    m = c * 2
    n = m + 1
    return n
'''


class MutationTests(unittest.TestCase):
    def test_every_family_keeps_the_sample_parseable(self):
        for source in (SRC, ASSIGN_RUN):
            for kind in MUTATIONS:
                for seed in (1, 7, 11, 23):
                    out = apply_mutation(source, kind, seed=seed)
                    self.assertTrue(parses(out), "%s/%d:\n%s" % (kind, seed, out))

    def test_mutation_is_deterministic_for_a_seed(self):
        for kind in MUTATIONS:
            self.assertEqual(apply_mutation(SRC, kind, 11),
                             apply_mutation(SRC, kind, 11), kind)

    def test_seeds_explore_the_mutation_space(self):
        for kind in MUTATIONS:
            if kind == "identity":
                continue
            source = ASSIGN_RUN if kind == "reorder" else SRC
            variants = {apply_mutation(source, kind, seed) for seed in range(1, 25)}
            self.assertGreater(len(variants), 1, "%s ignores its seed" % kind)

    def test_reorder_preserves_every_statement(self):
        out = apply_mutation(ASSIGN_RUN, "reorder", 5)
        self.assertTrue(parses(out))
        self.assertEqual(sorted(l.strip() for l in out.splitlines() if l.strip()),
                         sorted(l.strip() for l in ASSIGN_RUN.splitlines() if l.strip()))

    def test_rename_only_touches_locally_defined_names(self):
        names = defined_names(SRC)
        self.assertIn("fetch", names)
        self.assertIn("capacity", names)
        self.assertNotIn("__init__", names, "dunder names must stay intact")
        out = rename(SRC, random.Random(1))
        self.assertIn('"Docstring."', out, "string content must not be renamed")
        self.assertIn("len(self.items)", out, "builtin calls must stay intact")
        self.assertNotIn("def fetch", out)

    def test_partial_and_dead_code_leave_strictly_more_or_less_code(self):
        partial = apply_mutation(SRC, "partial", 5)
        self.assertLess(len(partial), len(SRC))
        padded = apply_mutation(SRC, "dead_code", 5)
        self.assertGreater(len(padded), len(SRC))

    def test_injected_lines_use_the_files_own_indent_unit(self):
        # a 2-space file must not be re-indented with four spaces: that produced
        # an unparsable compound mutant, i.e. a lexer-fallback measurement
        reformatted = apply_mutation(SRC, "reformat", 3)
        step = min(len(l) - len(l.lstrip()) for l in reformatted.splitlines()
                   if l.strip() and l[:1] == " ")
        self.assertLess(step, 4)
        for seed in range(1, 15):
            out = apply_mutation(reformatted, "comment_inject", seed)
            self.assertTrue(parses(out), "seed %d:\n%s" % (seed, out))

    def test_describe_labels_every_family(self):
        for kind in MUTATIONS:
            self.assertNotEqual(describe(kind), kind, kind)

    def test_unknown_family_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_mutation(SRC, "teleport", 1)


class ScoreTests(unittest.TestCase):
    def test_auc_extremes_and_ties(self):
        self.assertEqual(rank_auc([0.1, 0.2, 0.9], [0, 0, 1]), 1.0)
        self.assertEqual(rank_auc([0.9, 0.8, 0.1], [0, 0, 1]), 0.0)
        self.assertAlmostEqual(rank_auc([0.5, 0.5], [1, 0]), 0.5)

    def test_auc_needs_both_classes(self):
        import math
        self.assertTrue(math.isnan(rank_auc([0.1, 0.2], [0, 0])))

    def test_confusion_counts(self):
        cm = confusion([0.9, 0.4, 0.8, 0.2], [1, 1, 0, 0], 0.5)
        self.assertEqual((cm["tp"], cm["fp"], cm["tn"], cm["fn"]), (1, 1, 1, 1))
        self.assertEqual(cm["precision"], 0.5)
        self.assertEqual(cm["recall"], 0.5)

    def test_best_threshold_separates_cleanly(self):
        scores = [0.05, 0.1, 0.9, 0.95]
        labels = [0, 0, 1, 1]
        thr = best_threshold(scores, labels)
        self.assertTrue(0.1 <= thr <= 0.9)
        self.assertEqual(confusion(scores, labels, thr)["f1"], 1.0)

    def test_group_split_never_shares_a_group(self):
        rows = [[float(i)] * len(FEATURE_NAMES) for i in range(12)]
        labels = [i % 2 for i in range(12)]
        groups = [i // 4 for i in range(12)]
        train, test, held = group_split(rows, labels, groups, frac=0.5, seed=3)
        self.assertFalse(set(train) & set(test))
        self.assertEqual(len(train) + len(test), 12)
        self.assertTrue(all(groups[t] in held for t in test))
        self.assertTrue(all(groups[t] not in held for t in train))

    def test_standardizer_is_mean_zero_unit_variance(self):
        sc = Standardizer().fit([[2.0, 10.0], [4.0, 20.0], [6.0, 30.0]])
        self.assertAlmostEqual(sc.mean[0], 4.0)
        self.assertAlmostEqual(sum(sc.transform([4.0, 20.0])), 0.0)

    def test_model_trains_recovers_and_round_trips(self):
        rng = random.Random(2026)
        rows, labels = [], []
        for _ in range(120):
            label = rng.random() < 0.5
            base = 0.75 if label else 0.15
            rows.append([max(0.0, min(1.0, base + rng.gauss(0, 0.12)))
                         for _ in FEATURE_NAMES])
            labels.append(int(label))
        model = LogisticRegression().fit(rows, labels)
        metrics = evaluate(model, rows, labels, best_threshold(
            [model.score_row(r) for r in rows], labels))
        self.assertGreaterEqual(metrics["auc"], 0.95, metrics)

        clone = LogisticRegression.from_json(model.to_json())
        for row in rows[:20]:
            self.assertAlmostEqual(model.score_row(row), clone.score_row(row), places=5)

    def test_top_features_names_are_the_declared_features(self):
        model = LogisticRegression()
        model.weights = [0.5] + [0.0] * (len(FEATURE_NAMES) - 1)
        self.assertEqual(model.top_features(1)[0]["feature"], FEATURE_NAMES[0])


if __name__ == "__main__":
    unittest.main()
