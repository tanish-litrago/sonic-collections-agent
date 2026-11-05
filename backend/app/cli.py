"""python -m app.cli seed   |   python -m app.cli demo"""
import asyncio
import sys

from . import store
from .db import get_db
from .seed_data import DATA
from .services.matcher import NameIndex, match_row
from .services.statement import parse_statement


async def main(cmd):
    db = get_db()
    await store.reset(db)
    print("Seeded: 9 customers, 27 invoices")
    if cmd == "demo":
        custs, invs = await store.customers(db), await store.all_invoices(db)
        idx = NameIndex(custs)
        for t in parse_statement((DATA / "bank_statement_sample.csv").read_bytes()):
            r = match_row(t, custs, invs, idx)
            s = r["suggestion"]
            print(f"{t['narration'][:34]:34} {r['status']:14}", f"{s['invoice_numbers']} score {s['score']}: {s['reason']}" if s else r["reason"])


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "seed"))
