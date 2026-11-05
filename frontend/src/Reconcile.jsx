import React, { useState } from "react";
import { api, post, money, SETTLE } from "./api.js";
import { useLoad, Err } from "./shared.jsx";

const TONE = { match: "ok", low_confidence: "warn", no_match: "bad", ignored: "info" };
const LABEL = { match: "Match", low_confidence: "Low confidence", no_match: "No match", ignored: "Ignored" };

function Row({ m, reload, setErr }) {
  const r = m.result, s = r.suggestion, low = r.status === "low_confidence";
  const [settle, setSettle] = useState(s?.settle || "full"); const [ok, setOk] = useState(false); const [busy, setBusy] = useState(false);
  async function act(kind) {
    setBusy(true); setErr("");
    try {
      if (kind === "approve") await post(`/matches/${m._id}/approve`, { invoice_numbers: s.invoice_numbers, settle, confirm_low_confidence: low && ok });
      else await post(`/matches/${m._id}/reject`);
      await reload();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  const pending = m.state === "pending";
  return (
    <tr>
      <td className="mono">{m.txn.date}</td>
      <td className="mono">{m.txn.narration}</td>
      <td className="num">{money(m.txn.amount, m.txn.currency)}</td>
      <td><span className={"badge " + TONE[r.status]}>{LABEL[r.status]}</span></td>
      <td>
        {s ? <><b>{s.invoice_numbers.join(" + ")}</b> <span className="muted mono">score {s.score}</span><div>{s.reason}</div></> : <span className="muted">{r.reason}</span>}
        {r.evidence?.map((e) => (
          <div key={e.conversation_id} className="evidence">
            <b>Customer email</b> <span className="muted">({e.via}{e.consistent === false ? ", different customer" : ""})</span>
            <div>{e.subject} <span className="muted">from {e.from}</span></div>
            <div className="muted">{e.snippet}</div>
          </div>
        ))}
        {r.alternatives?.length > 0 && <div className="muted">Also possible: {r.alternatives.join(", ")}</div>}
      </td>
      <td>
        {s && pending && (
          <div>
            {s.settle_options.length > 1 && (
              <select aria-label="How to settle" value={settle} onChange={(e) => setSettle(e.target.value)}>
                {s.settle_options.map((o) => <option key={o} value={o}>{SETTLE[o]}</option>)}
              </select>
            )}
            {low && <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--warn)" }}><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> I checked {s.invoice_numbers[0]} myself</label>}
            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn" disabled={busy || (low && !ok)} onClick={() => act("approve")}>Approve</button>
              <button className="btn danger" disabled={busy} onClick={() => act("reject")}>Reject</button>
            </div>
          </div>
        )}
        {s && !pending && <span className={"badge " + (m.state === "approved" ? "ok" : "bad")}>{m.state}</span>}
      </td>
    </tr>
  );
}

export default function Reconcile() {
  const [rows, err, reload] = useLoad("/matches");
  const [e2, setE2] = useState(""); const [busy, setBusy] = useState(false);
  async function upload(e) {
    const f = e.target.files[0]; if (!f) return;
    setBusy(true); setE2("");
    const fd = new FormData(); fd.append("file", f);
    try { await api("/reconcile", { method: "POST", body: fd }); await reload(); } catch (x) { setE2(x.message); } finally { setBusy(false); e.target.value = ""; }
  }
  return (
    <>
      <h1>Bank reconciliation</h1>
      <p className="hint">Upload a bank statement CSV. Matching runs locally; nothing is applied until you approve it.</p>
      <div className="card">
        <label htmlFor="f" style={{ marginTop: 0 }}>Statement CSV (columns: txn_date, narration, reference, credit, debit, currency)</label>
        <input id="f" type="file" accept=".csv,text/csv" onChange={upload} disabled={busy} />
        {busy && <span className="muted"> Matching…</span>}
      </div>
      <Err msg={e2 || err} />
      {rows && rows.length > 0 && (
        <div className="scroll"><table>
          <thead><tr><th>Date</th><th>Narration</th><th className="num">Amount</th><th>Result</th><th>Suggestion</th><th>Action</th></tr></thead>
          <tbody>{rows.map((m) => <Row key={m._id + m.state} m={m} reload={reload} setErr={setE2} />)}</tbody>
        </table></div>
      )}
    </>
  );
}
