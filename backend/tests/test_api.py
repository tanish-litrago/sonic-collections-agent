import os
import sys
from pathlib import Path

os.environ.update(SECRET_KEY="t", ADMIN_USER="admin", ADMIN_PASSWORD="pw", DISABLE_POLLER="1", DEMO_TODAY="2026-11-04",
                  MAIL_USER="acct@test.dev", MAIL_PASSWORD="x")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app import db as dbmod, mail
from app.main import _hits, app, process_message
from app.services import llm

CSV = Path(__file__).resolve().parents[2] / "data" / "bank_statement_sample.csv"


@pytest.fixture()
def c(monkeypatch):
    _hits.clear()
    dbmod.set_db(AsyncMongoMockClient()["t"])
    sent = []
    monkeypatch.setattr(mail, "send_mail", lambda to, s, b, r=None: sent.append((to, s, b)) or "<id>")
    cl = TestClient(app)
    assert cl.post("/api/login", json={"username": "admin", "password": "pw"}).status_code == 200
    cl.post("/api/reset")
    cl.sent = sent
    return cl


def upload(c):
    return c.post("/api/reconcile", files={"file": ("s.csv", CSV.read_bytes(), "text/csv")}).json()["rows"]


def row(rows, needle):
    return next(r for r in rows if needle in r["txn"]["narration"])


def test_requires_login():
    assert TestClient(app).get("/api/invoices").status_code == 401
    assert TestClient(app).post("/api/login", json={"username": "admin", "password": "no"}).status_code == 401


def test_overdue_flags(c):
    inv = {i["invoice_number"]: i for i in c.get("/api/invoices").json()}
    assert inv["INV-1004"]["overdue"] and not inv["INV-1001"]["overdue"] and not inv["INV-1006"]["overdue"]


def test_double_approval_is_safe(c):
    r = row(upload(c), "KESTREL")
    body = {"invoice_numbers": ["INV-1004"], "settle": "full"}
    assert c.post(f"/api/matches/{r['_id']}/approve", json=body).status_code == 200
    assert c.post(f"/api/matches/{r['_id']}/approve", json=body).status_code == 409
    inv = {i["invoice_number"]: i for i in c.get("/api/invoices").json()}["INV-1004"]
    assert inv["balance_due"] == 0 and inv["status"] == "paid"


def test_tds_closes_invoice_and_wrong_amount_rejected(c):
    r = row(upload(c), "QUILLON")
    assert c.post(f"/api/matches/{r['_id']}/approve", json={"invoice_numbers": ["INV-1007"], "settle": "close_tds"}).status_code == 200
    inv = {i["invoice_number"]: i for i in c.get("/api/invoices").json()}["INV-1007"]
    assert inv["status"] == "paid" and inv["balance_due"] == 0
    r2 = row(upload(c), "ORBIS")
    assert c.post(f"/api/matches/{r2['_id']}/approve", json={"invoice_numbers": ["INV-1013"], "settle": "close_tds"}).status_code == 422


def test_partial_payment_leaves_balance(c):
    r = row(upload(c), "ORBIS")
    assert c.post(f"/api/matches/{r['_id']}/approve", json={"invoice_numbers": ["INV-1013"], "settle": "leave_open"}).status_code == 200
    inv = {i["invoice_number"]: i for i in c.get("/api/invoices").json()}["INV-1013"]
    assert inv["balance_due"] == 47200000 - 20000000 and inv["status"] == "sent"


def test_low_confidence_needs_explicit_confirm(c):
    r = row(upload(c), "SHARMA")
    body = {"invoice_numbers": ["INV-1017"], "settle": "full"}
    assert c.post(f"/api/matches/{r['_id']}/approve", json=body).status_code == 422
    assert c.post(f"/api/matches/{r['_id']}/approve", json={**body, "confirm_low_confidence": True}).status_code == 200


def test_bad_csv_rejected_cleanly(c):
    r = c.post("/api/reconcile", files={"file": ("s.csv", b"a,b\n1,2", "text/csv")})
    assert r.status_code == 422 and "columns" in r.json()["detail"]


def test_reminder_cooldown(c):
    first = c.post("/api/reminders/send").json()
    assert first["sent"] and len(c.sent) == len(first["sent"])
    second = c.post("/api/reminders/send").json()
    assert second["sent"] == [] and second["skipped_cooldown"]


def test_edit_email_validated(c):
    assert c.patch("/api/customers/C001", json={"contact_email": "nope"}).status_code == 422
    assert c.patch("/api/customers/C001", json={"contact_email": "a@b.co"}).status_code == 200


@pytest.mark.asyncio
async def test_inbox_flow(c, monkeypatch):
    import asyncio
    db = dbmod.get_db()
    mk = lambda frm, subj="Q", h=None: {"uid": "1", "message_id": f"<{frm}{subj}>", "from": frm, "subject": subj, "body": "hi", "headers": h or {}}
    assert (await process_message(db, mk("stranger@x.com")))["status"] == "needs_attention"
    assert (await process_message(db, mk("customer1@example.com", "Out of office")))["status"] == "automated"
    monkeypatch.setattr(llm, "complete_json", lambda p: {"intent": "balance_query", "confidence": 0.9,
                        "reply": "Balance on {INV-1002.number} is {INV-1002.balance}."})
    assert (await process_message(db, mk("customer1@example.com", "Balance")))["status"] == "replied"
    assert "₹2,36,000.00" in c.sent[-1][2]
    assert (await process_message(db, mk("customer1@example.com", "Balance"))).get("skipped")


def test_matches_returns_latest_batch(c):
    upload(c)
    two = c.post("/api/reconcile", files={"file": ("s.csv", b"txn_date,narration,reference,credit,debit,currency\n2026-10-01,NEFT CR-ZENITH,,41300,,INR\n", "text/csv")}).json()
    got = c.get("/api/matches").json()
    assert len(got) == 1 and got[0]["batch"] == two["batch"]


def test_customer_email_shows_beside_row_via_api(c):
    import asyncio
    from app.db import get_db
    asyncio.run(get_db().conversations.insert_one({"_id": "<e1>", "customer_id": "C006", "status": "needs_attention",
        "subject": "Paid", "from": "x@y.z", "body": "We paid INV-1017, reference 629315881020"}))
    rows = upload(c)
    sharma = row(rows, "SHARMA")
    assert sharma["result"]["status"] == "match" and sharma["result"]["evidence"][0]["conversation_id"] == "<e1>"


def test_empty_database_is_seeded_on_first_start(monkeypatch):
    _hits.clear()
    dbmod.set_db(AsyncMongoMockClient()["fresh"])
    with TestClient(app) as cl:
        cl.post("/api/login", json={"username": "admin", "password": "pw"})
        assert len(cl.get("/api/invoices").json()) == 27


def test_multi_invoice_payment_is_split_on_approval(c):
    r = row(upload(c), "SAFFRON")
    assert r["result"]["suggestion"]["invoice_numbers"] == ["INV-1010", "INV-1011", "INV-1012"]
    body = {"invoice_numbers": ["INV-1010", "INV-1011", "INV-1012"], "settle": "full"}
    assert c.post(f"/api/matches/{r['_id']}/approve", json=body).status_code == 200
    inv = {i["invoice_number"]: i for i in c.get("/api/invoices").json()}
    assert all(inv[n]["status"] == "paid" and inv[n]["balance_due"] == 0 for n in body["invoice_numbers"])
    from app.db import get_db
    import asyncio
    pays = asyncio.run(get_db().payments.find({"match_id": r["_id"]}).to_list(None))
    assert sorted(p["amount"] for p in pays) == [4130000, 7080000, 8260000] and sum(p["amount"] for p in pays) == 19470000
