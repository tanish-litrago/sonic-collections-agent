# Build log

Real problems met while building, how they were found, what changed.

- **Wrong label in my own eval (matcher).** A ₹30,000 payment from Redwood was labelled as a match for INV-1016, but Redwood
  has two open invoices, so it is ambiguous. The matcher was right and the label wrong; I relabelled it "no match, left to a human".
- **Rate limit tripped my own tests.** The test fixture logged in once per test and hit the 5-per-minute login limit (HTTP 429).
  The limiter works; the fixture now clears its state.
- **"Latest batch" returned a stale upload.** The matches list picked the latest batch by sorting on a random UUID. Found by
  reading the code before the UI test; added `created_at`, sorted on it, and added a regression test.
- **Reason text lost its capitals.** `.capitalize()` lowercased the rest ("payer matches kestrel", "tds"). Found in a screenshot; fixed.
- **Circular import in the frontend.** Pages imported helpers from `App.jsx`, which imports the pages. Moved the helpers to `shared.jsx`.
- **Fresh install showed an empty app.** The database was only seeded by a command or the reset button. The backend now seeds an empty database on startup (tested).
- **Normal emails were filed as "automated" (found in the live Gmail test).** The mail reader fills missing headers with empty strings, and my check treated any `Auto-Submitted` value other than "no" as an auto-reply, so an empty string counted. Every ordinary customer email was recorded as automated, never answered, and hidden under the Automated tab, which is why *Needs attention* looked empty. My unit test only used absent headers, never empty ones. Fixed by ignoring empty values; a test with empty headers now covers it.
- **Gemini model name and 503 errors.** The default model returned 404 for my key, and another alias returned frequent 503s. The model is now set with `GEMINI_MODEL`, and the call retries three times with backoff on 429 and 5xx before the email is sent to a person.
- **"Check inbox now" showed 0 emails after I opened the reply in the browser.** The inbox check reads only unread mail, and Gmail marks a message read when it is opened. I kept the design and documented it in the README (see decision 12).
