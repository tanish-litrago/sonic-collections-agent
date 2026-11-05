"""All database writes. Money is integer minor units. Payments are append-only; invoice updates are guarded."""
import re
import uuid
from datetime import datetime, timedelta, timezone

from . import seed_data
from .config import today
from .money import fmt
from .services.invoices import is_overdue

COOLDOWN_DAYS = 3
COLLECTIONS = ["organization", "customers", "invoices", "payments", "conversations", "reminders", "matches"]


def now():
    return datetime.now(timezone.utc)


class Conflict(Exception):
    pass


async def reset(db):
    for c in COLLECTIONS:
        await db[c].delete_many({})
    org, custs, invs = seed_data.load()
    await db.organization.insert_one({"_id": "org", **org})
    await db.customers.insert_many([{"_id": c["customer_id"], **c} for c in custs])
    await db.invoices.insert_many([{"_id": i["invoice_number"], **i} for i in invs])


async def all_invoices(db):
    return await db.invoices.find({}).to_list(None)


async def customers(db):
    return await db.customers.find({}).to_list(None)


def with_overdue(inv):
    t = today()
    od = is_overdue(inv, t)
    from datetime import date
    inv["overdue"] = od
    inv["days_overdue"] = (t - date.fromisoformat(inv["due_date"])).days if od else 0
    return inv


def reminder_text(cust, rows):
    lines = [f"- {i['invoice_number']}: balance {fmt(i['balance_due'], i['currency'])}, due {i['due_date']} ({i['days_overdue']} days overdue)" for i in rows]
    return (f"Dear {cust['contact_name']},\n\nThe following invoices are overdue:\n" + "\n".join(lines) +
            "\n\nPlease arrange payment at your earliest convenience. If you have already paid, "
            "reply with the payment date and reference and we will check our bank records.\n\nRegards,\nAccounts Team, AcmeCorp")


async def due_reminders(db):
    """Overdue sent invoices, grouped by customer, skipping any reminded in the last 3 days."""
    cutoff = now() - timedelta(days=COOLDOWN_DAYS)
    groups, skipped = {}, []
    for inv in await all_invoices(db):
        inv = with_overdue(inv)
        if not inv["overdue"]:
            continue
        last = await db.reminders.find_one({"invoice_number": inv["invoice_number"], "sent_at": {"$gt": cutoff}})
        if last:
            skipped.append(inv["invoice_number"])
        else:
            groups.setdefault(inv["customer_id"], []).append(inv)
    return groups, skipped


async def customer_by_email(db, addr: str):
    a = addr.strip().lower()
    return next((c for c in await customers(db) if c["contact_email"].strip().lower() == a), None)


async def approve(db, match_id: str, invoice_numbers: list[str], settle: str, confirm_low: bool):
    m = await db.matches.find_one({"_id": match_id})
    if not m or m["state"] != "pending":
        raise Conflict("This row was already handled")
    r, amount = m["result"], m["txn"]["amount"]
    if r["status"] == "low_confidence" and not confirm_low:
        raise ValueError("Low-confidence match: choose the invoice explicitly to approve")
    if r["status"] not in ("match", "low_confidence") or not invoice_numbers:
        raise ValueError("Nothing to approve for this row")
    invs = []
    for n in invoice_numbers:
        inv = await db.invoices.find_one({"_id": n})
        if not inv or inv["status"] != "sent" or inv["balance_due"] <= 0 or inv["currency"] != m["txn"]["currency"]:
            raise ValueError(f"{n} is not an open invoice in {m['txn']['currency']}")
        invs.append(inv)
    invs.sort(key=lambda i: i["due_date"])
    plan, left = [], amount
    for inv in invs:
        bal, tds = inv["balance_due"], 0
        if settle == "close_tds" and len(invs) == 1:
            tds = inv["subtotal"] // 10
            if amount != bal - tds:
                raise ValueError("Amount is not exactly total minus 10% TDS")
            apply = amount
        else:
            apply = min(left, bal)
        left -= apply
        plan.append((inv, apply, tds))
    claim = await db.matches.update_one({"_id": match_id, "state": "pending"}, {"$set": {"state": "approved", "approved_at": now()}})
    if claim.modified_count != 1:
        raise Conflict("This row was already handled")
    for inv, apply, tds in plan:
        new_bal = inv["balance_due"] - apply - tds
        res = await db.invoices.update_one({"_id": inv["_id"], "balance_due": inv["balance_due"]},
                                           {"$set": {"balance_due": new_bal, "status": "paid" if new_bal == 0 else "sent"},
                                            "$inc": {"amount_paid": apply + tds}})
        if res.modified_count != 1:
            await db.matches.update_one({"_id": match_id}, {"$set": {"state": "conflict"}})
            raise Conflict(f"{inv['_id']} changed while approving; re-check and retry")
        await db.payments.insert_one({"_id": str(uuid.uuid4()), "match_id": match_id, "invoice_number": inv["_id"],
                                      "amount": apply, "tds_withheld": tds, "currency": inv["currency"],
                                      "txn_date": m["txn"]["date"], "narration": m["txn"]["narration"],
                                      "approved_at": now(), "overpayment": max(0, left) if inv is plan[-1][0] else 0})
    return {"applied": [p[0]["_id"] for p in plan], "overpayment": max(0, left)}
