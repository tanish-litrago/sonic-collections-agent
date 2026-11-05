import React, { useEffect, useState } from "react";
import { api } from "./api.js";

export function useLoad(path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = () => api(path).then((d) => { setData(d); setError(""); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [path]);
  return [data, error, load];
}
export const Err = ({ msg }) => (msg ? <div className="banner error" role="alert">{msg}</div> : null);

export const Loading = () => (
  <div className="skeleton" role="status" aria-label="Loading"><span /><span /><span /></div>
);
export const Empty = ({ children }) => <div className="empty">{children}</div>;
