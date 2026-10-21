"""Roman numerals both ways, table driven."""

PAIRS = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
         (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
         (5, "V"), (4, "IV"), (1, "I"))
VALUES = {symbol: value for value, symbol in PAIRS}


def to_roman(number):
    if not isinstance(number, int) or not 0 < number < 4000:
        raise ValueError("only 1..3999 has a roman form, got %r" % (number,))
    chunks = []
    rest = number
    for value, symbol in PAIRS:
        while rest >= value:
            chunks.append(symbol)
            rest -= value
    return "".join(chunks)


def from_roman(text):
    text = text.strip().upper()
    if not text or any(ch not in VALUES for ch in text):
        raise ValueError("not a roman numeral: %r" % (text,))
    total = 0
    index = 0
    while index < len(text):
        current = VALUES[text[index]]
        following = VALUES[text[index + 1]] if index + 1 < len(text) else 0
        if following > current:
            total += following - current
            index += 2
        else:
            total += current
            index += 1
    return total


def round_trip(number):
    return from_roman(to_roman(number)) == number
