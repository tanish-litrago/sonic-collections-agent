# Decisions

Format: what I picked, what I rejected, why.

**1. Matching: hard filters plus a hand-weighted additive score.** Rejected: training a model, and letting the LLM pick.
There are 27 invoices and no labelled history, so a model would have nothing to learn from, and an LLM match cannot be
checked. A weighted score gives a one-line reason per match, which a reviewer can audit.

**2. Name similarity: normalised token coverage, rapidfuzz token-set ratio, and char 3-gram TF-IDF cosine, combined.**
Bank narrations abbreviate (`ORBIS PKG`, `SAFFRON PEAK HOSP`). Token coverage with prefix/subsequence matching handles
that; n-grams add tolerance for typos; token-set ratio handles word order. Rejected: Levenshtein alone (fails on
abbreviations) and local sentence embeddings (extra heavy dependency in the setup; I did not benchmark them, so this is a
judgement, not a measured result). Weights were tuned by hand on the sample and the synthetic cases.

**3. Replies: LLM returns JSON with placeholders; code fills figures; a validator rejects stray digits.** Rejected:
letting the LLM write the full email and then checking it. Placeholders make wrong numbers impossible by construction.
Reminder emails use a fixed template, because nothing in them needs generation.

**4. Money as integer minor units.** Rejected: floats (rounding) and Decimal128 in Mongo (more conversion code).
All four currencies have two decimals.

**5. Append-only payments plus a guarded atomic invoice update.** Rejected: Mongo multi-document transactions (need a
replica set, which complicates `docker compose up`). The guard on the old balance plus claiming the match row first
makes double approval safe.

**6. Precision first.** Suggest only at score 45 or more; ambiguous equal invoices choose the oldest at a lower score;
unknown payers cap at 40 and need an explicit confirmation. A short payment with two possible invoices stays unmatched.

**7. TDS: preselect only on an exact amount.** Total minus 10% of the subtotal, Indian customers only. Any other
shortfall is a partial payment and leaves the balance open.

**8. Inbox: IMAP polling every 60 s plus a button.** Rejected: webhooks (need a public URL). Reminders are a button
with a 3-day cooldown per invoice, so a grader cannot flood an inbox.

**9. One admin login with a signed cookie.** The assignment needs no user management. Added rate limits on login and
upload, strict CORS, input validation, and a 1 MB CSV cap.

**10. Evidence linking is deterministic.** A customer email links to a bank row by exact bank reference or invoice number,
not by LLM. It can nudge a score or promote a low-confidence row; a person still approves.

**11. MongoDB.** Invoices carry nested line items and the payments and conversations collections are naturally documents.

**12. The inbox check reads unread mail only.** Rejected: reading recent mail by date and skipping known Message-IDs. *Reset demo data* clears the stored conversations, so old emails would look new and be answered a second time. The cost is that opening a reply in the Gmail web page hides it from the check; the README says so and how to recover.

**13. LLM failures never block the inbox.** A transient error (429, 5xx) is retried three times with backoff; any other failure, or invalid JSON, sends the email to *Needs attention*. The model name is configurable because a free-tier key may not have access to a given model.
