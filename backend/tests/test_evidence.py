import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.seed_data import load
from app.services.evidence import link_evidence
from app.services.matcher import NameIndex, match_row
from app.services.statement import parse_statement

org, custs, invs = load()
idx, by_num = NameIndex(custs), {i["invoice_number"]: i for i in invs}
rows = {t["narration"]: t for t in parse_statement((Path(__file__).resolve().parents[2] / "data" / "bank_statement_sample.csv").read_bytes())}
SHARMA, REDWOOD, ORBIS = rows["IMPS/R K SHARMA/CLINIC DUES"], rows["NEFT CR-REDWOOD CLINIC"], rows["UPI/ORBIS PKG/PART PAYMENT"]
cid = lambda name: next(c["customer_id"] for c in custs if c["name"].startswith(name))
mail = lambda cust, body: {"_id": "m1", "customer_id": cid(cust), "subject": "Payment", "from": "x@y.z", "body": body}

def run(t, convs):
    return link_evidence(match_row(t, custs, invs, idx), t, convs, by_num)

def test_unknown_payer_promoted_when_owner_quotes_reference():
    r = run(SHARMA, [mail("Redwood", f"We paid INV-1017 yesterday, reference {SHARMA['reference']}")])
    assert r["status"] == "match" and r["suggestion"]["score"] == 75 and r["evidence"][0]["via"] == "reference"

def test_no_promotion_without_the_reference():
    r = run(SHARMA, [mail("Redwood", "We paid INV-1017 yesterday")])
    assert r["status"] == "low_confidence"

def test_reference_from_a_different_customer_is_flagged_not_trusted():
    r = run(SHARMA, [mail("Kestrel", f"paid, ref {SHARMA['reference']}")])
    assert r["status"] == "low_confidence" and "different customer" in r["suggestion"]["reason"]

def test_reference_boosts_a_normal_match_and_email_is_shown_beside_row():
    base = match_row(REDWOOD, custs, invs, idx)["suggestion"]["score"]
    r = run(REDWOOD, [mail("Redwood", f"Paid via NEFT, UTR {REDWOOD['reference'].lower()}")])
    assert r["suggestion"]["score"] == base + 15 and r["evidence"][0]["snippet"]

def test_unrelated_email_links_nothing():
    assert "evidence" not in run(ORBIS, [mail("Kestrel", "Thanks, got it")])
