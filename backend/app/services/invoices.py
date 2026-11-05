from datetime import date

def is_overdue(inv: dict, today: date) -> bool:
    return (inv["status"] == "sent" and inv["balance_due"] > 0
            and date.fromisoformat(inv["due_date"]) < today)

def open_invoices(invs: list[dict]) -> list[dict]:
    return [i for i in invs if i["status"] == "sent" and i["balance_due"] > 0]
