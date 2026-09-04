import { useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import {
  X, ArrowSquareOut, PencilSimple, ArrowUUpLeft, Trash, FloppyDisk, Warning,
} from "@phosphor-icons/react";

const CURRENCY = (n) =>
  `₹${(Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function isSimpleTwoLine(entry) {
  const lines = entry?.lines || [];
  if (lines.length !== 2) return false;
  const debits = lines.filter((l) => (+l.debit || 0) > 0 && (+l.credit || 0) === 0);
  const credits = lines.filter((l) => (+l.credit || 0) > 0 && (+l.debit || 0) === 0);
  return debits.length === 1 && credits.length === 1;
}

// Shared transaction detail — used by the Daybook and every Account Ledger.
// "Simple outside, professional underneath": shows the full double-entry, and
// (for permitted, safe entries) lets the user Edit / Reverse / Delete.
export const TransactionDetail = ({ entry, onClose, onChanged }) => {
  const navigate = useNavigate();
  const [mode, setMode] = useState("view");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmReverse, setConfirmReverse] = useState(false);
  const [form, setForm] = useState({
    date: entry.date || "",
    narration: entry.narration || "",
    reference: entry.reference || "",
    amount: entry.total ?? "",
  });

  const lines = entry.lines || [];
  const totalDr = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalCr = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);

  const source = entry.source || "manual";
  const isReversal = source.endsWith("_reversal");
  const isReversed = !!entry.reversed;
  const canModify = !isReversal && !isReversed;
  const standalone = ["manual", "income", "expense"].includes(source) && !entry.source_id;
  const canDelete = canModify && standalone;
  const canEditAmount = canModify && standalone && isSimpleTwoLine(entry);
  const canOpen = entry.project_id || entry.client_id || ["invoice_payment", "invoice"].includes(source);

  const openSource = () => {
    onClose();
    if (entry.project_id) return navigate(`/projects/${entry.project_id}`);
    if (["invoice_payment", "invoice"].includes(source)) return navigate("/invoices");
    if (entry.client_id) return navigate(`/clients/${entry.client_id}`);
  };

  const saveEdit = async () => {
    setBusy(true);
    try {
      const payload = {
        date: form.date,
        narration: form.narration,
        reference: form.reference,
      };
      if (canEditAmount) payload.amount = Number(form.amount);
      await api.patch(`/journal-entries/${entry.id}`, payload);
      toast.success("Transaction updated");
      onChanged && onChanged();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update transaction");
    } finally {
      setBusy(false);
    }
  };

  const doReverse = async () => {
    setBusy(true);
    try {
      await api.post(`/journal-entries/${entry.id}/reverse`);
      toast.success("Transaction reversed — a balancing entry was posted");
      onChanged && onChanged();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not reverse transaction");
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await api.delete(`/journal-entries/${entry.id}`);
      toast.success("Transaction deleted");
      onChanged && onChanged();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete transaction");
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" data-testid="txn-detail-modal" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[301] w-full max-w-xl bg-white shadow-2xl max-h-[90vh] overflow-auto">
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-[#E5E5E5]">
          <div className="min-w-0">
            <div className="overline text-[#8B7F6A]">TRANSACTION DETAIL</div>
            <div className="font-display font-bold text-xl truncate" data-testid="txn-detail-narration">
              {entry.narration || "Journal entry"}
            </div>
            <div className="text-xs text-[#5C5C5C] mt-0.5 font-mono">
              {entry.date}{entry.reference ? ` · Ref ${entry.reference}` : ""}{entry.created_by_name ? ` · by ${entry.created_by_name}` : ""}
            </div>
            {isReversed && (
              <span className="inline-block mt-2 text-[10px] font-semibold text-[#B4001C] border border-[#B4001C] px-2 py-0.5" data-testid="txn-reversed-badge">
                REVERSED
              </span>
            )}
            {isReversal && (
              <span className="inline-block mt-2 text-[10px] font-semibold text-[#8B7F6A] border border-[#8B7F6A] px-2 py-0.5">
                REVERSAL ENTRY
              </span>
            )}
          </div>
          <button onClick={onClose} className="btn-ghost" data-testid="txn-detail-close"><X size={16} /></button>
        </div>

        {/* EDIT MODE */}
        {mode === "edit" ? (
          <div className="p-5 space-y-3" data-testid="txn-edit-form">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">Date</label>
              <input type="date" className="input-flat w-full" value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="txn-edit-date" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">Description</label>
              <input className="input-flat w-full" value={form.narration}
                onChange={(e) => setForm({ ...form, narration: e.target.value })} data-testid="txn-edit-narration" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">Reference</label>
              <input className="input-flat w-full" value={form.reference}
                onChange={(e) => setForm({ ...form, reference: e.target.value })} data-testid="txn-edit-reference" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">Amount</label>
              <input type="number" step="0.01" className="input-flat w-full" value={form.amount}
                disabled={!canEditAmount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="txn-edit-amount" />
              {!canEditAmount && (
                <div className="text-[11px] text-[#9A9A9A] mt-1 flex items-start gap-1">
                  <Warning size={13} className="mt-0.5 shrink-0" />
                  Amount is locked for this entry (it has GST/splits or is linked). Reverse it and record a new one to change the amount.
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setMode("view")} className="btn-ghost text-sm" data-testid="txn-edit-cancel">Cancel</button>
              <button onClick={saveEdit} disabled={busy} className="btn-primary text-sm" data-testid="txn-edit-save">
                <FloppyDisk size={14} /> {busy ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* VIEW MODE — double entry */}
            <div className="p-5">
              <div className="overline mb-2 text-[#9A9A9A]">ACCOUNTING ENTRY (DEBIT / CREDIT)</div>
              <table className="w-full text-sm">
                <thead className="text-[10px] font-mono uppercase text-[#9A9A9A]">
                  <tr><th className="p-2 text-left">Account</th><th className="p-2 text-right">Debit</th><th className="p-2 text-right">Credit</th></tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={i} className="border-t border-[#F0F0F0]">
                      <td className="p-2">{l.account_name}<span className="text-[10px] text-[#9A9A9A] uppercase ml-1">{l.account_type}</span></td>
                      <td className="p-2 text-right font-mono text-[#1D633E]">{l.debit ? CURRENCY(l.debit) : "—"}</td>
                      <td className="p-2 text-right font-mono text-[#B4001C]">{l.credit ? CURRENCY(l.credit) : "—"}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-[#0A0A0A] font-semibold">
                    <td className="p-2">Total</td>
                    <td className="p-2 text-right font-mono">{CURRENCY(totalDr)}</td>
                    <td className="p-2 text-right font-mono">{CURRENCY(totalCr)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Actions */}
            <div className="p-4 border-t border-[#E5E5E5] flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                {canModify && (
                  <button onClick={() => setMode("edit")} className="btn-ghost text-sm" data-testid="txn-edit-btn">
                    <PencilSimple size={14} /> Edit
                  </button>
                )}
                {canModify && (
                  confirmReverse ? (
                    <span className="flex items-center gap-1">
                      <button onClick={doReverse} disabled={busy} className="btn-primary bg-[#8B7F6A] text-sm" data-testid="txn-reverse-confirm">
                        {busy ? "Reversing…" : "Confirm reverse"}
                      </button>
                      <button onClick={() => setConfirmReverse(false)} className="btn-ghost text-sm">No</button>
                    </span>
                  ) : (
                    <button onClick={() => setConfirmReverse(true)} className="btn-ghost text-sm" data-testid="txn-reverse-btn">
                      <ArrowUUpLeft size={14} /> Reverse
                    </button>
                  )
                )}
              </div>
              <div className="flex items-center gap-2">
                {canOpen && (
                  <button onClick={openSource} className="btn-ghost text-sm" data-testid="txn-open-source">
                    <ArrowSquareOut size={14} /> Open related record
                  </button>
                )}
                {canDelete && (
                  confirmDelete ? (
                    <span className="flex items-center gap-1">
                      <button onClick={doDelete} disabled={busy} className="btn-primary bg-[#B4001C] text-sm" data-testid="txn-delete-confirm">
                        {busy ? "Deleting…" : "Confirm delete"}
                      </button>
                      <button onClick={() => setConfirmDelete(false)} className="btn-ghost text-sm">No</button>
                    </span>
                  ) : (
                    <button onClick={() => setConfirmDelete(true)} className="btn-ghost text-sm text-[#B4001C]" data-testid="txn-delete-btn">
                      <Trash size={14} /> Delete
                    </button>
                  )
                )}
              </div>
            </div>
            {!canModify && (
              <div className="px-4 pb-4 text-[11px] text-[#9A9A9A]">
                This is a {isReversed ? "reversed" : "reversal / system"} entry and is locked to protect your books.
              </div>
            )}
          </>
        )}
      </div>
    </div>,
    document.body
  );
};
