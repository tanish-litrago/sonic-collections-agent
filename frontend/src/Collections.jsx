import React, { useState } from "react";
import { api, post } from "./api.js";
import { useLoad, Err } from "./shared.jsx";

const TONE = { needs_attention: "bad", replied: "ok", automated: "warn", resolved: "info" };
const LABEL = { needs_attention: "Needs attention", replied: "Replied", automated: "Automated mail", resolved: "Resolved" };

export default function Collections() {
  const [tab, setTab] = useState("needs_attention");
  const [convs, err, reload] = useLoad("/conversations?status=" + tab);
  const [busy, setBusy] = useState(""); const [msg, setMsg] = useState(""); const [e2, setE2] = useState("");
  async function run(kind, fn) {
    setBusy(kind); setMsg(""); setE2("");
    try { setMsg(await fn()); reload(); } catch (e) { setE2(e.message); } finally { setBusy(""); }
  }
  const sendReminders = () => run("rem", async () => {
    const r = await post("/reminders/send");
    const n = r.sent.reduce((a, s) => a + s.invoices.length, 0);
    return `Sent ${r.sent.length} reminder email(s) covering ${n} invoice(s). ${r.skipped_cooldown.length} skipped (reminded in the last 3 days).` + (r.failed.length ? ` ${r.failed.length} failed to send.` : "");
  });
  const checkInbox = () => run("inbox", async () => `Checked inbox: ${(await post("/inbox/check")).processed} new email(s) processed.`);
  const resolve = (id) => api(`/conversations/${encodeURIComponent(id)}/resolve`, { method: "POST" }).then(reload).catch((e) => setE2(e.message));
  return (
    <>
      <h1>Collections</h1>
      <p className="hint">Reminders go to customers with overdue invoices. Replies are read from the inbox every minute, or on demand.</p>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className="btn" onClick={sendReminders} disabled={!!busy}>{busy === "rem" ? "Sending…" : "Send reminders"}</button>
        <button className="btn secondary" onClick={checkInbox} disabled={!!busy}>{busy === "inbox" ? "Checking…" : "Check inbox now"}</button>
      </div>
      {msg && <div className="banner success">{msg}</div>}
      <Err msg={e2 || err} />
      <div className="tabs">
        {Object.entries(LABEL).map(([k, l]) => <button key={k} className={"btn " + (tab === k ? "" : "secondary")} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {convs && convs.length === 0 && <p className="muted">Nothing here.</p>}
      {(convs || []).map((c) => (
        <div className="card" key={c._id}>
          <div className="row"><span className={"badge " + (TONE[c.status] || "info")}>{LABEL[c.status] || c.status}</span>
            <b>{c.subject || "(no subject)"}</b><span className="muted">from {c.from}</span></div>
          {c.reason && <p className="muted" style={{ margin: "6px 0" }}>{c.reason}</p>}
          {c.summary && <p style={{ margin: "6px 0" }}>Summary: {c.summary}</p>}
          {c.claimed_invoices?.length > 0 && <p style={{ margin: "6px 0" }}>Customer mentions: {c.claimed_invoices.join(", ")}{c.claimed_date ? ` (date: ${c.claimed_date})` : ""}. Not marked paid until it appears in a bank statement.</p>}
          <pre className="body">{c.body}</pre>
          {c.reply && <><div className="muted">Reply {c.status === "replied" ? "sent" : "drafted, not sent"}:</div><pre className="body">{c.reply}</pre></>}
          {c.status === "needs_attention" && <button className="btn secondary" onClick={() => resolve(c._id)}>Mark resolved</button>}
        </div>
      ))}
    </>
  );
}
