"""Deterministic source mutations used to stress the detector.

The eight families here mirror what a model-generated file actually looks like
when it is derived from an open-source original: identifiers swapped, layout
rewritten, comments invented, helper code padded in, statements re-ordered, or
only part of a function kept. Each mutation is a pure ``str -> str`` function
driven by a seeded ``random.Random`` so the benchmark is reproducible bit for
bit, which is what makes the resulting recall numbers checkable.

Every mutation is verified to keep the sample files *parseable* where possible:
unparseable output would test the fallback lexer instead of the fingerprint, so
:func:`codeguard.benchmark` records the compile status of each mutant.
"""

from __future__ import annotations

import io
import keyword
import random
import re
import tokenize

MUTATIONS = ("identity", "rename", "reformat", "comment_inject", "dead_code",
             "reorder", "partial", "compound")

_COMMENT_POOL = [
    "TODO: refactor later", "NOTE: kept for compatibility",
    "FIXME: this is fragile", "performance tweak", "sanity check before use",
    "handle the edge case reported by users", "align with upstream behaviour",
    "guard against empty input", "legacy path, do not remove",
    "explain what happens when the value is missing",
]

_DEAD_FUNCS = [
    ("_coerce_optional", ["value", "fallback"],
     ["if value is None:", "    return fallback", "return value"]),
    ("_describe_kind", ["obj"], ["return type(obj).__name__.lower()"]),
    ("chunk_pairs", ["items", "size"],
     ["out = []", "i = 0", "while i < len(items):",
      "    out.append(items[i:i + size])", "    i += size", "return out"]),
    ("_safe_len", ["thing"], ["try:", "    return len(thing)",
                              "except TypeError:", "    return 0"]),
    ("merge_defaults", ["mapping", "defaults"],
     ["result = dict(defaults)", "for key in mapping:",
      "    result[key] = mapping[key]", "return result"]),
    ("_is_blank", ["text"], ["if text is None:", "    return True",
                             "return not text.strip()"]),
]

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DEF_RE = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)")
_CLASS_RE = re.compile(r"^class\s+([A-Za-z_]\w*)")
_PARAM_RE = re.compile(r"\(([^)]*)\)")
_ASSIGN_RE = re.compile(r"^([A-Za-z_]\w*)\s*(?::[^=]+)?=(?!=)")
_BLOCK_START_RE = re.compile(r"^(?:@|def\s|class\s|async\s+def\s)")


def _safe_new_name(old: str, index: int, rng) -> str:
    prefix = ("xq", "nb", "kl", "rm", "ts")[index % 5]
    return "%s%d_%s" % (prefix, rng.randrange(100, 999), old[:2][::-1])


def defined_names(text: str) -> set:
    """Identifiers the file itself introduces: defs, classes, params, targets."""
    names = set()
    for line in text.splitlines():
        stripped = line.strip()
        m = _DEF_RE.match(stripped) or _CLASS_RE.match(stripped)
        if m:
            names.add(m.group(1))
            pm = _PARAM_RE.search(stripped)
            if pm:
                for part in pm.group(1).split(","):
                    part = part.strip().lstrip("*").split("=")[0].strip()
                    if part and _IDENT_RE.fullmatch(part) and part != "self":
                        names.add(part)
            continue
        m = _ASSIGN_RE.match(stripped)
        if m:
            names.add(m.group(1))
    return {n for n in names if not keyword.iskeyword(n) and not n.startswith("__")}


def rename(text: str, rng) -> str:
    """Swap every locally defined identifier for an unrelated name.

    Rewriting happens on real token coordinates, so strings and comments are
    never touched - renaming their contents would change behaviour and hide the
    effect we are actually trying to measure.
    """
    mapping = {name: _safe_new_name(name, i, rng)
               for i, name in enumerate(sorted(defined_names(text)))}
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(text).readline)
                if t.type == tokenize.NAME and t.string in mapping]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    lines = text.splitlines(True)
    # rewrite right-to-left per line, so earlier replacements cannot shift
    # the column offsets of later tokens
    for tok in sorted(toks, key=lambda t: (t.start[0], t.start[1]), reverse=True):
        ln, col = tok.start
        line = lines[ln - 1]
        lines[ln - 1] = (line[:col] + mapping[tok.string] + line[col + len(tok.string):])
    return "".join(lines)


def reformat(text: str, rng) -> str:
    """Change layout only: indent unit, blank lines, keyword spacing."""
    unit = 2 if rng.random() < 0.5 else 3
    lines = [l for l in text.splitlines()]
    widths = sorted({len(l) - len(l.lstrip()) for l in lines if l.strip()})
    depth = {w: i * unit for i, w in enumerate(widths)}
    out, blank = [], 0
    for line in lines:
        if not line.strip():
            blank += 1
            if out and out[-1].strip():
                out.append("")
            continue
        indent = len(line) - len(line.lstrip())
        body = line[indent:]
        if rng.random() < 0.3:
            body = re.sub(r"\b([A-Za-z_]\w*)=(?!=)", r"\1 = ", body)
        out.append(" " * depth[indent] + body)
    return "\n".join(out) + "\n"


def _indent_step(text: str) -> str:
    """The file's own indent unit, so injected lines cannot clash with it.

    ``reformat`` may already have switched the source to 2- or 3-space indents,
    and a hard-coded four spaces would make the compound mutant unparsable - we
    would then be measuring a lexer fallback instead of the fingerprint. The
    smallest positive indent is used because continuation lines are indented
    further than any block body, never less.
    """
    indented = [line for line in text.splitlines()
                if line.strip() and line[:1] in (" ", "\t")]
    if not indented:
        return "    "
    first = indented[0][: len(indented[0]) - len(indented[0].lstrip())]
    if "\t" in first:
        return "\t"
    return " " * min(len(line) - len(line.lstrip()) for line in indented)


def comment_inject(text: str, rng) -> str:
    """Add invented comments and docstrings between statements."""
    step = _indent_step(text)
    lines = text.splitlines()
    out = []
    for line in lines:
        if line.strip() and rng.random() < 0.16:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + "# " + rng.choice(_COMMENT_POOL))
        out.append(line)
        if line.rstrip().endswith(":") and _DEF_RE.match(line.lstrip()):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + step + '"""Handle the request and return a result."""')
    return "\n".join(out) + "\n"


def dead_code(text: str, rng) -> str:
    """Pad with plausible but unused helpers - the classic obfuscation."""
    picks = rng.sample(_DEAD_FUNCS, k=min(len(_DEAD_FUNCS), rng.randint(3, 5)))
    blocks = []
    for name, args, body in picks:
        blocks.append("\n\ndef %s(%s):\n    \"\"\"Internal helper.\"\"\"\n%s\n"
                      % (name, ", ".join(args),
                         "\n".join("    " + line for line in body)))
        if rng.random() < 0.4:
            blocks.append("\n\n%s = %d\n" % (name.upper().lstrip("_"),
                                             rng.randint(2, 64)))
    return text.rstrip("\n") + "\n" + "".join(blocks)


def _top_level_blocks(text: str):
    """Split at column-0 definition lines; everything before is the header."""
    lines = text.splitlines(True)
    starts = []
    for i, l in enumerate(lines):
        if not (l.strip() and not l.startswith((" ", "\t", "\f"))):
            continue
        if not _BLOCK_START_RE.match(l):
            continue
        if i and lines[i - 1].lstrip().startswith("@"):
            continue  # keep a decorator attached to the definition it decorates
        starts.append(i)
    if not starts:
        return text, []
    head = "".join(lines[:starts[0]])
    blocks = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        blocks.append("".join(lines[s:end]))
    return head, blocks


def reorder(text: str, rng) -> str:
    """Re-order top-level definitions and independent statements within them."""
    head, blocks = _top_level_blocks(text)
    if len(blocks) > 2:
        order = list(range(len(blocks)))
        rng.shuffle(order)
        blocks = [blocks[i] for i in order]
    return head + "".join(_shuffle_statements(b, rng) for b in blocks)


def _shuffle_statements(block: str, rng) -> str:
    lines = block.splitlines(True)
    if len(lines) < 4:
        return block
    out = list(lines)
    i = 1
    while i < len(out) - 1:
        a, b = out[i], out[i + 1]
        same_indent = (len(a) - len(a.lstrip())) == (len(b) - len(b.lstrip()))
        safe = not any(a.lstrip().startswith(p) or b.lstrip().startswith(p)
                       for p in ("#", "@", "if", "for", "while", "try", "with",
                                 "else", "elif", "except", "finally", "return",
                                 "del", "global", "def", "class"))
        if safe and same_indent and _ASSIGN_RE.match(a.strip()) \
                and _ASSIGN_RE.match(b.strip()) and rng.random() < 0.5:
            out[i], out[i + 1] = b, a
            i += 2
        else:
            i += 1
    return "".join(out)


def partial(text: str, rng) -> str:
    """Keep a contiguous run of whole definitions - partial copying is common."""
    head, blocks = _top_level_blocks(text)
    if not blocks:
        lines = text.splitlines(True)
        return "".join(lines[len(lines) // 3:])
    keep = rng.randint(1, max(1, min(len(blocks), max(2, len(blocks) // 3))))
    start = rng.randrange(0, len(blocks) - keep + 1)
    imports = [l for l in head.splitlines(True)
               if re.match(r"\s*(import|from)\b", l)][:8]
    return "".join(imports) + "".join(blocks[start:start + keep])


def compound(text: str, rng) -> str:
    """Rename + reformat + comments + dead padding, i.e. a real rewrite."""
    return dead_code(comment_inject(reformat(rename(text, rng), rng), rng), rng)


_APPLY = {"rename": rename, "reformat": reformat, "comment_inject": comment_inject,
          "dead_code": dead_code, "reorder": reorder, "partial": partial,
          "compound": compound}


def apply_mutation(text: str, kind: str, seed: int) -> str:
    if kind == "identity":
        return text
    if kind not in _APPLY:
        raise ValueError("unknown mutation %r" % kind)
    return _APPLY[kind](text, random.Random(seed))


def parses(text: str) -> bool:
    try:
        compile(text, "<mutant>", "exec")
        return True
    except (SyntaxError, ValueError):
        return False


def describe(kind: str) -> str:
    """Chinese label used in the results table."""
    return {"identity": "原样复制（对照）", "rename": "全局标识符重命名",
            "reformat": "重排缩进/空格/空行", "comment_inject": "注入注释与文档串",
            "dead_code": "注入未调用的死代码", "reorder": "顶层定义与语句重排",
            "partial": "仅截取部分定义", "compound": "重命名+格式化+注释+死代码"
            }.get(kind, kind)
