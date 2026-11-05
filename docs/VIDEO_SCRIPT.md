# Video script (2.5 to 3 minutes). Loom, unlisted.

0:00 Hook. "This is AcmeCorp's collections and reconciliation tool. It chases overdue invoices, answers customer emails, and matches bank statements. A person approves every payment. The LLM never touches money."

0:20 Architecture (show README diagram). React front end, FastAPI back end, MongoDB. Matching is local code. The LLM only classifies emails and drafts text with placeholders.

0:45 Invoices page. Filter overdue, show days overdue, expand one invoice. Mention drafts are never chased.

1:05 Collections. Click Send reminders. Show the email arrive. Reply from the test mailbox asking for a balance. Click Check inbox now. Show the automatic reply with exact figures. Then send a dispute: show it land in Needs attention.

1:45 Why the figures are safe. Show a draft with a number the LLM invented being rejected (test name: test_llm_invented_number_is_rejected). Placeholders filled from the database.

2:00 Reconciliation. Upload the sample statement. Walk three rows: Quillon (TDS preselected), Saffron Peak (one payment, three invoices), R K Sharma (low confidence, checkbox needed). Approve one and show the invoice balance change.

2:35 Evidence and honesty. Show eval/report.md: full matcher vs two baselines. Say it is my own labelled set. Mention known gaps from the README.

2:50 Close. "Everything runs with docker compose up. Thanks."
