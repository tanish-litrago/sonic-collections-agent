import json
from pathlib import Path
from .money import to_minor

DATA = next(p / "data" for p in Path(__file__).resolve().parents if (p / "data" / "invoices.json").exists())
MONEY = ["subtotal", "discount", "tax", "total", "amount_paid", "balance_due"]

def load():
    org = json.loads((DATA / "organization.json").read_text(encoding="utf-8"))
    custs = json.loads((DATA / "customers.json").read_text(encoding="utf-8"))
    invs = json.loads((DATA / "invoices.json").read_text(encoding="utf-8"))
    for i in invs:
        for k in MONEY: i[k] = to_minor(i[k])
        for li in i["line_items"]:
            li["unit_price"] = to_minor(li["unit_price"]); li["amount"] = to_minor(li["amount"])
    return org, custs, invs
