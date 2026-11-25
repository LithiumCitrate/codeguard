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
import math
import re
import tokenize
from dataclasses import dataclass

BUILTIN_NAMES = frozenset(dir(builtins)) - {"__name__", "__doc__", "__package__"}
KEYWORDS = frozenset(keyword.kwlist)

_LANG_EXT = {
    ".py": "python", ".pyw": "python",
    ".c": "c", ".h": "c", ".cpp": "c", ".cc": "c", ".hpp": "c",
    ".go": "go",
    ".js": "javascript", ".mjs": "javascript", ".ts": "javascript",
    ".jsx": "javascript", ".tsx": "javascript",
    ".rs": "rust",
}

_LANG_KEYWORDS = {
    "c": frozenset({
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if",
        "inline", "int", "long", "register", "restrict", "return", "short",
        "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
        "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
        "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
        "_Static_assert", "_Thread_local",
        "bool", "true", "false", "nullptr", "class", "namespace", "template",
        "typename", "using", "virtual", "override", "final", "public",
        "private", "protected", "friend", "new", "delete", "this", "try",
        "catch", "throw", "constexpr", "noexcept", "operator", "explicit",
        "mutable",
    }),
    "go": frozenset({
        "break", "case", "chan", "const", "continue", "default", "defer",
        "else", "fallthrough", "for", "func", "go", "goto", "if", "import",
        "interface", "map", "package", "range", "return", "select", "struct",
        "switch", "type", "var",
    }),
    "javascript": frozenset({
        "async", "await", "break", "case", "catch", "class", "const",
        "continue", "debugger", "default", "delete", "do", "else", "enum",
        "export", "extends", "false", "finally", "for", "from", "function",
        "if", "implements", "import", "in", "instanceof", "interface", "let",
        "new", "null", "of", "package", "private", "protected", "public",
        "return", "static", "super", "switch", "this", "throw", "true", "try",
        "typeof", "var", "void", "while", "with", "yield", "as", "type",
        "namespace", "declare", "readonly", "abstract", "keyof", "infer",
        "satisfies",
    }),
    "rust": frozenset({
        "as", "async", "await", "break", "const", "continue", "crate", "dyn",
        "else", "enum", "extern", "false", "fn", "for", "if", "impl", "in",
        "let", "loop", "match", "mod", "move", "mut", "pub", "ref", "return",
        "self", "Self", "static", "struct", "super", "trait", "true", "type",
        "unsafe", "use", "where", "while", "abstract", "become", "box", "do",
        "final", "macro", "override", "priv", "try", "typeof", "unsized",
        "virtual", "yield",
    }),
}

_GENERIC_KEYWORDS = frozenset().union(*_LANG_KEYWORDS.values())

_LANG_BUILTINS = {
    "c": frozenset({
        "NULL", "EOF", "stdin", "stdout", "stderr", "errno", "printf",
        "fprintf", "sprintf", "snprintf", "vsnprintf", "scanf", "sscanf",
        "puts", "fputs", "fgets", "fopen", "fclose", "fread", "fwrite",
        "fseek", "ftell", "fflush", "malloc", "calloc", "realloc", "free",
        "memcpy", "memmove", "memset", "memcmp", "strlen", "strcmp",
        "strncmp", "strcpy", "strncpy", "strcat", "strncat", "strchr",
        "strrchr", "strstr", "strdup", "strtol", "strtoul", "atoi", "atol",
        "abort", "exit", "assert", "qsort", "bsearch", "size_t", "ssize_t",
        "ptrdiff_t", "intptr_t", "uintptr_t", "int8_t", "int16_t", "int32_t",
        "int64_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t", "FILE",
        "va_list", "va_start", "va_end", "va_arg", "offsetof", "std",
        "string", "vector", "map", "unordered_map", "set", "pair",
        "shared_ptr", "unique_ptr", "make_shared", "make_unique",
    }),
    "go": frozenset({
        "any", "bool", "byte", "comparable", "complex64", "complex128",
        "error", "float32", "float64", "int", "int8", "int16", "int32",
        "int64", "rune", "string", "uint", "uint8", "uint16", "uint32",
        "uint64", "uintptr", "true", "false", "iota", "nil", "append", "cap",
        "clear", "close", "complex", "copy", "delete", "imag", "len", "make",
        "max", "min", "new", "panic", "print", "println", "real", "recover",
        "fmt",
    }),
    "javascript": frozenset({
        "undefined", "NaN", "Infinity", "globalThis", "window", "document",
        "console", "Math", "JSON", "Object", "Array", "String", "Number",
        "Boolean", "Symbol", "BigInt", "Map", "Set", "WeakMap", "WeakSet",
        "Promise", "RegExp", "Date", "Error", "TypeError", "RangeError",
        "SyntaxError", "Function", "Reflect", "Proxy", "Intl", "Buffer",
        "process", "module", "exports", "require", "setTimeout",
        "clearTimeout", "setInterval", "clearInterval", "fetch", "parseInt",
        "parseFloat", "isNaN", "isFinite", "encodeURIComponent",
        "decodeURIComponent", "ArrayBuffer", "Uint8Array",
    }),
    "rust": frozenset({
        "bool", "char", "str", "i8", "i16", "i32", "i64", "i128", "isize",
        "u8", "u16", "u32", "u64", "u128", "usize", "f32", "f64", "Option",
        "Some", "None", "Result", "Ok", "Err", "Vec", "String", "Box", "Rc",
        "Arc", "Cell", "RefCell", "Mutex", "RwLock", "HashMap", "HashSet",
        "BTreeMap", "BTreeSet", "Cow", "Pin", "PhantomData", "Clone", "Copy",
        "Debug", "Default", "Display", "Drop", "Eq", "PartialEq", "Ord",
        "PartialOrd", "Hash", "Iterator", "IntoIterator", "From", "Into",
        "TryFrom", "TryInto", "AsRef", "AsMut", "Deref", "DerefMut", "Send",
        "Sync", "Sized", "Unpin", "Fn", "FnMut", "FnOnce", "Future",
        "println", "eprintln", "print", "eprint", "format", "write",
        "writeln", "vec", "panic", "assert", "assert_eq", "assert_ne",
        "debug_assert", "unreachable", "unimplemented", "todo", "cfg",
        "derive", "include_str", "drop", "std", "core", "alloc",
    }),
}


def resolve_language(path: str, recorded: str = "") -> str:
    """Resolve source language from file extension, keeping specific recorded tags."""
    import os
    ext = os.path.splitext(path)[1].lower()
    lang = _LANG_EXT.get(ext, "generic")
    if lang == "generic" and recorded:
        return recorded
    return lang


def _keywords_for(language: str) -> frozenset:
    if language == "python":
        return KEYWORDS
    return _LANG_KEYWORDS.get(language, _GENERIC_KEYWORDS)


def _builtins_for(language: str) -> frozenset:
    if language == "python":
        return BUILTIN_NAMES
    return _LANG_BUILTINS.get(language, frozenset())

_IDENT_START = re.compile(r"[A-Za-z_\u0080-\uffff]")
_IDENT_RE = re.compile(r"[A-Za-z_\u0080-\uffff][A-Za-z0-9_\u0080-\uffff]*")
_NUM_RE = re.compile(r"[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][-+]?[0-9]+)?")
_FALLBACK_OPS = ("**=", "//=", "<<=", ">>=", "...", "**", "//", "<<", ">>",
                 "==", "!=", "<=", ">=", ":=", "->", "+=", "-=", "*=", "/=",
                 "%=", "@=", "&=", "|=", "^=", "~=")


def _fallback_tokens(text, language="python"):
    """Syntax-independent lexer used when ``tokenize`` cannot parse the input.

    Diff hunks, file fragments and non-Python sources are never parseable as a
    module, so the fallback still has to track strings, comments, numbers and
    line numbers correctly - otherwise every span it produces would be junk.

    Comment syntax is language-aware. Python drops ``#`` to end of line; the
    C-family sources the corpus also carries (C/Go/JS/Rust, indexed as
    ``generic``) drop ``//`` and ``/* */`` instead and keep a leading ``#`` as a
    preprocessor token rather than swallowing the whole directive. Treating a C
    ``#include`` as a comment used to delete real code from the fingerprint.
    """
    c_style = language != "python"
    kw_set = _keywords_for(language)
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
        if not c_style and ch == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c_style and ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c_style and ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            line += text[i:end].count("\n")
            i = end
            continue
        if c_style and ch == "#":
            out.append(Token("#", line, "op"))
            i += 1
            continue
        if not c_style and (text.startswith('"""', i) or text.startswith("'''", i)):
            quote = text[i:i + 3]
            j = text.find(quote, i + 3)
            body = text[i:(n if j < 0 else j + 3)]
            out.append(Token(body, line, "string"))
            line += body.count("\n")
            i = n if j < 0 else j + 3
            continue
        if c_style and language in ("go", "javascript") and ch == "`":
            j = i + 1
            while j < n:
                if language == "javascript" and text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    break
                j += 1
            body = text[i:min(j + 1, n)]
            out.append(Token(body, line, "string"))
            line += body.count("\n")
            i = j + 1
            continue
        if c_style and language == "rust" and ch == "'":
            # Rust uses `'` for both char literals (`'a'`, `'\n'`) and lifetimes (`'a`).
            if i + 2 < n and text[i + 1] not in ("\\", "\n", "'") and text[i + 2] == "'":
                out.append(Token(text[i:i + 3], line, "string"))
                i += 3
                continue
            if i + 1 < n and text[i + 1] == "\\":
                j = i + 2
                closed = False
                while j < n and text[j] != "\n":
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == "'":
                        closed = True
                        break
                    j += 1
                if closed:
                    out.append(Token(text[i:j + 1], line, "string"))
                    i = j + 1
                    continue
            out.append(Token("'", line, "op"))
            i += 1
            continue
        prefix = text[max(0, i - 1):i]
        if (c_style and ch == '"') or (
                ch in "\"'" and (not prefix or prefix in " \t=(,[:+%\n")):
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
            if c_style and ch == "'" and (j >= n or text[j] != "'"):
                out.append(Token("'", line, "op"))
                i += 1
                continue
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
            kind = "keyword" if word in kw_set else "name"
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
        return _fallback_tokens(text, language)
    try:
        raw = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return _fallback_tokens(text, "python")
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
    except (ValueError, OverflowError):
        # int literals longer than float range raise instead of parsing
        return _bucket(len(plain), _NUM_BUCKETS)
    if not math.isfinite(value):
        # 1e999 / nan are valid Python but have no magnitude to bucket
        return _bucket(len(plain), _NUM_BUCKETS)
    return _bucket(int(abs(value)), _NUM_BUCKETS)


def literal_stream(tokens) -> list:
    return [t.text for t in tokens]


def abstract_stream(tokens, language: str = "python") -> list:
    builtins_set = _builtins_for(language)
    aliases = {}
    out = []
    for tok in tokens:
        if tok.kind == "name":
            if tok.text in builtins_set:
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


def role_stream(tokens, language: str = "python") -> list:
    """Rename-invariant view: locals collapse to ``L``, stable names survive."""
    builtins_set = _builtins_for(language)
    out = []
    for tok in tokens:
        if tok.kind == "name":
            if tok.text in builtins_set:
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


_DEF_ROLES = frozenset({
    "K:def", "K:class",
    "K:func", "K:function", "K:fn",
    "K:struct", "K:interface", "K:impl", "K:enum", "K:trait",
})
_CONTAINER_DEF_ROLES = frozenset({"K:interface", "K:impl", "K:trait"})


def relation_edges(roles) -> list:
    """Role-level structural edges, hashed as an unordered set downstream."""
    edges = set()
    n = len(roles)
    i = 0
    while i < n:
        tok = roles[i]
        if tok in _DEF_ROLES:
            if i + 1 < n and roles[i + 1] == "LP":
                head = "?"
                j = i + 1
            else:
                head = roles[i + 1] if i + 1 < n else "?"
                j = i + 2
            depth, params = 0, []
            while j < n:
                t = roles[j]
                if depth == 0 and t == "OPEN" and tok in _CONTAINER_DEF_ROLES:
                    break
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


def verbatim_text(text: str, language: str = "python") -> str:
    """Comment-free, whitespace-folded token sequence for verbatim overlap."""
    return " ".join(t.text for t in tokenize_source(text, language))


def _make_span(tokens, lines, start: int, stop: int,
               language: str = "python") -> Span:
    window = tokens[start:stop]
    roles = role_stream(window, language=language)
    return Span(lines[start], lines[stop - 1],
                tuple(literal_stream(window)),
                tuple(abstract_stream(window, language=language)),
                tuple(roles),
                tuple(relation_edges(roles)),
                start, stop)


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
        spans.append(_make_span(tokens, lines, start, stop, language=language))
        if stop == n:
            break
    return spans


def _first_non_import_line(text: str) -> int | None:
    """Line number of the first code line past leading docstrings/imports."""
    in_doc = ""
    for ln_no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if in_doc:
            if in_doc in s:
                in_doc = ""
            continue
        if ln_no <= 8 and (s.startswith('"""') or s.startswith("'''")):
            quote = s[:3]
            if s.count(quote) == 1:
                in_doc = quote
            continue
        if s.startswith(("import ", "from ")):
            continue
        return ln_no
    return None


def build_query_spans(text: str, language: str = "python", size: int = 48,
                      stride: int = 24) -> list:
    """Query-side span builder: adds one post-import body span when needed.

    Partial copies and LLM-generated helpers frequently pair a block of
    ``import`` statements with a function lifted from the middle of an upstream
    file. When that pushes the first definition inside the same 48-token window
    as the imports, both LSH Jaccard and containment get diluted. Adding a
    single span anchored at the first non-import definition recovers those
    matches without altering the on-disk index format.
    """
    spans = build_spans(text, language, size, stride)
    if language != "python" or not spans:
        return spans
    first_line = _first_non_import_line(text)
    if first_line is None:
        return spans
    tokens = tokenize_source(text, language)
    body_idx = next((i for i, t in enumerate(tokens) if t.line >= first_line), None)
    if body_idx is None or body_idx == 0:
        return spans
    if any(abs(sp.tok_start - body_idx) <= 4 for sp in spans):
        return spans
    stop = min(len(tokens), body_idx + size)
    if stop - body_idx < 10:
        return spans
    lines = [t.line for t in tokens]
    return spans + [_make_span(tokens, lines, body_idx, stop, language=language)]
