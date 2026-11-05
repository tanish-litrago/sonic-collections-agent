"""Money is integer minor units (paise/cents) everywhere. Never floats."""
from decimal import Decimal, ROUND_HALF_UP

def to_minor(x) -> int:
    return int((Decimal(str(x)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))

def fmt(minor: int, cur: str) -> str:
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
    neg, minor = minor < 0, abs(minor)
    whole, frac = divmod(minor, 100)
    s = str(whole)
    if cur == "INR" and len(s) > 3:  # Indian grouping: 1,18,000
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        s = ",".join(parts + [tail])
    else:
        s = f"{whole:,}"
    return f"{'-' if neg else ''}{sym}{s}.{frac:02d}"
