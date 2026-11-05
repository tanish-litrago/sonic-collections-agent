import sys
sys.path.insert(0, "backend")
from app.seed_data import load
from app.services.matcher import NameIndex, match_row
from app.services.statement import parse_statement
org, custs, invs = load()
idx = NameIndex(custs)
for t in parse_statement(open("data/bank_statement_sample.csv", "rb").read()):
    r = match_row(t, custs, invs, idx)
    s = r["suggestion"]
    print(t["row"], t["narration"][:32].ljust(32), r["status"].ljust(14), (s["invoice_numbers"], s["score"], s["settle"]) if s else r.get("reason"))
