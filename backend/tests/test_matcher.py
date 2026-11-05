import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.money import fmt, to_minor
from app.seed_data import load
from app.services.matcher import NameIndex, match_row

org, custs, invs = load()
idx = NameIndex(custs)

def row(date, narr, amt, cur="INR", d="credit"):
    return {"row": 0, "date": date, "narration": narr, "amount": to_minor(amt), "currency": cur, "direction": d}

def test_money_never_float_and_indian_grouping():
    assert to_minor("7350.5") == 735050 and fmt(11800000, "INR") == "₹1,18,000.00"

def test_tds_preselected_only_on_exact_amount():
    r = match_row(row("2026-10-20", "RTGS CR-QUILLON TECH PVT LTD", "324000"), custs, invs, idx)
    assert r["suggestion"]["settle"] == "close_tds"
    r = match_row(row("2026-10-20", "RTGS CR-QUILLON TECH PVT LTD", "324001"), custs, invs, idx)
    assert r["status"] != "match" or r["suggestion"]["settle"] != "close_tds"

def test_unknown_payer_is_never_a_confident_match():
    r = match_row(row("2026-10-20", "IMPS/R K SHARMA/CLINIC DUES", "88500"), custs, invs, idx)
    assert r["status"] == "low_confidence" and r["suggestion"]["score"] <= 40

def test_draft_invoices_never_matched():
    r = match_row(row("2026-10-20", "NEFT CR-KESTREL FOODS PVT LTD", "147500"), custs, invs, idx)
    assert r["status"] == "no_match"

def test_currency_and_date_filters():
    assert match_row(row("2026-09-25", "SWIFT CR HARBOUR ANALYTICS INC", "12500", "EUR"), custs, invs, idx)["status"] == "no_match"
    assert match_row(row("2026-09-01", "NEFT CR-BRIGHTLINE LOGISTICS PVT LTD", "236000"), custs, invs, idx)["status"] == "no_match"
