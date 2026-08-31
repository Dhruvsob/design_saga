import { useEffect, useState } from "react";
import api from "../lib/api";

// Module-level cache so every dropdown across the app shares one fetch.
let _cache = null;
let _promise = null;

export function invalidateMasterData() {
  _cache = null;
  _promise = null;
}

export default function useMasterData() {
  const [data, setData] = useState(_cache);

  useEffect(() => {
    if (_cache) { setData(_cache); return; }
    if (!_promise) {
      _promise = api.get("/master-data").then((r) => { _cache = r.data; return _cache; })
        .catch(() => { _promise = null; return null; });
    }
    _promise.then((d) => { if (d) setData(d); });
  }, []);

  // labels for a kind (active only), with a graceful fallback list
  const values = (kind, fallback = []) => {
    const rows = data?.data?.[kind] || [];
    const labels = rows.filter((r) => r.is_active !== false).map((r) => r.label);
    return labels.length ? labels : fallback;
  };

  return { md: data, values, loaded: !!data };
}
