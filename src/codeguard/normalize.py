"""Level-aware source normalization.

One token stream feeds four views, each invariant to a different class of
obfuscation:

* ``literal``    - code tokens only; catches verbatim copying.
* ``abstract``   - local identifiers aliased by first appearance, literals
  bucketed; catches renaming and reformatting inside one file.
* ``role``       - identifiers reduced to roles (local/builtin/keyword); the
  comparison basis that stays valid *across* files.
* ``relational`` - unordered role edges and shape n-grams; survives statement
  reordering because downstream hashing treats them as a set.

Comments are removed from every view, so injected commentary can neither create
nor inflate a match; :func:`verbatim_text` is the same comment-free token stream
used for the verbatim-run measurement in :mod:`codeguard.evidence`.
"""

from __future__ import annotations

import builtins
import io
import keyword
import re
import tokenize
from dataclasses import dataclass

BUILTIN_NAMES = frozenset(dir(builtins)) - {"__name__", "__doc__", "__package__"}
KEYWORDS = frozenset(keyword.kwlist)

_IDENT_START = re.compile(r"[A-Za-z_\u0080-\uffff]")
_IDENT_RE = re.compile(r"[A-Za-z_\u0080-\uffff][A-Za-z0-9_\u0080-\uffff]*")
_NUM_RE = re.compile(r"[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][-+]?[0-9]+)?")
_FALLBACK_OPS = ("**=", "//=", "<<=", ">>=", "...", "**", "//", "<<", ">>",
                 "==", "!=", "<=", ">=", ":=", "->", "+=", "-=", "*=", "/=",
                 "%=", "@=", "&=", "|=", "^=", "~=")


def _fallback_tokens(text):
    """Syntax-independent lexer used when ``tokenize`` cannot parse the input.

    Diff hunks, file fragments and non-Python sources are never parseable as a
    module, so the fallback still has to track strings, comments, numbers and
    line numbers correctly - otherwise every span it produces would be junk.
    """
    out = []
    i, line, n = 0, 1, len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in " \t\r\f\v":
            i += 1
            continue
        if ch == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith('"""', i) or text.startswith("'''", i):
            quote = text[i:i + 3]
            j = text.find(quote, i + 3)
            body = text[i:(n if j < 0 else j + 3)]
            out.append(Token(body, line, "string"))
            line += body.count("\n")
            i = n if j < 0 else j + 3
            continue
        prefix = text[max(0, i - 1):i]
        if ch in "\"'" and (not prefix or prefix in " \t=(,[:+%\n"):
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == ch:
                    break
                if text[j] == "\n":
                    break
                j += 1
            body = text[i:min(j + 1, n)]
            out.append(Token(body, line, "string"))
            line += body.count("\n")
            i = j + 1
            continue
        if ch.isdigit():
            m = _NUM_RE.match(text, i)
            out.append(Token(m.group(0), line, "number"))
            i = m.end()
            continue
        if _IDENT_START.match(ch):
            m = _IDENT_RE.match(text, i)
            word = m.group(0)
            kind = "keyword" if keyword.iskeyword(word) else "name"
            out.append(Token(word, line, kind))
            i = m.end()
            continue
        for op in _FALLBACK_OPS:
            if text.startswith(op, i):
                out.append(Token(op, line, "op"))
                i += len(op)
                break
        else:
            out.append(Token(ch, line, "op"))
            i += 1
    return out

_OP_MAP = {"{": "OPEN", "}": "CLOSE", "(": "LP", ")": "RP", "[": "LB", "]": "RB",
           "=": "EQ", ":": "COLON", ":=": "WALRUS", ";": "SEMI"}
_STR_BUCKETS = ((8, "s1"), (24, "s2"), (64, "s3"), (160, "s4"), (4096, "s5"),
                (10 ** 9, "s6"))
_NUM_BUCKETS = ((0, "z0"), (1, "z1"), (10, "z2"), (256, "z3"), (65536, "z4"),
                (10 ** 12, "z5"), (10 ** 400, "z6"))


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    kind: str  # name | keyword | number | string | op | attr


@dataclass
class Span:
    """A sliding window over the normalized streams, carrying evidence locators."""

    start_line: int
    end_line: int
    literal: tuple
    abstract: tuple
    role: tuple
    edges: tuple
    tok_start: int
    tok_end: int

    @property
    def size(self) -> int:
        return self.tok_end - self.tok_start


def tokenize_source(text: str, language: str = "python") -> list:
    """Meaningful tokens, never raising on malformed or partial input."""
    if language != "python":
        return _fallback_tokens(text)
    try:
        raw = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return _fallback_tokens(text)
    out = []
    for tok in raw:
        if tok.type in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
                        tokenize.DEDENT, tokenize.ENDMARKER, tokenize.COMMENT,
                        tokenize.ENCODING):
            continue
        value = tok.string
        if tok.type == tokenize.NAME:
            kind = "keyword" if keyword.iskeyword(value) else "name"
        elif tok.type == tokenize.NUMBER:
            kind = "number"
        elif tok.type == tokenize.STRING:
            kind = "string"
        else:
            kind = "op"
        out.append(Token(value, tok.start[0], kind))
    return out


def _bucket(value: int, buckets) -> str:
    for limit, label in buckets:
        if value <= limit:
            return label
    return buckets[-1][1]


def _number_bucket(text: str) -> str:
    plain = text.replace("_", "")
    try:
        if plain.lower().startswith(("0x", "0b", "0o")):
            return _bucket(len(plain), _NUM_BUCKETS)
        value = float(plain)
    except ValueError:
        return _bucket(len(plain), _NUM_BUCKETS)
    return _bucket(int(abs(value)), _NUM_BUCKETS)


def literal_stream(tokens) -> list:
    return [t.text for t in tokens]


def abstract_stream(tokens) -> list:
    aliases = {}
    out = []
    for tok in tokens:
        if tok.kind == "name":
            if tok.text in BUILTIN_NAMES:
                out.append("B:" + tok.text)
                continue
            alias = aliases.get(tok.text)
            if alias is None:
                alias = "v%d" % len(aliases)
                aliases[tok.text] = alias
            out.append(alias)
        elif tok.kind == "keyword":
            out.append(tok.text)
        elif tok.kind == "number":
            out.append(_number_bucket(tok.text))
        elif tok.kind == "string":
            out.append(_bucket(len(tok.text.lstrip("rbuRBfF")), _STR_BUCKETS))
        else:
            out.append(_OP_MAP.get(tok.text, "PUNCT"))
    return out


def role_stream(tokens) -> list:
    """Rename-invariant view: locals collapse to ``L``, stable names survive."""
    out = []
    for tok in tokens:
        if tok.kind == "name":
            if tok.text in BUILTIN_NAMES:
                out.append("B:" + tok.text)
            elif tok.text.isupper() and len(tok.text) > 2:
                out.append("C")  # module-level constant shape
            elif tok.text[0].isupper():
                out.append("T")  # type-like name
            else:
                out.append("L")
        elif tok.kind == "keyword":
            out.append("K:" + tok.text)
        elif tok.kind == "number":
            out.append(_number_bucket(tok.text))
        elif tok.kind == "string":
            out.append(_bucket(len(tok.text.lstrip("rbuRBfF")), _STR_BUCKETS))
        else:
            out.append(_OP_MAP.get(tok.text, "PUNCT"))
    return out


def _is_term(tok: str) -> bool:
    if not tok or tok in ("OPEN", "CLOSE", "LP", "RP", "LB", "RB", "COLON",
                          "EQ", "SEMI", "WALRUS", "PUNCT"):
        return False
    return True


def relation_edges(roles) -> list:
    """Role-level structural edges, hashed as an unordered set downstream."""
    edges = set()
    n = len(roles)
    i = 0
    while i < n:
        tok = roles[i]
        if tok == "K:def" or tok == "K:class":
            head = roles[i + 1] if i + 1 < n else "?"
            j, depth, params = i + 2, 0, []
            while j < n:
                t = roles[j]
                if t in ("OPEN", "LP", "LB"):
                    depth += 1
                elif t in ("CLOSE", "RP", "RB"):
                    if depth == 0:
                        break
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break   # the header's own bracket just closed
                elif depth >= 1 and _is_term(t):
                    params.append(t)
                j += 1
            edges.add(("%s.arity" % tok[2:], min(len(params), 8)))
            for p in params[:8]:
                edges.add(("%s.sig" % tok[2:], p))
            edges.add(("def.shape", tok[2:], head))
            i = max(j, i + 1)
            continue
        if _is_term(tok) and i + 1 < n and roles[i + 1] == "LP":
            depth, j, args = 0, i + 1, []
            while j < n:
                t = roles[j]
                if t == "LP":
                    depth += 1
                    if depth == 1:
                        j += 1
                        continue
                elif t == "RP":
                    depth -= 1
                    if depth == 0:
                        break
                elif depth >= 1 and _is_term(t):
                    args.append(t)
                j += 1
            edges.add(("call.arity", min(len(args), 8)))
            edges.add(("call.head", tok))
            for a in args[:8]:
                edges.add(("call.arg", a))
            i = max(j, i + 1)
            continue
        if _is_term(tok) and i + 1 < n and roles[i + 1] in ("EQ", "WALRUS"):
            rhs = next((t for t in roles[i + 2:i + 14] if _is_term(t)), "?")
            edges.add(("bind", tok, rhs))
        i += 1
    return sorted("%s|%s|%s" % e if len(e) == 3 else "%s|%s" % e for e in edges)


def shape_ngrams(roles, k: int = 5) -> list:
    """Order-sensitive n-grams over the rename-invariant view."""
    if len(roles) < k:
        return [" ".join(roles)] if roles else []
    return [" ".join(roles[i:i + k]) for i in range(len(roles) - k + 1)]


def verbatim_text(text: str) -> str:
    """Comment-free, whitespace-folded token sequence for verbatim overlap."""
    return " ".join(t.text for t in tokenize_source(text))


def build_spans(text: str, language: str = "python", size: int = 48,
                stride: int = 24) -> list:
    """Slide a token window over the file and canonicalize *within* each window.

    Aliasing per window (rather than per file) makes the abstract layer survive
    insertions elsewhere in the file, which is exactly the dead-code injection
    case a naive global alias table breaks on.
    """
    tokens = tokenize_source(text, language)
    if not tokens:
        return []
    lines = [t.line for t in tokens]
    n = len(tokens)
    starts = list(range(0, max(1, n - size + 1), max(1, stride)))
    if not starts or starts[-1] + size < n:
        starts.append(max(0, n - size))
    spans = []
    for start in starts:
        stop = min(n, start + size)
        if stop - start < 10:
            continue
        window = tokens[start:stop]
        roles = role_stream(window)
        spans.append(Span(lines[start], lines[stop - 1],
                          tuple(literal_stream(window)),
                          tuple(abstract_stream(window)),
                          tuple(roles),
                          tuple(relation_edges(roles)),
                          start, stop))
        if stop == n:
            break
    return spans
