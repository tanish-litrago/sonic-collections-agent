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
