"""Eval harness: python eval/run.py  ->  writes eval/report.md"""
import sys
sys.path.insert(0, "backend")
from app.seed_data import load
from app.money import to_minor
from app.services.invoices import open_invoices
from app.services.matcher import NameIndex, match_row, parse_narration
from app.services.statement import parse_statement

org, custs, invs = load()
idx = NameIndex(custs)

def T(date, narr, amt, cur="INR", d="credit"):
    return {"row": 0, "date": date, "narration": narr, "reference": "", "amount": to_minor(amt), "currency": cur, "direction": d}

# expected: (status, [invoices], settle or None)
SAMPLE = [("match", ["INV-1004"], None), ("match", ["INV-1013"], "leave_open"), ("match", ["INV-1007"], "close_tds"),
          ("match", ["INV-1024"], None), ("match", ["INV-1021"], None), ("match", ["INV-1002"], None),
          ("match", ["INV-1016"], None), ("ignored", [], None), ("match", ["INV-1026"], None),
          ("match", ["INV-1010", "INV-1011", "INV-1012"], None), ("ignored", [], None),
          ("low_confidence", ["INV-1017"], None), ("no_match", [], None), ("no_match", [], None)]
cases = [(t, e, "sample") for t, e in zip(parse_statement(open("data/bank_statement_sample.csv", "rb").read()), SAMPLE)]
SYN = [
 (T("2026-10-03", "NEFT CR-KESTRAL FOODS PVT LTD INV1005", 590000 / 100 * 100 / 100 if False else "59000"), ("match", ["INV-1005"], None), "typo in payer name"),
 (T("2026-10-05", "UPI/BRIGHTLINE LOGISTIC/INV-1002", "236000"), ("match", ["INV-1002"], None), "truncated name"),
 (T("2026-10-05", "NEFT CR-BRIGHTLINE LOGISTICS PVT LTD", "216000"), ("match", ["INV-1002"], "close_tds"), "TDS without invoice ref"),
 (T("2026-10-10", "NEFT CR-ZENITH TRADERS", "41300"), ("low_confidence", ["INV-1011"], None), "unknown payer, exact amount"),
 (T("2026-10-03", "NEFT CR-KESTREL FOODS PVT LTD", "59000"), ("match", ["INV-1004"], None), "two equal invoices, oldest first"),
 (T("2026-09-25", "SWIFT CR HARBOUR ANALYTICS INC", "12500", "EUR"), ("no_match", [], None), "wrong currency"),
 (T("2026-09-01", "NEFT CR-BRIGHTLINE LOGISTICS PVT LTD", "236000"), ("no_match", [], None), "payment before invoice date"),
 (T("2026-10-20", "NEFT CR-KESTREL FOODS PVT LTD", "147500"), ("no_match", [], None), "amount only fits a draft"),
 (T("2026-10-28", "RTGS CR-QUILLON TECH PVT LTD", "531000"), ("match", ["INV-1007", "INV-1008"], None), "two invoices, one payment"),
 (T("2026-10-28", "RTGS CR-REDWOOD CLINIC", "30000"), ("no_match", [], None), "short payment, two open invoices: ambiguous, left to a human"),
]
cases += [(t, e, w) for t, e, w in SYN]

def full(t):
    r = match_row(t, custs, invs, idx)
    s = r["suggestion"]
    return r["status"], (s["invoice_numbers"] if s else []), (s["settle"] if s else None)

def name_only(t):  # baseline: best name -> oldest open invoice
    if t["direction"] == "debit": return "ignored", [], None
    _, payer, _ = parse_narration(t["narration"])
    best = max(idx.cust, key=lambda c: idx.sim(payer, c)) if payer else None
    if not best or idx.sim(payer, best) < 0.6: return "no_match", [], None
    mine = sorted([i for i in open_invoices(invs) if i["customer_id"] == best], key=lambda i: i["due_date"])
    return ("match", [mine[0]["invoice_number"]], None) if mine else ("no_match", [], None)

def amount_only(t):  # baseline: first open invoice with the same amount
    if t["direction"] == "debit": return "ignored", [], None
    hit = [i for i in open_invoices(invs) if i["balance_due"] == t["amount"]]
    return ("match", [hit[0]["invoice_number"]], None) if hit else ("no_match", [], None)

def score(fn):
    tp = fp = fn_ = ok = 0
    for t, (es, ei, ec), _ in cases:
        s, i, c = fn(t)
        exp_match = es == "match"
        pred_match = s == "match"
        good = pred_match and exp_match and i == ei and (ec is None or c == ec)
        tp += good
        fp += pred_match and not good
        fn_ += exp_match and not good
        ok += (s == es and i == ei and (ec is None or c == ec)) if fn is full else 0
    return tp, fp, fn_, ok

lines = ["# Reconciliation eval report", "", f"{len(cases)} labelled rows ({len(SAMPLE)} from the sample statement, {len(SYN)} synthetic).", "",
         "| Matcher | Precision | Recall | Wrong matches | Exact outcome |", "|---|---|---|---|---|"]
for name, fn in [("Full (name + number + amount + date)", full), ("Baseline: name only", name_only), ("Baseline: amount only", amount_only)]:
    tp, fp, fn_, ok = score(fn)
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn_) if tp + fn_ else 0
    lines.append(f"| {name} | {p:.0%} | {r:.0%} | {fp} | {str(ok) + '/' + str(len(cases)) if fn is full else '-'} |")
lines += ["", "## Misses by the full matcher", ""]
miss = 0
for t, (es, ei, ec), why in cases:
    s, i, c = full(t)
    if not (s == es and i == ei and (ec is None or c == ec)):
        miss += 1; lines.append(f"- {why}: `{t['narration']}` expected {es} {ei} {ec}, got {s} {i} {c}")
if not miss: lines.append("None.")
open("eval/report.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

# CI gate: the full matcher must have no wrong matches and no misses on the labelled rows
_tp, _fp, _fn, _ = score(full)
sys.exit(1 if (_fp or _fn) else 0)
