import asyncio
import hmac
import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

from . import mail, store
from .db import get_db
from .services import agent
from .services.matcher import NameIndex, match_row
from .services.invoices import open_invoices
from .services.statement import parse_statement

COOKIE, MAX_AGE = "session", 8 * 3600
_hits: dict = defaultdict(deque)


def signer():
    return URLSafeTimedSerializer(os.environ["SECRET_KEY"])


def limit(request: Request, bucket: str, n: int, per: int = 60):
    q = _hits[(request.client.host if request.client else "?", bucket)]
    t = time.time()
    while q and q[0] < t - per:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, "Too many requests, try again in a minute")
    q.append(t)


def admin(request: Request):
    try:
        signer().loads(request.cookies.get(COOKIE, ""), max_age=MAX_AGE)
    except BadSignature:
        raise HTTPException(401, "Please log in")


async def poll_inbox():
    while True:
        await asyncio.sleep(int(os.getenv("INBOX_POLL_SECONDS", "60")))
        try:
            if mail.configured():
                await check_inbox()
        except Exception as e:  # keep polling
            print("inbox poll failed:", type(e).__name__)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(poll_inbox()) if os.getenv("DISABLE_POLLER") != "1" else None
    yield
    if task:
        task.cancel()

app = FastAPI(title="AcmeCorp Collections", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def login(body: Login, request: Request, response: Response):
    limit(request, "login", 5)
    ok = hmac.compare_digest(body.username, os.environ["ADMIN_USER"]) & hmac.compare_digest(body.password, os.environ["ADMIN_PASSWORD"])
    if not ok:
        raise HTTPException(401, "Wrong username or password")
    response.set_cookie(COOKIE, signer().dumps("admin"), httponly=True, samesite="lax", max_age=MAX_AGE)
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me", dependencies=[Depends(admin)])
async def me():
    return {"ok": True, "mail_configured": mail.configured(), "llm": os.getenv("LLM_PROVIDER", "gemini")}


@app.get("/api/organization", dependencies=[Depends(admin)])
async def organization():
    return await get_db().organization.find_one({"_id": "org"}) or {}


@app.get("/api/customers", dependencies=[Depends(admin)])
async def customers():
    return await store.customers(get_db())


class EmailIn(BaseModel):
    contact_email: str


@app.patch("/api/customers/{cid}", dependencies=[Depends(admin)])
async def edit_customer(cid: str, body: EmailIn):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", body.contact_email.strip()) or len(body.contact_email) > 200:
        raise HTTPException(422, "Enter a valid email address")
    r = await get_db().customers.update_one({"_id": cid}, {"$set": {"contact_email": body.contact_email.strip()}})
    if not r.matched_count:
        raise HTTPException(404, "Customer not found")
    return {"ok": True}


@app.get("/api/invoices", dependencies=[Depends(admin)])
async def invoices():
    return [store.with_overdue(i) for i in await store.all_invoices(get_db())]


@app.post("/api/reset", dependencies=[Depends(admin)])
async def reset():
    await store.reset(get_db())
    return {"ok": True}


@app.post("/api/reminders/send", dependencies=[Depends(admin)])
async def send_reminders(request: Request):
    limit(request, "remind", 10)
    if not mail.configured():
        raise HTTPException(503, "Email is not configured: set MAIL_USER and MAIL_PASSWORD in .env")
    db = get_db()
    groups, skipped = await store.due_reminders(db)
    custs = {c["_id"]: c for c in await store.customers(db)}
    sent, failed = [], []
    for cid, rows in groups.items():
        c = custs[cid]
        try:
            await asyncio.to_thread(mail.send_mail, c["contact_email"], "Overdue invoices from AcmeCorp", store.reminder_text(c, rows))
            for r in rows:
                await db.reminders.insert_one({"_id": str(uuid.uuid4()), "invoice_number": r["invoice_number"], "customer_id": cid, "sent_at": store.now()})
            sent.append({"customer": c["name"], "invoices": [r["invoice_number"] for r in rows]})
        except Exception as e:
            failed.append({"customer": c["name"], "error": type(e).__name__})
    return {"sent": sent, "skipped_cooldown": skipped, "failed": failed}


async def process_message(db, msg: dict) -> dict:
    mid = msg["message_id"] or str(uuid.uuid4())
    if await db.conversations.find_one({"_id": mid}):
        return {"skipped": True}
    doc = {"_id": mid, "from": msg["from"], "subject": msg["subject"], "body": msg["body"][:4000], "received_at": store.now()}
    auto = agent.is_automated(msg["headers"], msg["from"], msg["subject"])
    cust = await store.customer_by_email(db, msg["from"])
    if auto:
        doc.update(status="automated", reason=f"Detected {auto}; no reply sent", customer_id=cust and cust["_id"])
    elif not cust:
        doc.update(status="needs_attention", reason="Unknown sender; no customer data was used", customer_id=None)
    else:
        doc["customer_id"] = cust["_id"]
        res = await asyncio.to_thread(agent.handle, cust, await store.all_invoices(db), msg["subject"], msg["body"])
        doc.update({k: v for k, v in res.items() if k not in ("action", "reply")})
        if res["action"] == "reply":
            try:
                await asyncio.to_thread(mail.send_mail, msg["from"], "Re: " + msg["subject"], res["reply"], msg["message_id"] or None)
                doc.update(status="replied", reply=res["reply"], reply_sent_at=store.now())
            except Exception as e:
                doc.update(status="needs_attention", reason=f"Reply could not be sent ({type(e).__name__})", reply=res["reply"])
        else:
            doc["status"] = "needs_attention"
    await db.conversations.insert_one(doc)
    return {"status": doc["status"]}


async def check_inbox():
    db = get_db()
    msgs = await asyncio.to_thread(mail.fetch_unseen)
    done = []
    for m in msgs:
        await process_message(db, m)
        done.append(m["uid"])
    await asyncio.to_thread(mail.mark_seen, done)
    return len(msgs)


@app.post("/api/inbox/check", dependencies=[Depends(admin)])
async def inbox_check(request: Request):
    limit(request, "inbox", 10)
    if not mail.configured():
        raise HTTPException(503, "Email is not configured: set MAIL_USER and MAIL_PASSWORD in .env")
    return {"processed": await check_inbox()}


@app.get("/api/conversations", dependencies=[Depends(admin)])
async def conversations(status: str | None = None):
    q = {"status": status} if status else {}
    return await get_db().conversations.find(q).sort("received_at", -1).to_list(200)


@app.post("/api/conversations/{cid}/resolve", dependencies=[Depends(admin)])
async def resolve_conversation(cid: str):
    r = await get_db().conversations.update_one({"_id": cid}, {"$set": {"status": "resolved"}})
    if not r.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@app.post("/api/reconcile", dependencies=[Depends(admin)])
async def reconcile(request: Request, file: UploadFile = File(...)):
    limit(request, "upload", 10)
    raw = await file.read(1_000_001)
    try:
        txns = parse_statement(raw)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db = get_db()
    custs, invs = await store.customers(db), await store.all_invoices(db)
    idx, batch, out = NameIndex(custs), str(uuid.uuid4()), []
    for t in txns:
        r = match_row(t, custs, invs, idx)
        doc = {"_id": str(uuid.uuid4()), "batch": batch, "txn": t, "result": r,
               "created_at": store.now(), "state": "pending" if r["status"] in ("match", "low_confidence") else "info"}
        await db.matches.insert_one(doc)
        out.append(doc)
    return {"batch": batch, "rows": out}


@app.get("/api/matches", dependencies=[Depends(admin)])
async def matches(batch: str | None = None):
    if not batch:
        last = await get_db().matches.find({}).sort("created_at", -1).to_list(1)
        batch = last[0]["batch"] if last else None
    return await get_db().matches.find({"batch": batch}).to_list(None) if batch else []


class Approval(BaseModel):
    invoice_numbers: list[str]
    settle: str = "full"
    confirm_low_confidence: bool = False


@app.post("/api/matches/{mid}/approve", dependencies=[Depends(admin)])
async def approve(mid: str, body: Approval):
    if body.settle not in ("full", "close_tds", "leave_open"):
        raise HTTPException(422, "Unknown settlement option")
    try:
        return await store.approve(get_db(), mid, body.invoice_numbers, body.settle, body.confirm_low_confidence)
    except store.Conflict as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/matches/{mid}/reject", dependencies=[Depends(admin)])
async def reject(mid: str):
    r = await get_db().matches.update_one({"_id": mid, "state": "pending"}, {"$set": {"state": "rejected"}})
    if r.modified_count != 1:
        raise HTTPException(409, "This row was already handled")
    return {"ok": True}
