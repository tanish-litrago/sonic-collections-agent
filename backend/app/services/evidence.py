"""Bonus: link customer emails to bank rows. Deterministic (no LLM): an email links to a row when its text
contains the row's bank reference, or names the suggested invoice. Evidence only ever nudges a score;
a person still approves."""
import re

TOKEN = re.compile(r"[A-Za-z0-9]{6,24}")
INV = re.compile(r"INV[\s\-]?(\d{4})", re.I)
REF_BOOST, MENTION_BOOST, CONFLICT_PENALTY, PROMOTED_SCORE = 15, 5, 15, 75


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def link_evidence(res: dict, txn: dict, convs: list[dict], invs_by_num: dict) -> dict:
    if res["status"] == "ignored" or txn["direction"] != "credit":
        return res
    ref = _norm(txn.get("reference", ""))
    s = res.get("suggestion")
    owner = {invs_by_num[n]["customer_id"] for n in s["invoice_numbers"]} if s else set()
    ev = []
    for c in convs:
        text = f"{c.get('subject', '')} {c.get('body', '')}"
        by_ref = len(ref) >= 6 and ref in {_norm(t) for t in TOKEN.findall(text)}
        mentioned = {f"INV-{n}" for n in INV.findall(text)}
        by_inv = bool(s) and bool(mentioned & set(s["invoice_numbers"]))
        if not (by_ref or by_inv):
            continue
        consistent = bool(s) and c.get("customer_id") in owner
        ev.append({"conversation_id": c["_id"], "subject": c.get("subject", ""), "from": c.get("from", ""),
                   "snippet": (c.get("body") or "")[:160], "via": "reference" if by_ref else "invoice number",
                   "consistent": consistent if s else None})
    if not ev:
        return res
    res["evidence"] = ev
    if not s:
        return res
    ok_ref = any(e["via"] == "reference" and e["consistent"] for e in ev)
    bad_ref = any(e["via"] == "reference" and not e["consistent"] for e in ev)
    ok_mention = any(e["via"] != "reference" and e["consistent"] for e in ev)
    if bad_ref:
        s["score"] = max(0, s["score"] - CONFLICT_PENALTY)
        s["reason"] += ". Warning: an email quoting this bank reference comes from a different customer"
    elif ok_ref:
        if res["status"] == "low_confidence":  # unknown payer, but the invoice owner quoted this exact reference
            res["status"], s["score"] = "match", PROMOTED_SCORE
            s["reason"] = f"Customer email quotes this bank reference for {s['invoice_numbers'][0]}; amount equals it exactly"
        else:
            s["score"] = min(99, s["score"] + REF_BOOST)
            s["reason"] += "; confirmed by a customer email quoting the same bank reference"
    elif ok_mention:
        s["score"] = min(99, s["score"] + MENTION_BOOST)
        s["reason"] += "; customer email mentions this invoice"
    return res
