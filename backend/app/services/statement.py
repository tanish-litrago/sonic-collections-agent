import csv
import io
from decimal import Decimal, InvalidOperation
from ..money import to_minor

MAX_BYTES = 1_000_000

def parse_statement(raw: bytes) -> list[dict]:
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV is larger than 1 MB")
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    need = {"txn_date", "narration", "reference", "credit", "debit", "currency"}
    if not rows.fieldnames or not need <= set(rows.fieldnames):
        raise ValueError("CSV needs columns: " + ", ".join(sorted(need)))
    out = []
    for n, r in enumerate(rows):
        try:
            credit, debit = (r["credit"] or "").strip(), (r["debit"] or "").strip()
            amt = to_minor(credit or debit or "0")
            out.append({"row": n, "date": r["txn_date"].strip(), "narration": r["narration"].strip(),
                        "reference": (r["reference"] or "").strip(), "amount": amt,
                        "currency": r["currency"].strip().upper(),
                        "direction": "credit" if credit else "debit"})
        except (InvalidOperation, ValueError, AttributeError):
            raise ValueError(f"Row {n + 2}: unreadable amount or date")
    return out
