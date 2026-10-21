"""Calendar arithmetic on weekday counts, without external libraries."""

import datetime as _dt

MONTH_DAYS = (31, 28, 31, 30, 31, 31, 30, 31, 30, 31, 31, 30)


def leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    if month == 2 and leap(year):
        return 29
    return MONTH_DAYS[month - 1]


def clamp_day(year, month, day):
    return min(day, days_in_month(year, month))


def month_shift(date, months):
    """Add whole months, snapping to the last valid day of the target month."""
    index = (date.year * 12 + date.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return _dt.date(year, month, clamp_day(year, month, date.day))


def weekday_count(start, end):
    total = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            total += 1
        cursor += _dt.timedelta(days=1)
    return total


def next_workday(date):
    cursor = date + _dt.timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor += _dt.timedelta(days=1)
    return cursor


def quarters_of(year):
    point = _dt.date(year, 1, 1)
    spans = []
    for _ in range(4):
        end = month_shift(point, 3) - _dt.timedelta(days=1)
        spans.append((point, end))
        point = end + _dt.timedelta(days=1)
    return spans
