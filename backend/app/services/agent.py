"""Inbound email handling. The LLM never types a figure: code fills placeholders from the DB,
then a validator rejects any digit that did not come from the database."""
import re
from datetime import date

from ..money import fmt
from . import llm

AUTO_INTENTS = {"balance_query", "claims_paid", "promises_payment"}
PLACEHOLDER = re.compile(r"\{(INV-\d{4})\.(balance|due|number|total)\}")
AUTOMATED_SUBJECT = re.compile(r"out of office|automatic reply|auto-reply|undeliverable|delivery status|mail delivery failed", re.I)


def is_automated(headers: dict, sender: str, subject: str) -> str | None:
    h = {k.lower(): str(v).lower() for k, v in headers.items()}
    if "mailer-daemon" in sender.lower() or "postmaster" in sender.lower():
        return "bounce"
    auto_sub = h.get("auto-submitted", "").strip().lower()
    if (auto_sub and auto_sub != "no") or h.get("x-autoreply") or h.get("precedence") in {"auto_reply", "bulk", "junk"}:
        return "auto-reply"
    return "auto-reply" if AUTOMATED_SUBJECT.search(subject or "") else None


def customer_context(customer, invoices):
    """Only this customer's sent invoices. Drafts and other customers never reach the LLM."""
    mine = [i for i in invoices if i["customer_id"] == customer["customer_id"] and i["status"] != "draft"]
    vals = {}
    for i in mine:
        n = i["invoice_number"]
        vals[(n, "balance")] = fmt(i["balance_due"], i["currency"])
        vals[(n, "total")] = fmt(i["total"], i["currency"])
        vals[(n, "due")] = date.fromisoformat(i["due_date"]).strftime("%d %b %Y")
        vals[(n, "number")] = n
    return mine, vals


def render(reply: str, vals: dict) -> str | None:
    """Fill placeholders. Returns None if the draft uses an unknown placeholder or any digit of its own."""
    bare = PLACEHOLDER.sub("", reply)
    if re.search(r"\d", bare):
        return None
    out = reply
    for m in PLACEHOLDER.finditer(reply):
        key = (m.group(1), m.group(2))
        if key not in vals:
            return None
        out = out.replace(m.group(0), vals[key])
    return None if re.search(r"\{[^}]*\}", out) else out


def handle(customer, invoices, subject, body):
    mine, vals = customer_context(customer, invoices)
    ctx = "\n".join(f"- {i['invoice_number']} status={i['status']} placeholders: "
                    f"{{{i['invoice_number']}.balance}} {{{i['invoice_number']}.due}} {{{i['invoice_number']}.number}}"
                    for i in mine)
    prompt = f"CONTEXT (customer {customer['name']}):\n{ctx}\n\nEMAIL SUBJECT: {subject}\nEMAIL BODY:\n{body[:4000]}"
    try:
        out = llm.complete_json(prompt)
    except Exception as e:  # provider down, bad JSON: a human handles it
        return {"action": "needs_attention", "reason": f"LLM unavailable or invalid output ({type(e).__name__})"}
    intent = out.get("intent", "other")
    claimed = [n for n in out.get("claimed_invoice_numbers", []) if any(i["invoice_number"] == n for i in mine)]
    info = {"intent": intent, "summary": str(out.get("summary", ""))[:300], "claimed_invoices": claimed,
            "claimed_date": out.get("claimed_date")}
    if intent not in AUTO_INTENTS or float(out.get("confidence", 0)) < 0.6:
        return {"action": "needs_attention", "reason": f"Intent '{intent}' needs a person", **info}
    text = render(str(out.get("reply", "")), vals)
    if not text:
        return {"action": "needs_attention", "reason": "Draft failed number validation", **info}
    return {"action": "reply", "reply": text, **info}
