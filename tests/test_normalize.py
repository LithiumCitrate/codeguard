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

    def test_non_finite_and_oversized_literals_stay_bucketable(self):
        # third-party sources hold 1e999, nan and 400-digit integers; int() of
        # those raised, which aborted the whole index build
        src = ("def weird(a, b, c):\n"
               "    x = 1e999\n"
               "    y = 1e-3\n"
               "    z = " + "9" * 400 + "\n"
               "    return a + b + c + x + y + z\n")
        roles = role_stream(tokenize_source(src))
        self.assertIn("L", roles)
        self.assertTrue(any(token.startswith("z") for token in roles))
        self.assertTrue(build_spans(src, "python", 48, 24))


class MultilingualFallbackTests(unittest.TestCase):
    """The corpus also carries C/Go/JS/Rust (indexed as ``generic``)."""

    def test_c_style_comments_are_dropped(self):
        src = ("int add(int a, int b) {\n"
               "    // line comment must vanish\n"
               "    /* block comment\n"
               "       spanning lines */\n"
               "    return a + b;\n"
               "}\n")
        joined = " ".join(t.text for t in tokenize_source(src, language="generic"))
        self.assertNotIn("vanish", joined)
        self.assertNotIn("spanning", joined)
        self.assertIn("return", joined)

    def test_c_preprocessor_is_not_swallowed_as_a_comment(self):
        src = "#include <stdio.h>\nint main(void) { return 0; }\n"
        texts = [t.text for t in tokenize_source(src, language="generic")]
        self.assertIn("#", texts)
        self.assertIn("include", texts)
        self.assertIn("stdio", texts)

    def test_python_floor_division_stays_an_operator(self):
        toks = tokenize_source("x = a // b\n", language="python")
        self.assertIn("//", [t.text for t in toks])

    def test_block_comment_preserves_line_numbers(self):
        src = "int a;\n/* one\ntwo\nthree */\nint b;\n"
        b_tok = [t for t in tokenize_source(src, language="generic")
                 if t.text == "b"][0]
        self.assertEqual(b_tok.line, 5)

    def test_language_for_maps_supported_extensions(self):
        from codeguard.adjudicate import language_for
        self.assertEqual(language_for("a.py"), "python")
        self.assertEqual(language_for("a.pyw"), "python")
        for ext in (".c", ".h", ".cpp", ".cc", ".hpp"):
            self.assertEqual(language_for("mod" + ext), "c")
        self.assertEqual(language_for("srv.go"), "go")
        for ext in (".js", ".mjs", ".ts", ".jsx", ".tsx"):
            self.assertEqual(language_for("app" + ext), "javascript")
        self.assertEqual(language_for("lib.rs"), "rust")
        self.assertEqual(language_for("notes.txt"), "generic")

    def test_language_specific_keywords_and_builtins(self):
        c_toks = tokenize_source("static int f(size_t n) { printf(\"x\"); return 0; }\n", "c")
        c_kinds = {t.text: t.kind for t in c_toks}
        self.assertEqual(c_kinds["static"], "keyword")
        self.assertEqual(c_kinds["return"], "keyword")
        c_roles = role_stream(c_toks, language="c")
        self.assertIn("B:size_t", c_roles)
        self.assertIn("B:printf", c_roles)

        go_toks = tokenize_source("func run(n int) { s := make([]int, n); fmt.Println(len(s)) }\n", "go")
        go_kinds = {t.text: t.kind for t in go_toks}
        self.assertEqual(go_kinds["func"], "keyword")
        go_roles = role_stream(go_toks, language="go")
        self.assertIn("K:func", go_roles)
        self.assertIn("B:make", go_roles)
        self.assertIn("B:len", go_roles)

        js_toks = tokenize_source("function deb(fn) { const t = setTimeout(fn, 10); console.log(t); }\n", "javascript")
        js_kinds = {t.text: t.kind for t in js_toks}
        self.assertEqual(js_kinds["function"], "keyword")
        self.assertEqual(js_kinds["const"], "keyword")
        js_roles = role_stream(js_toks, language="javascript")
        self.assertIn("K:function", js_roles)
        self.assertIn("B:setTimeout", js_roles)
        self.assertIn("B:console", js_roles)

        rs_src = "pub fn parse<'a>(input: &'a str) -> Option<Vec<String>> { let ch = 'x'; println!(\"{}\", input); None }\n"
        rs_toks = tokenize_source(rs_src, "rust")
        rs_kinds = {t.text: t.kind for t in rs_toks}
        self.assertEqual(rs_kinds["fn"], "keyword")
        self.assertEqual(rs_kinds["let"], "keyword")
        self.assertIn("'x'", [t.text for t in rs_toks if t.kind == "string"])
        rs_roles = role_stream(rs_toks, language="rust")
        self.assertIn("K:fn", rs_roles)
        self.assertIn("B:Option", rs_roles)
        self.assertIn("B:Vec", rs_roles)

    def test_multilang_definition_edges_survive_rename_and_reorder(self):
        go_a = "func helper(x int, y string) int {\n    res := len(y)\n    return res + x\n}\n"
        go_b = "func renamed_fn(a int, b string) int {\n    total := len(b)\n    return total + a\n}\n"
        roles_a = role_stream(tokenize_source(go_a, "go"), language="go")
        roles_b = role_stream(tokenize_source(go_b, "go"), language="go")
        self.assertEqual(roles_a, roles_b)
        edges_a = relation_edges(roles_a)
        edges_b = relation_edges(roles_b)
        self.assertEqual(edges_a, edges_b)
        self.assertIn("def.shape|func|L", edges_a)

        rust_a = (
            "struct Store { count: usize }\n"
            "trait Runner { fn step(&self); }\n"
            "impl Runner for Store {\n"
            "    fn step(&self) { let a = 1; let b = 2; println!(\"{}\", a + b); }\n"
            "}\n"
        )
        rust_reordered = (
            "trait Runner { fn step(&self); }\n"
            "struct Store { count: usize }\n"
            "impl Runner for Store {\n"
            "    fn step(&self) { let b = 2; let a = 1; println!(\"{}\", a + b); }\n"
            "}\n"
        )
        edges_r1 = relation_edges(role_stream(tokenize_source(rust_a, "rust"), language="rust"))
        edges_r2 = relation_edges(role_stream(tokenize_source(rust_reordered, "rust"), language="rust"))
        self.assertEqual(set(edges_r1), set(edges_r2))
        self.assertTrue(any(e.startswith("def.shape|struct|") for e in edges_r1))
        self.assertTrue(any(e.startswith("def.shape|trait|") for e in edges_r1))
        self.assertTrue(any(e.startswith("def.shape|impl|") for e in edges_r1))
        self.assertTrue(any(e.startswith("def.shape|fn|") for e in edges_r1))

        js_src = "function compute(items, scale) { return items.length * scale; }\n"
        js_edges = relation_edges(role_stream(tokenize_source(js_src, "javascript"), language="javascript"))
        self.assertIn("def.shape|function|L", js_edges)
        self.assertIn("function.arity|2", js_edges)

        enum_rs = "enum Mode { Fast, Safe }\n"
        e_edges = relation_edges(role_stream(tokenize_source(enum_rs, "rust"), language="rust"))
        self.assertTrue(any(e.startswith("def.shape|enum|") for e in e_edges))

        go_iface = "type Reader interface { Read(buf []byte) int }\n"
        i_edges = relation_edges(role_stream(tokenize_source(go_iface, "go"), language="go"))
        self.assertTrue(any(e.startswith("def.shape|interface|") for e in i_edges))


class QuerySpanTests(unittest.TestCase):
    def test_query_spans_adds_body_span_past_leading_imports(self):
        from codeguard.normalize import build_query_spans
        snippet = (
            "import json\n"
            "import os\n"
            "import re\n"
            "from pathlib import Path\n"
            "def parse_items(raw_text, limit=10):\n"
            "    out = []\n"
            "    for line in raw_text.splitlines():\n"
            "        out.append(line)\n"
            "    return out[:limit]\n"
        )
        base = build_spans(snippet, "python", 48, 24)
        query = build_query_spans(snippet, "python", 48, 24)
        self.assertEqual(len(base), 1)
        self.assertEqual(len(query), 2)
        self.assertEqual(query[-1].literal[:2], ("def", "parse_items"))

    def test_query_spans_skips_extra_span_when_no_imports(self):
        from codeguard.normalize import build_query_spans
        body_only = "def add(a, b):\n    x = a + b\n    y = x * 2\n    return y\n"
        self.assertEqual(
            len(build_query_spans(body_only, "python", 48, 24)),
            len(build_spans(body_only, "python", 48, 24)),
        )


if __name__ == "__main__":
    unittest.main()
