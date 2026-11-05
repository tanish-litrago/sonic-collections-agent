import React, { useEffect, useState } from "react";
import { api, post, money } from "./api.js";
import { useLoad, Err, Loading, Empty } from "./shared.jsx";
import Collections from "./Collections.jsx";
import Reconcile from "./Reconcile.jsx";

function Login({ onDone }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setBusy(true);
    try { await post("/login", { username: u, password: p }); onDone(); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  return (
    <form className="card login" onSubmit={submit}>
      <h1>AcmeCorp Collections</h1>
      <p className="hint">Accounts team login</p>
      <Err msg={err} />
      <label htmlFor="u">Username</label>
      <input id="u" type="text" value={u} onChange={(e) => setU(e.target.value)} autoFocus />
      <label htmlFor="p">Password</label>
      <input id="p" type="password" value={p} onChange={(e) => setP(e.target.value)} />
      <button className="btn" disabled={busy || !u || !p}>
        {busy ? "Signing in..." : "Log in"}
      </button>
    </form>
  );
}

function Organization() {
  const [o, err] = useLoad("/organization");
  if (err) return <Err msg={err} />;
  if (!o) return <Loading />;
  const b = o.bank_details || {};
  return (
    <>
      <h1>{o.name}</h1><p className="hint">Organization details</p>
      <div className="card">
        <p>{o.address}</p>
        <p>{o.accounts_contact_name} · {o.accounts_email} · {o.phone}</p>
        <p>Default currency: <b>{o.default_currency}</b> · Accepted: {(o.accepted_currencies || []).join(", ")}</p>
        <p>{o.payment_terms}</p>
        <p>Payment methods: {(o.payment_methods || []).join(", ")}</p>
      </div>
      {Object.keys(b).length > 0 && (
        <div className="card"><b>Bank details</b>
          {Object.entries(b).map(([k, v]) => <div key={k}><span className="muted">{k.replace(/_/g, " ")}: </span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>)}
        </div>
      )}
    </>
  );
}

function CustomerRow({ c, reload }) {
  const [v, setV] = useState(c.contact_email); const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  async function save() {
    try { await api(`/customers/${c._id}`, { method: "PATCH", body: JSON.stringify({ contact_email: v }) }); setMsg("Saved"); setErr(""); reload(); }
    catch (e) { setErr(e.message); setMsg(""); }
  }
  return (
    <tr>
      <td>{c.name}<div className="muted">{c.contact_name}</div></td>
      <td>{c.city}, {c.country}</td><td>{c.currency}</td>
      <td>
        <div className="row">
          <input type="email" aria-label={`Contact email for ${c.name}`} value={v} onChange={(e) => { setV(e.target.value); setMsg(""); }} size={30} />
          <button className="btn secondary" onClick={save} disabled={v === c.contact_email}>Save</button>
          {msg && <span className="badge ok">{msg}</span>}
        </div>
        {err && <div style={{ color: "var(--bad)" }}>{err}</div>}
      </td>
    </tr>
  );
}

function Customers() {
  const [cs, err, load] = useLoad("/customers");
  return (
    <>
      <h1>Customers</h1><p className="hint">Set a customer's email to your test inbox to try reminders and replies.</p>
      <Err msg={err} />
      {!cs && !err && <Loading />}
      {cs && <div className="scroll"><table>
        <thead><tr><th>Customer</th><th>Location</th><th>Currency</th><th>Contact email</th></tr></thead>
        <tbody>{(cs || []).map((c) => <CustomerRow key={c._id + c.contact_email} c={c} reload={load} />)}</tbody>
      </table></div>}
    </>
  );
}

function Invoices() {
  const [invs, err] = useLoad("/invoices");
  const [filter, setFilter] = useState("all"); const [open, setOpen] = useState(null);
  const rows = (invs || []).filter((i) => filter === "all" || (filter === "overdue" ? i.overdue : i.status === filter));
  const tone = { paid: "ok", sent: "info", draft: "warn", void: "bad" };
  return (
    <>
      <h1>Invoices</h1><p className="hint">Balances are in each invoice's own currency.</p>
      <Err msg={err} />
      <div className="tabs">
        {["all", "overdue", "sent", "paid", "draft"].map((f) => (
          <button key={f} className={"btn " + (filter === f ? "" : "secondary")} onClick={() => setFilter(f)}>{f[0].toUpperCase() + f.slice(1)}</button>
        ))}
      </div>
      {!invs && !err && <Loading />}
      {invs && rows.length === 0 && <Empty>No invoices match this filter.</Empty>}
      {invs && rows.length > 0 && <div className="scroll"><table>
        <thead><tr><th>Invoice</th><th>Customer</th><th>Issued</th><th>Due</th><th className="num">Total</th><th className="num">Paid</th><th className="num">Balance</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((i) => (
            <React.Fragment key={i._id}>
              <tr>
                <td><button className="btn secondary" aria-expanded={open === i._id} onClick={() => setOpen(open === i._id ? null : i._id)}>{i.invoice_number}</button></td>
                <td>{i.customer_name}</td><td className="mono">{i.invoice_date}</td><td className="mono">{i.due_date}</td>
                <td className="num">{money(i.total, i.currency)}</td><td className="num">{money(i.amount_paid, i.currency)}</td><td className="num">{money(i.balance_due, i.currency)}</td>
                <td><span className={"badge " + (tone[i.status] || "info")}>{i.status}</span>{i.overdue && <> <span className="badge bad">{i.days_overdue} days overdue</span></>}</td>
              </tr>
              {open === i._id && (
                <tr><td colSpan={8}>
                  <div className="muted">PO {i.po_number || "-"} · {i.payment_terms} · {i.tax_name}</div>
                  <table><thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Unit price</th><th className="num">Amount</th></tr></thead>
                    <tbody>{i.line_items.map((l, n) => <tr key={n}><td>{l.description}</td><td className="num">{l.quantity}</td><td className="num">{money(l.unit_price, i.currency)}</td><td className="num">{money(l.amount, i.currency)}</td></tr>)}</tbody></table>
                </td></tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table></div>}
    </>
  );
}

const PAGES = { organization: ["Organization", Organization], customers: ["Customers", Customers], invoices: ["Invoices", Invoices], collections: ["Collections", Collections], reconciliation: ["Reconciliation", Reconcile] };

export default function App() {
  const [authed, setAuthed] = useState(null); const [info, setInfo] = useState({});
  const [page, setPage] = useState(location.hash.slice(1) in PAGES ? location.hash.slice(1) : "invoices");
  const [note, setNote] = useState("");
  const check = () => api("/me").then((d) => { setInfo(d); setAuthed(true); }).catch(() => setAuthed(false));
  useEffect(() => { check(); const f = () => setAuthed(false); window.addEventListener("auth-lost", f); return () => window.removeEventListener("auth-lost", f); }, []);
  useEffect(() => { location.hash = page; }, [page]);
  if (authed === null) return <p className="muted" style={{ padding: 20 }}>Loading…</p>;
  if (!authed) return <Login onDone={check} />;
  const Page = PAGES[page][1];
  async function reset() {
    if (!confirm("Reset all demo data? Payments, emails and matches will be wiped.")) return;
    try { await post("/reset"); setNote("Demo data reset"); setPage("invoices"); setTimeout(() => location.reload(), 600); } catch (e) { setNote(e.message); }
  }
  return (
    <>
      <header>
        <span className="brand">AcmeCorp Collections</span>
        {Object.entries(PAGES).map(([k, [label]]) => <button key={k} className={"nav " + (page === k ? "active" : "")} onClick={() => setPage(k)}>{label}</button>)}
        <span className="spacer" />
        <button className="btn secondary" onClick={reset}>Reset demo data</button>
        <button className="nav" onClick={async () => { await post("/logout"); setAuthed(false); }}>Log out</button>
      </header>
      <main>
        {note && <div className="banner success">{note}</div>}
        {!info.mail_configured && page === "collections" && <div className="banner error">Email is not configured. Set MAIL_USER and MAIL_PASSWORD in .env and restart.</div>}
        <Page info={info} />
      </main>
    </>
  );
}
