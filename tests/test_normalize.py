"""Layer invariances of the normaliser - the claims the design rests on."""

import unittest

from codeguard.mutations import apply_mutation
from codeguard.normalize import (abstract_stream, build_spans, literal_stream,
                                 relation_edges, role_stream, tokenize_source,
                                 verbatim_text)

SRC = '''"""Short sample module used by the tests."""
import os


def compute_ratio(total, count, label="value"):
    # a comment that must never influence the fingerprint
    if count == 0:
        return 0.0
    ratio = total / count
    print(label, ratio)
    return ratio
'''


class TokenizeTests(unittest.TestCase):
    def test_comments_are_dropped_everywhere(self):
        joined = " ".join(literal_stream(tokenize_source(SRC)))
        self.assertNotIn("must never influence", joined)
        self.assertNotIn("must never influence", verbatim_text(SRC))

    def test_fallback_lexer_tracks_line_numbers_on_partial_input(self):
        truncated = SRC[:200]                # not parseable as a module
        toks = tokenize_source(truncated, language="generic")
        self.assertGreater(len(toks), 5)
        self.assertGreater(max(t.line for t in toks), 1)
        self.assertTrue(all(t.kind in ("name", "keyword", "number", "string",
                                       "op", "attr") for t in toks))

    def test_string_contents_are_one_token(self):
        toks = tokenize_source('x = "hello world"')
        self.assertEqual([t.text for t in toks if t.kind == "string"],
                         ['"hello world"'])

    def test_numbers_and_names_keep_source_lines(self):
        toks = tokenize_source("a = 1\nb = 2\nc = 3\n")
        self.assertEqual([t.line for t in toks if t.text in ("1", "2", "3")],
                         [1, 2, 3])


class InvarianceTests(unittest.TestCase):
    def spans(self, text, size=48, stride=24):
        out = build_spans(text, "python", size, stride)
        self.assertTrue(out, "expected at least one span")
        return out

    def test_role_and_abstract_layers_are_invariant_to_renaming(self):
        mutated = apply_mutation(SRC, "rename", 12345)
        self.assertNotEqual(mutated, SRC)    # the mutation really happened
        self.assertEqual(self.spans(SRC)[0].role, self.spans(mutated)[0].role)
        self.assertEqual(self.spans(SRC)[0].abstract, self.spans(mutated)[0].abstract)

    def test_literal_layer_does_change_under_renaming(self):
        self.assertNotEqual(self.spans(SRC)[0].literal,
                            self.spans(apply_mutation(SRC, "rename", 999))[0].literal)

    def test_reordering_statements_keeps_the_edge_set(self):
        swapped = SRC.replace("    ratio = total / count\n    print(label, ratio)\n",
                              "    print(label, ratio)\n    ratio = total / count\n")
        self.assertNotEqual(swapped, SRC)
        self.assertEqual(set(self.spans(SRC)[0].edges),
                         set(self.spans(swapped)[0].edges))

    def test_edges_are_role_level_and_rename_invariant(self):
        edges = relation_edges(role_stream(tokenize_source(SRC)))
        self.assertTrue(any(e.startswith("call.head|") for e in edges))
        renamed = relation_edges(role_stream(tokenize_source(apply_mutation(SRC, "rename", 7))))
        self.assertEqual(edges, renamed)

    def test_spans_enforce_min_token_size(self):
        for span in self.spans(SRC + "\n" * 3 + "def z(a, b):\n    return a + b\n" * 8):
            self.assertGreaterEqual(len(span.literal), 10)
            self.assertEqual(span.tok_end - span.tok_start, len(span.literal))


if __name__ == "__main__":
    unittest.main()
