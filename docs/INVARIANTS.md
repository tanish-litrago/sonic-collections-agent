# Invariants

Rules the code must not break. Each has a test or a single place that enforces it.

1. **Money is never a float.** Amounts are integer minor units (paise/cents) end to end; `money.to_minor` parses with `Decimal`. (`test_money_never_float_and_indian_grouping`)
2. **The LLM never decides money and never types a figure.** It returns an intent and placeholders; code fills numbers from the database. (`test_llm_invented_number_is_rejected`)
3. **Nothing changes an invoice without a person's approval.** Customer claims such as "we paid" are recorded, not applied. Only `/matches/{id}/approve` writes payments.
4. **The LLM only sees the sender's own invoices.** Drafts and other customers' invoices are never in the prompt, and a placeholder for another customer's invoice is rejected. (`test_other_customers_invoice_placeholder_rejected`, `test_draft_invoice_not_in_context`)
5. **Customer emails are untrusted data.** They cannot change instructions or reach other customers' data. Unknown senders never reach the LLM.
6. **Payments are append-only.** Invoice balances change only through a guarded update that succeeds if the balance is still what we read; approving the same row twice returns 409. (`test_double_approval_is_safe`)
7. **Wrong matches cost more than misses.** Below the confidence threshold the answer is "no match"; unknown payers are never preselected. (`test_unknown_payer_is_never_a_confident_match`)
8. **Draft invoices are never chased, quoted or matched.**
9. **Out-of-office and bounce mail is never answered.** (`test_automated_mail_detected`)
10. **No secrets in the repository.** Credentials come from `.env`, which is git-ignored.
