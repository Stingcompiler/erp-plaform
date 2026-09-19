"""Gregorian ⇄ Hijri by the tabular (arithmetic) Islamic calendar.

The zakat year is a lunar year, so the report that fixes the hawl date
needs a Hijri date without a network call or a dependency. The tabular
calendar (30-year cycle, leap years 2,5,7,10,13,16,18,21,24,26,29) is the
one printed in almanacs; it can differ from the moon-sighted date by a
day, which is why the report shows the conversion and lets the owner pick
the day.
"""
from datetime import date

MONTHS_AR = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة",
    "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]
MONTHS_EN = [
    "Muharram", "Safar", "Rabi' I", "Rabi' II", "Jumada I", "Jumada II",
    "Rajab", "Sha'ban", "Ramadan", "Shawwal", "Dhu al-Qa'dah", "Dhu al-Hijjah",
]
_LEAP_YEARS = {2, 5, 7, 10, 13, 16, 18, 21, 24, 26, 29}
# Julian day number of 1 Muharram 1 AH: the "astronomical" epoch (Thursday
# 15 July 622 CE, Julian), which tracks Umm al-Qura more closely than the
# civil epoch one day later.
_EPOCH = 1948439


def _jdn(gregorian):
    a = (14 - gregorian.month) // 12
    y = gregorian.year + 4800 - a
    m = gregorian.month + 12 * a - 3
    return (
        gregorian.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    )


def _from_jdn(jdn):
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    return date(100 * b + d - 4800 + m // 10, m + 3 - 12 * (m // 10), e - (153 * m + 2) // 5 + 1)


def is_leap(year):
    return year % 30 in _LEAP_YEARS


def month_length(year, month):
    if month == 12:
        return 30 if is_leap(year) else 29
    return 30 if month % 2 == 1 else 29


def to_hijri(gregorian):
    """(year, month, day) in the tabular Hijri calendar."""
    days = _jdn(gregorian) - _EPOCH
    cycles, rem = divmod(days, 10631)  # days in 30 lunar years
    year = 30 * cycles + 1
    while True:
        length = 355 if is_leap(year) else 354
        if rem < length:
            break
        rem -= length
        year += 1
    month = 1
    while rem >= month_length(year, month):
        rem -= month_length(year, month)
        month += 1
    return year, month, rem + 1


def to_gregorian(year, month, day):
    days = 0
    full_cycles, year_in_cycle = divmod(year - 1, 30)
    days += full_cycles * 10631
    for y in range(30 * full_cycles + 1, year):
        days += 355 if is_leap(y) else 354
    for m in range(1, month):
        days += month_length(year, m)
    return _from_jdn(_EPOCH + days + day - 1)


def format_hijri(gregorian, language="ar"):
    year, month, day = to_hijri(gregorian)
    names = MONTHS_AR if language == "ar" else MONTHS_EN
    suffix = "هـ" if language == "ar" else "AH"
    return f"{day} {names[month - 1]} {year} {suffix}"


def next_occurrence(gregorian, month, day):
    """The next Gregorian date on which the Hijri calendar reads month/day."""
    year, m, d = to_hijri(gregorian)
    candidate = to_gregorian(year, month, min(day, month_length(year, month)))
    if candidate < gregorian:
        year += 1
        candidate = to_gregorian(year, month, min(day, month_length(year, month)))
    return candidate
