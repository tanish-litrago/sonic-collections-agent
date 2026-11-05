# AcmeCorp Collections and Reconciliation

A small accounts-receivable tool for the fictional company AcmeCorp. It (1) emails customers about overdue
invoices and answers their replies, and (2) matches a bank statement CSV to open invoices and lets a person
approve each match. A person approves every payment. The LLM never decides anything about money.

> Built with AI assistance (Claude and Antigravity). I ran everything and can explain every part of it.

## Architecture

```
React (Vite) ──nginx /api──▶ FastAPI ──▶ MongoDB
 :5173                        :8000        invoices, customers, payments (append-only),
                               │           conversations, reminders, matches
                               ├─ SMTP/IMAP (Gmail)      reminders out, replies in
                               ├─ LLM (Gemini or local Ollama)   classify + draft only
                               └─ matcher (local, no LLM)        bank rows -> invoices
```

Backend layout: `backend/app/main.py` (routes, auth), `store.py` (all writes), `services/matcher.py`,
`services/evidence.py`, `services/agent.py`, `services/llm.py`, `mail.py`, `money.py`.
Frontend: `frontend/src` (plain React, separate app, talks to the API only).
Docs: `docs/INVARIANTS.md`, `docs/DECISIONS.md`, `docs/BUILD_LOG.md`, `explanation.pdf`.

## Run it end to end

Requires Docker, a Gmail account for the organization mailbox, and either a Gemini API key or a local Ollama.

1. `cp .env.example .env` and fill it in:

| Variable | Meaning |
|---|---|
| `ADMIN_USER`, `ADMIN_PASSWORD`, `SECRET_KEY` | Login for the web app and cookie signing. Change them |
| `MAIL_USER`, `MAIL_PASSWORD` | Organization Gmail address and an **App Password** (Google account > Security > 2-Step Verification > App passwords). IMAP must be enabled in Gmail settings |
| `LLM_PROVIDER` | `gemini` (set `LLM_API_KEY`) or `ollama` (set `OLLAMA_MODEL`, default `gemma4:e4b`; Ollama must run on the host) |
| `DEMO_TODAY` | Optional, e.g. `2026-11-04`. Pins "today" for overdue calculation. Default is the real date |

2. `docker compose up --build`
3. Open http://localhost:5173 and log in. The database is seeded automatically on first start
   (9 customers, 27 invoices). **Reset demo data** in the header restores it at any time.
4. **Customers** page: set a customer's email to a second test mailbox you control.
5. **Collections**: *Send reminders* emails that customer about overdue invoices. Reply from the test mailbox
   (for example "How much do I owe on INV-1004?"), then click *Check inbox now* (the inbox is also polled every 60 s).
   Balance questions are answered automatically. Disputes, extension requests and unknown senders appear under
   *Needs attention*.
6. **Reconciliation**: upload `data/bank_statement_sample.csv`, review each row, approve or reject. Approving updates
   the invoice balance and appends a payment record.

Without Docker: `pip install -r backend/requirements.txt`, run MongoDB, `uvicorn app.main:app` from `backend/`,
and `npm install && npm run dev` in `frontend/` (dev server proxies `/api` to port 8000).

## Tests and evaluation

- `make test` runs the backend tests (matcher, agent validation, API, evidence linking). They use a fake LLM and an
  in-memory database, so they need no credentials. The live Gmail and Gemini/Ollama calls are only covered by step 5 above.
- `python eval/run.py` writes `eval/report.md`: precision, recall and wrong-match rate on 24 labelled rows
  (the 14 sample rows plus 10 synthetic edge cases), against two naive baselines. The full matcher scores 24/24 on
  my own labels; the baselines reach 39% (name only) and 54% (amount only) precision. These are my labels,
  so treat the result as a sanity check and not as a benchmark.

## How the important parts work

- **Overdue**: status `sent`, balance above zero, due date before today. Drafts are never chased.
- **Replies**: the LLM returns an intent and a draft containing placeholders like `{INV-1004.balance}`. Code fills
  every figure from the database. A draft with a digit of its own, an unknown placeholder or another customer's
  invoice is discarded and sent to *Needs attention*. Only the sender's own non-draft invoices are given to the LLM.
- **Matching**: hard filters (same currency, open invoice, invoice date not after payment date), then an additive
  score from payer name, invoice number in the narration, amount and date. Each match carries a one-line reason.
  TDS (10% of the subtotal, India only) is preselected only when the amount is exactly total minus TDS.
  One payment covering several invoices is suggested when the amounts add up exactly.
  An unknown payer whose amount equals one invoice is shown as *Low confidence* and needs an explicit tick to approve.
- **Bonus items**: multi-invoice payments, out-of-office/bounce detection, and linking a customer email to a bank row
  (by bank reference or invoice number; shown beside the row and used as extra evidence).

## Scope and honest limits

Left out on purpose: user accounts and roles (one admin login), currency conversion, HTML or attachment parsing in
emails, automatic approval of any payment, deployment to a public host.

Known gaps:
- Reply quality depends on the LLM. Anything the validator cannot verify goes to a person, so a weak model sends fewer
  automatic replies, not wrong ones. I did not test Gemini and the local model against each other.
- TDS handling assumes India and 10% of the subtotal, as described in the assignment.
- Statement dates must be `YYYY-MM-DD`. Files over 1 MB are rejected.
- A short payment from a customer with several open invoices is left to a human unless the narration names one.
- I did not benchmark sentence embeddings; I chose not to use them (see `docs/DECISIONS.md`).
- The session cookie is not marked `Secure` because the demo runs over plain HTTP. Put it behind HTTPS for real use.
- One backend instance is assumed (the inbox poller is in-process).
