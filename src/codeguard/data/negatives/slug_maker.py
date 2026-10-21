"""URL slug construction with width-aware truncation."""

import re
import unicodedata

_SPAN = re.compile(r"[^a-z0-9]+")


def fold(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slugify(text, max_width=48, separator="-"):
    lowered = fold(text).casefold()
    core = _SPAN.sub(separator, lowered).strip(separator)
    if len(core) <= max_width:
        return core
    cut = core[:max_width]
    if separator in cut[max_width - len(separator):]:
        cut = cut[: cut.rindex(separator, max_width - len(separator))]
    return cut.rstrip(separator)


def uniquify(base, taken):
    """Append the smallest counter that has not been used yet."""
    if base not in taken:
        return base
    counter = 2
    while "%s-%d" % (base, counter) in taken:
        counter += 1
    return "%s-%d" % (base, counter)


def title_from_slug(slug):
    return " ".join(word.capitalize() for word in slug.split("-"))
