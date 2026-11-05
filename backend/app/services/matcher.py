"""Local bank-statement matcher. No LLM. Hard filters, then an additive explainable score."""
import math
import re
from collections import Counter
from datetime import date
from itertools import combinations

from rapidfuzz import fuzz

from ..money import fmt
from .invoices import open_invoices

LEGAL = {"pvt", "private", "ltd", "limited", "llp", "gmbh", "inc", "co", "corp", "the"}
NOISE = r"\b(PART PAYMENT|PART|PAYMENT|DUES|OCT|SEP|NOV|AUG|PAID)\b"
RECOGNISED = 0.6   # payer name similarity needed to treat the payer as a known customer
MATCH_MIN = 45     # below this we say "no match": wrong matches cost more than misses
LOW_CONF_CAP = 40


def norm_tokens(s: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if t not in LEGAL]


def parse_narration(narr: str):
    u = narr.upper()
    refs = [f"INV-{n}" for n in re.findall(r"(?:INV|RE|REF)[\s\-:/]*(\d{4})\b", u)]
    s = re.sub(r"^(NEFT|RTGS|IMPS|UPI|SWIFT|SEPA)\b[\s/\-]*(CR|DR)?[\s/\-]*", "", u)
    s = re.sub(r"(?:INV|RE|REF)[\s\-:/]*\d{4}\b", " ", s)
    s = re.sub(NOISE, " ", s)
    return refs, " ".join(norm_tokens(s)), "PART" in u


def _grams(s: str) -> Counter:
    s = f"  {s} "
    return Counter(s[i:i + 3] for i in range(len(s) - 2))


class NameIndex:
    """Payer-name similarity against customers: token coverage (handles abbreviations like
    PKG/HOSP), rapidfuzz token-set ratio, and char 3-gram TF-IDF cosine."""

    def __init__(self, customers):
        self.cust = {c["customer_id"]: " ".join(norm_tokens(c["name"])) for c in customers}
        docs = {k: _grams(v) for k, v in self.cust.items()}
        df = Counter(g for d in docs.values() for g in d)
        n = len(docs)
        self.idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}
        self.vec = {k: self._tfidf(d) for k, d in docs.items()}
        tdf = Counter(t for v in self.cust.values() for t in set(v.split()))
        self.tidf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in tdf.items()}

    def _tfidf(self, g):
        return {k: v * self.idf.get(k, math.log(len(self.cust) + 1) + 1) for k, v in g.items()}

    @staticmethod
    def _cos(a, b):
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    def _tok_match(p, c):
        if len(p) < 3:
            return p == c
        return c.startswith(p) or (p[0] == c[0] and iter(c) is not None and _subseq(p, c))

    def sim(self, payer: str, cid: str) -> float:
        cname, ptoks = self.cust[cid], payer.split()
        ptoks = [t for t in ptoks if len(t) >= 3 or t.isdigit()] or ptoks
        ctoks = cname.split()
        if not ptoks:
            return 0.0
        w = lambda t: self.tidf.get(t, max(self.tidf.values()))
        pm = sum(w(p) for p in ptoks if any(self._tok_match(p, c) for c in ctoks))
        cm = sum(w(c) for c in ctoks if any(self._tok_match(p, c) for p in ptoks))
        pcov = pm / sum(w(p) for p in ptoks)
        ccov = cm / sum(w(c) for c in ctoks)
        cov = math.sqrt(pcov * ccov)
        tsr = fuzz.token_set_ratio(payer, cname) / 100
        cos = self._cos(self._tfidf(_grams(payer)), self.vec[cid])
        return 0.5 * cov + 0.25 * tsr + 0.25 * cos


def _subseq(p, c):
    it = iter(c)
    return all(ch in it for ch in p)


def _date(s):
    return date.fromisoformat(s)


def settle_options(inv, amount, cust):
    bal = inv["balance_due"]
    if amount >= bal:
        return ["full"], "full"
    tds = inv["subtotal"] // 10
    if cust["country"] == "India" and inv["currency"] == "INR" and inv["amount_paid"] == 0 \
            and amount == bal - tds:
        return ["close_tds", "leave_open"], "close_tds"
    return ["leave_open", "close_tds"] if cust["country"] == "India" else ["leave_open"], "leave_open"


def score_invoice(inv, cust, txn, name_sim, refs, part_hint):
    pts, why = 0.0, []
    amt, bal = txn["amount"], inv["balance_due"]
    if inv["invoice_number"] in refs:
        pts += 50; why.append("invoice number in narration")
    elif refs:
        pts -= 25; why.append("narration cites a different invoice")
    pts += 30 * name_sim
    if name_sim >= RECOGNISED:
        why.append("payer matches " + cust["name"].split()[0])
    if amt == bal:
        pts += 30; why.append("exact amount")
    elif inv["amount_paid"] == 0 and cust["country"] == "India" and inv["currency"] == "INR" \
            and amt == bal - inv["subtotal"] // 10:
        pts += 28; why.append("amount = total minus 10% TDS")
    elif amt < bal:
        pts += 8 + (10 if part_hint else 0); why.append("part payment")
    else:
        pts -= 30; why.append("amount exceeds balance")
    d = (_date(txn["date"]) - _date(inv["due_date"])).days
    pts += 5 if d <= 30 else 2
    return pts, "; ".join(why)


def match_row(txn, customers, invoices, idx: NameIndex):
    """txn: {date, narration, reference, amount(minor, credit only), currency, direction}."""
    base = {"row": txn.get("row"), "suggestion": None, "alternatives": []}
    if txn["direction"] == "debit":
        return {**base, "status": "ignored", "reason": "Outgoing payment, not a receipt"}
    if re.search(r"\bINT\.?\s?PD\b|INTEREST", txn["narration"].upper()):
        return {**base, "status": "no_match", "reason": "Bank interest credit"}

    refs, payer, part_hint = parse_narration(txn["narration"])
    custs = {c["customer_id"]: c for c in customers}
    sims = {cid: idx.sim(payer, cid) for cid in custs} if payer else {}
    recognised = {cid for cid, s in sims.items() if s >= RECOGNISED and custs[cid]["currency"] == txn["currency"]}
    pool = [i for i in open_invoices(invoices)
            if i["currency"] == txn["currency"] and _date(i["invoice_date"]) <= _date(txn["date"])]
    by_num = {i["invoice_number"]: i for i in pool}

    cands = []
    for inv in pool:
        cid = inv["customer_id"]
        if cid in recognised or inv["invoice_number"] in refs:
            s, why = score_invoice(inv, custs[cid], txn, sims.get(cid, 0.0), refs, part_hint)
            cands.append((s, inv, why))
    cands.sort(key=lambda c: (-c[0], c[1]["due_date"]))  # tie -> oldest first

    # several invoices paid together (bonus): exact sum of 2-4 open invoices of one known payer
    multi = None
    for cid in recognised:
        mine = [i for i in pool if i["customer_id"] == cid]
        for n in (2, 3, 4):
            for combo in combinations(mine, n):
                if sum(i["balance_due"] for i in combo) == txn["amount"]:
                    sc = min(99, 30 * sims[cid] + 40 + 5 + (10 if len(refs) == 0 else 0))
                    multi = (sc, combo)
    if multi and (not cands or multi[0] > cands[0][0] and txn["amount"] > cands[0][1]["balance_due"]):
        sc, combo = multi
        nums = [i["invoice_number"] for i in combo]
        return {**base, "status": "match", "suggestion": {
            "invoice_numbers": nums, "score": round(sc), "settle": "full",
            "settle_options": ["full"],
            "reason": f"One payment covers {', '.join(nums)}: amounts add up exactly"}}

    if cands:
        score = cands[0][0]
        if len(cands) > 1 and cands[0][0] - cands[1][0] < 10 and cands[0][1]["customer_id"] == cands[1][1]["customer_id"]:
            score -= 10
            cands[0] = (cands[0][0], cands[0][1], cands[0][2] + "; also fits another invoice, oldest chosen")
        score = int(max(0, min(99, round(score))))
        if score >= MATCH_MIN:
            inv = cands[0][1]
            opts, pre = settle_options(inv, txn["amount"], custs[inv["customer_id"]])
            alts = [c[1]["invoice_number"] for c in cands[1:4]]
            return {**base, "status": "match", "alternatives": alts, "suggestion": {
                "invoice_numbers": [inv["invoice_number"]], "score": score, "settle": pre,
                "settle_options": opts, "reason": cands[0][2][:1].upper() + cands[0][2][1:]}}

    # unknown payer but amount equals exactly one open invoice: show, never preselect
    exact = [i for i in pool if i["balance_due"] == txn["amount"]]
    if not recognised and len(exact) == 1:
        inv = exact[0]
        return {**base, "status": "low_confidence", "suggestion": {
            "invoice_numbers": [inv["invoice_number"]], "score": LOW_CONF_CAP, "settle": "full",
            "settle_options": ["full"],
            "reason": f"Payer not recognised; amount equals {inv['invoice_number']} exactly. Choose it yourself to approve"}}
    return {**base, "status": "no_match", "reason": "Payer not recognised" if not recognised else "No open invoice fits this payment"}
