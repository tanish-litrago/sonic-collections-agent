"""SMTP send + IMAP read. Gmail with App Passwords. Blocking calls: run them in a thread."""
import email
import imaplib
import os
import re
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr


def configured() -> bool:
    return bool(os.getenv("MAIL_USER") and os.getenv("MAIL_PASSWORD"))


def send_mail(to: str, subject: str, body: str, in_reply_to: str | None = None) -> str:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["MAIL_USER"], to, subject
    msg["Message-ID"] = make_msgid()
    if in_reply_to:
        msg["In-Reply-To"] = msg["References"] = in_reply_to
    msg.set_content(body)
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "465")), timeout=30) as s:
        s.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
        s.send_message(msg)
    return msg["Message-ID"]


def _body(m) -> str:
    part = next((p for p in m.walk() if p.get_content_type() == "text/plain"), None)
    if part is None:
        return ""
    text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    out = []
    for line in text.splitlines():
        if line.startswith(">") or re.match(r"^On .+wrote:\s*$", line):
            break
        out.append(line)
    return "\n".join(out).strip()


def fetch_unseen(limit: int = 20) -> list[dict]:
    """Returns parsed unseen mails. Mails are marked seen only after mark_seen() is called."""
    box = imaplib.IMAP4_SSL(os.getenv("IMAP_HOST", "imap.gmail.com"))
    box.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
    box.select("INBOX")
    _, data = box.search(None, "UNSEEN")
    out = []
    for uid in data[0].split()[:limit]:
        _, raw = box.fetch(uid, "(BODY.PEEK[])")
        m = email.message_from_bytes(raw[0][1])
        out.append({"uid": uid.decode(), "message_id": m.get("Message-ID", ""), "from": parseaddr(m.get("From", ""))[1].lower(),
                    "subject": m.get("Subject", ""), "body": _body(m), "headers": {k: m.get(k, "") for k in
                    ("Auto-Submitted", "X-Autoreply", "Precedence")}})
    box.logout()
    return out


def mark_seen(uids: list[str]):
    if not uids:
        return
    box = imaplib.IMAP4_SSL(os.getenv("IMAP_HOST", "imap.gmail.com"))
    box.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
    box.select("INBOX")
    for u in uids:
        box.store(u, "+FLAGS", "\\Seen")
    box.logout()
