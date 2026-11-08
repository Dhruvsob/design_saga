import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { X, ArrowSquareOut } from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate, formatINR } from "../lib/format";
import { TransactionDetail } from "./TransactionDetail";

const STATUS = { received: ["Received", "chip-paid"], reversed: ["Reversed", "chip-cancelled"] };

/**
 * Every receipt recorded against one collection, each opening its accounting
 * entry. Corrections happen in that entry (Delete reverses the receipt), so the
 * collection, reminder, ledgers and reports stay on one record.
 */
export default function CollectionEntries({ row, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [detail, setDetail] = useState(null);
  const load = () => api.get(`/accounting/collections/${row.source_type}/${row.id}/entries`)
    .then(({ data: d }) => setData(d))
    .catch((e) => { setData({ receipts: [] }); toast.error(e?.response?.data?.detail || "Could not load receipts"); });
  useEffect(() => { load(); }, [row.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose} data-testid="collection-entries">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[291] w-full max-w-2xl bg-white shadow-2xl max-h-[90vh] overflow-auto">
        <div className="flex items-start justify-between p-5 border-b border-[var(--line)]">
          <div className="min-w-0">
            <div className="overline text-[var(--accent-strong)]">RECEIPTS &amp; ENTRIES</div>
            <div className="font-display font-bold text-xl truncate">{row.name || "Collection"}</div>
            <div className="text-xs text-[var(--ink-2)] mt-0.5">
              {row.party_name || row.client_name || row.vendor_name || ""}{row.project_name ? ` · ${row.project_name}` : ""}
              {" · expected "}{formatINR(row.amount)}
            </div>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5">
          {data === null && <div className="overline">LOADING…</div>}
          {data && data.receipts.length === 0 && (
            <div className="text-sm text-[var(--ink-3)] py-6 text-center">Nothing received yet. Use Receive to record a payment.</div>
          )}
          {data && data.receipts.length > 0 && (
            <table className="w-full text-sm" data-testid="collection-entries-table">
              <thead><tr className="overline text-left border-b border-[var(--line)]">
                <th className="py-2">Date</th><th className="py-2">Into</th><th className="py-2">Reference</th>
                <th className="py-2 text-right">Amount</th><th className="py-2">Status</th><th className="py-2" />
              </tr></thead>
              <tbody>{data.receipts.map((r) => {
                const [label, chip] = STATUS[r.status] || [r.status, "chip-draft"];
                return (
                  <tr key={r.id} className="border-b border-[var(--line-soft)]">
                    <td className="py-2 text-xs whitespace-nowrap">{formatDate(r.date)}</td>
                    <td className="py-2 text-xs">{r.account || "—"}</td>
                    <td className="py-2 text-xs font-mono">{r.reference || "—"}</td>
                    <td className="py-2 text-right tabular-nums font-semibold">{formatINR(r.amount)}
                      {r.receipt_total && r.receipt_total !== r.amount && <div className="text-[10px] font-normal text-[var(--ink-3)]">of a {formatINR(r.receipt_total)} receipt</div>}</td>
                    <td className="py-2"><span className={`status-chip ${chip}`}>{label}</span></td>
                    <td className="py-2 text-right">
                      {r.journal && (
                        <button type="button" className="btn-ghost text-xs" onClick={() => setDetail(r.journal)} data-testid={`collection-entry-open-${r.id}`}>
                          <ArrowSquareOut size={13} /> Open entry
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
          <p className="mt-4 text-[11px] text-[var(--ink-3)]">To correct a wrong receipt, open its entry and choose Delete: the receipt is reversed, the amount is due again and its reminder comes back.</p>
        </div>
      </div>
      {detail && (
        <TransactionDetail entry={detail} onClose={() => setDetail(null)}
          onChanged={() => { setDetail(null); load(); onChanged && onChanged(); }} />
      )}
    </div>,
    document.body,
  );
}
