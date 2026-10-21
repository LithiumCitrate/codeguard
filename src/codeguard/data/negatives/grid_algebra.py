"""Row-major dense matrices over nested lists - no numpy, on purpose."""


def shape(matrix):
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    return rows, cols


def check_square(matrix):
    width = {len(row) for row in matrix}
    if len(width) != 1:
        raise ValueError("ragged matrix: %s" % sorted(width))
    return len(matrix), width.pop()


def transpose(matrix):
    rows, cols = check_square(matrix)
    return [[matrix[r][c] for r in range(rows)] for c in range(cols)]


def scale(matrix, factor):
    return [[cell * factor for cell in row] for row in matrix]


def add(left, right):
    check_square(left), check_square(right)
    return [[a + b for a, b in zip(lrow, rrow)] for lrow, rrow in zip(left, right)]


def dot(left, right):
    lr, lc = check_square(left)
    rr, rc = check_square(right)
    if lc != rr:
        raise ValueError("inner dimensions disagree: %d vs %d" % (lc, rr))
    out = []
    for row in range(lr):
        line = []
        for col in range(rc):
            total = 0
            for inner in range(lc):
                total += left[row][inner] * right[inner][col]
            line.append(total)
        out.append(line)
    return out


def identity(size):
    return [[1 if i == j else 0 for j in range(size)] for i in range(size)]
