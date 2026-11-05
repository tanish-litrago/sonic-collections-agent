export async function api(path, opts = {}) {
  const isForm = opts.body instanceof FormData;
  const r = await fetch("/api" + path, {
    credentials: "include",
    ...opts,
    headers: opts.body && !isForm ? { "Content-Type": "application/json" } : undefined,
  });
  if (r.status === 401 && path !== "/login") {
    window.dispatchEvent(new Event("auth-lost"));
    throw new Error("Please log in");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${r.status})`);
  return data;
}
export const post = (path, body) => api(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// Money arrives as integer minor units (paise/cents). Display only.
export const money = (minor, cur) =>
  new Intl.NumberFormat(cur === "INR" ? "en-IN" : "en-US", { style: "currency", currency: cur }).format(minor / 100);

export const SETTLE = { full: "Apply payment", close_tds: "Close invoice (TDS deducted)", leave_open: "Leave balance open" };
