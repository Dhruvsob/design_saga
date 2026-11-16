import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { MagnifyingGlass, Star, X } from "@phosphor-icons/react";
import api from "../lib/api";
import AuthImage from "./AuthImage";
import { formatINR } from "../lib/format";

/**
 * Pick a product from the studio library; the parent receives a ready BOQ line
 * (a snapshot of name, specs, unit, latest price and vendor from /products/{id}/boq-line).
 */
export default function ProductPicker({ room, onPick, onClose }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      api.get("/products", { params: { q: q.trim() || undefined, page_size: 30 } })
        .then(({ data }) => alive && setRows(data.items || []))
        .catch((e) => { if (alive) { setRows([]); toast.error(e?.response?.data?.detail || "Could not load the library"); } });
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [q]);

  const pick = async (p) => {
    setBusy(p.id);
    try {
      const { data } = await api.get(`/products/${p.id}/boq-line`, { params: { room: room || undefined } });
      onPick(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not add this product"); setBusy(null); }
  };

  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Add from product library" data-testid="product-picker"
        className="relative z-[291] w-full max-w-2xl bg-white shadow-2xl max-h-[88vh] flex flex-col">
        <div className="flex items-center gap-3 p-4 border-b border-[var(--line)]">
          <div className="font-display font-bold text-lg mr-auto">Add from product library</div>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-4 border-b border-[var(--line-soft)]">
          <label className="relative block">
            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
            <input autoFocus className="input-flat w-full pl-8" placeholder="Search name, brand, model, SKU" aria-label="Search products"
              value={q} onChange={(e) => setQ(e.target.value)} data-testid="product-picker-search" />
          </label>
        </div>
        <div className="overflow-y-auto">
          {rows === null && <div className="overline p-4">LOADING…</div>}
          {rows && rows.length === 0 && (
            <p className="p-6 text-sm text-[var(--ink-3)]">{q ? "No products match." : "The library is empty. Add products under Procurement → Library."}</p>
          )}
          <ul className="divide-y divide-[var(--line-soft)]">
            {(rows || []).map((p) => (
              <li key={p.id}>
                <button type="button" disabled={busy === p.id} onClick={() => pick(p)} data-testid={`pick-${p.id}`}
                  className="w-full text-left flex items-center gap-3 p-3 hover:bg-[var(--surface-2)] disabled:opacity-60">
                  <AuthImage src={p.cover_url} alt="" className="w-14 h-11 object-cover shrink-0" fallbackClassName="w-14 h-11 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm truncate">{p.preferred && <Star size={11} weight="fill" className="inline text-[var(--accent-strong)] mr-1" />}{p.name}</div>
                    <div className="text-xs text-[var(--ink-2)] truncate">{[p.brand, p.model, p.category].filter(Boolean).join(" · ") || "—"}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-mono text-sm">{p.latest_price ? formatINR(p.latest_price.price) : "No price"}</div>
                    <div className="text-[11px] text-[var(--ink-3)]">{p.latest_price ? `/ ${p.latest_price.unit}` : ""}</div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <p className="p-3 text-[11px] text-[var(--ink-3)] border-t border-[var(--line-soft)]">
          The line copies the product's details and latest price now; later library changes do not alter this quotation.
        </p>
      </div>
    </div>, document.body);
}
