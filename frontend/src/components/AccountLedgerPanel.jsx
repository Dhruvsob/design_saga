import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { PERIOD_PRESETS, computeRange, periodLabel } from "../lib/period";
import { downloadFile } from "../lib/download";
import { TransactionDetail } from "./TransactionDetail";
import {
  X, MagnifyingGlass, Bank, ArrowSquareOut, DownloadSimple, Printer, Plus,
} from "@phosphor-icons/react";

const CURRENCY = (n) =>
  `₹${(Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const today = () => new Date().toISOString().slice(0, 10);

// Slide-over showing one account's complete transaction history.
// Reuses GET /accounting/ledger/account/{id}. Adds inline Quick-Add (for
// expense/income accounts), CSV/Print export, and click-through to the full
// transaction detail (view / edit / reverse / delete).
export const AccountLedgerPanel = ({ account, accounts = [], onClose }) => {
  const [preset, setPreset] = useState("month");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  const banks = useMemo(
    () => (accounts || []).filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name)),
    [accounts]
  );
  const [addForm, setAddForm] = useState({ amount: "", date: today(), bank_id: "", payment_method: "cash", notes: "" });
  useEffect(() => {
    if (!addForm.bank_id && banks[0]) setAddForm((f) => ({ ...f, bank_id: banks[0].id }));
  }, [banks]); // eslint-disable-line

  const canQuickAdd = account && (account.type === "expense" || account.type === "income");

  const rangeQs = useCallback(() => {
    const r = computeRange(preset);
    const fromDate = r ? r.from : from;
    const toDate = r ? r.to : to;
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    return params.toString() ? `?${params.toString()}` : "";
  }, [preset, from, to]);

  const load = useCallback(() => {
    if (!account) return;
    setLoading(true);
    api
      .get(`/accounting/ledger/account/${account.id}${rangeQs()}`)
      .then(({ data }) => setData(data))
      .finally(() => setLoading(false));
  }, [account, rangeQs]);

  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    const all = (data?.rows || []).slice().reverse(); // newest first for reading
    const term = q.trim().toLowerCase();
    if (!term) return all;
    const num = term.replace(/[₹,\s]/g, "");
    return all.filter((r) => {
      const hay = `${r.narration || ""} ${r.reference || ""} ${r.source || ""}`.toLowerCase();
      const amountMatch = num && (String(r.debit).includes(num) || String(r.credit).includes(num));
      return hay.includes(term) || amountMatch;
    });
  }, [data, q]);

  const openTxn = async (journalId) => {
    if (!journalId) return;
    try {
      const { data } = await api.get(`/journal-entries/${journalId}`);
      setDetail(data);
    } catch {
      toast.error("Could not load transaction");
    }
  };

  const exportCsv = () => {
    if (!account) return;
    downloadFile(`/accounting/ledger/account/${account.id}/csv${rangeQs()}`,
      `ledger-${(account.name || "account").toLowerCase().replace(/\s+/g, "-")}.csv`).catch(() => {});
  };

  const submitAdd = async () => {
    const amt = Number(addForm.amount);
    if (!amt || amt <= 0) { toast.error("Enter a valid amount"); return; }
    if (!addForm.bank_id) { toast.error("Select a cash / bank account"); return; }
    try {
      if (account.type === "expense") {
        await api.post("/accounting/expense", {
          date: addForm.date, amount: amt, expense_account_id: account.id,
          paid_from_account_id: addForm.bank_id, payment_method: addForm.payment_method, notes: addForm.notes,
        });
      } else {
        await api.post("/accounting/income", {
          date: addForm.date, amount: amt, income_account_id: account.id,
          bank_account_id: addForm.bank_id, payment_method: addForm.payment_method, notes: addForm.notes,
        });
      }
      toast.success(`${account.type === "expense" ? "Expense" : "Income"} recorded`);
      setShowAdd(false);
      setAddForm((f) => ({ ...f, amount: "", notes: "" }));
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    }
  };

  if (!account) return null;
  const txnCount = data?.rows?.length || 0;

  return createPortal(
    <>
    <div className="fixed inset-0 z-[300] flex justify-end" data-testid="account-ledger-panel" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" data-testid="account-ledger-backdrop" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[301] w-full max-w-3xl h-full bg-white shadow-2xl flex flex-col animate-[slide-in-right_0.2s_ease]">
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-[#E5E5E5]">
          <div>
            <div className="overline text-[#8B7F6A]">ACCOUNT LEDGER</div>
            <div className="font-display font-bold text-2xl flex items-center gap-2" data-testid="ledger-account-name">
              {account.is_bank && <Bank size={18} className="text-[#8B7F6A]" />}
              {account.name}
            </div>
            <div className="text-xs text-[#5C5C5C] uppercase tracking-wide mt-0.5">
              {account.type}{account.code ? ` · ${account.code}` : ""} · {periodLabel(preset, from, to)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={exportCsv} className="btn-ghost text-xs" data-testid="ledger-export-csv"><DownloadSimple size={12} /> CSV</button>
            <button onClick={() => window.print()} className="btn-ghost text-xs" data-testid="ledger-print"><Printer size={12} /> Print</button>
            <button onClick={onClose} className="btn-ghost" data-testid="ledger-close-btn"><X size={16} /></button>
          </div>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-[#E5E5E5] border-b border-[#E5E5E5]">
          <SummaryCell label="Closing balance" value={CURRENCY(data?.closing_balance)} strong testid="ledger-closing" />
          <SummaryCell label="Transactions" value={loading ? "…" : String(rows.length)} testid="ledger-count" />
          <SummaryCell label="Total in (Dr)" value={CURRENCY(data?.total_debit)} tint="#1D633E" testid="ledger-debit" />
          <SummaryCell label="Total out (Cr)" value={CURRENCY(data?.total_credit)} tint="#B4001C" testid="ledger-credit" />
        </div>

        {/* Controls */}
        <div className="p-4 space-y-3 border-b border-[#E5E5E5]">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex flex-wrap gap-1.5" data-testid="ledger-presets">
              {PERIOD_PRESETS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setPreset(p.id)}
                  data-testid={`ledger-preset-${p.id}`}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    preset === p.id
                      ? "bg-[#0A0A0A] text-white border-[#0A0A0A]"
                      : "bg-white text-[#5C5C5C] border-[#E5E5E5] hover:border-[#8B7F6A]"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {canQuickAdd && (
              <button onClick={() => setShowAdd((s) => !s)}
                className={`btn-primary text-xs ${account.type === "income" ? "bg-[#1D633E]" : "bg-[#B4001C]"}`}
                data-testid="ledger-quickadd-btn">
                <Plus size={13} /> {showAdd ? "Cancel" : `Record ${account.type}`}
              </button>
            )}
          </div>

          {showAdd && canQuickAdd && (
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2 p-3 bg-[#FAFAF7] border border-[#E5E5E5]" data-testid="ledger-quickadd-form">
              <input type="number" step="0.01" placeholder="Amount" className="input-flat" value={addForm.amount}
                onChange={(e) => setAddForm({ ...addForm, amount: e.target.value })} data-testid="ledger-add-amount" />
              <input type="date" className="input-flat" value={addForm.date}
                onChange={(e) => setAddForm({ ...addForm, date: e.target.value })} data-testid="ledger-add-date" />
              <select className="input-flat" value={addForm.bank_id}
                onChange={(e) => setAddForm({ ...addForm, bank_id: e.target.value })} data-testid="ledger-add-bank">
                <option value="" disabled>Cash / Bank</option>
                {banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <select className="input-flat" value={addForm.payment_method}
                onChange={(e) => setAddForm({ ...addForm, payment_method: e.target.value })}>
                {["cash", "bank_transfer", "upi", "cheque", "credit_card", "online", "other"].map((m) => <option key={m}>{m}</option>)}
              </select>
              <button onClick={submitAdd} className="btn-primary" data-testid="ledger-add-submit">Save</button>
              <input className="input-flat md:col-span-5" placeholder="Note (optional)" value={addForm.notes}
                onChange={(e) => setAddForm({ ...addForm, notes: e.target.value })} data-testid="ledger-add-notes" />
            </div>
          )}

          {preset === "custom" && (
            <div className="flex items-center gap-2 text-xs">
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="input-flat" data-testid="ledger-from" />
              <span className="text-[#9A9A9A]">→</span>
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="input-flat" data-testid="ledger-to" />
            </div>
          )}
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9A9A9A]" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search description, reference or amount…"
              className="input-flat w-full pl-9"
              data-testid="ledger-search"
            />
          </div>
        </div>

        {/* Ledger table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C] z-10">
              <tr>
                <th className="p-3 text-left">Date</th>
                <th className="p-3 text-left">Description</th>
                <th className="p-3 text-right">Debit</th>
                <th className="p-3 text-right">Credit</th>
                <th className="p-3 text-right">Balance</th>
              </tr>
            </thead>
            <tbody data-testid="ledger-rows">
              {rows.map((r, i) => (
                <tr key={`${r.journal_id}-${i}`}
                  onClick={() => openTxn(r.journal_id)}
                  className="border-t border-[#F0F0F0] hover:bg-[#FAFAF7] cursor-pointer"
                  data-testid={`ledger-row-${r.journal_id}`}>
                  <td className="p-3 font-mono text-xs whitespace-nowrap">{r.date}</td>
                  <td className="p-3">
                    <div>{r.narration || "—"}</div>
                    {r.reference && <div className="text-[10px] text-[#9A9A9A] font-mono">Ref: {r.reference}</div>}
                  </td>
                  <td className="p-3 text-right font-mono text-[#1D633E]">{r.debit ? CURRENCY(r.debit) : "—"}</td>
                  <td className="p-3 text-right font-mono text-[#B4001C]">{r.credit ? CURRENCY(r.credit) : "—"}</td>
                  <td className="p-3 text-right font-mono font-semibold">{CURRENCY(r.balance)}</td>
                </tr>
              ))}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-10 text-center text-[#9A9A9A]">
                    {txnCount === 0 ? "No transactions in this period." : "No matches for your search."}
                  </td>
                </tr>
              )}
              {loading && (
                <tr><td colSpan={5} className="p-10 text-center overline">LOADING…</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-3 border-t border-[#E5E5E5] text-[10px] text-[#9A9A9A] flex items-center gap-1">
          <ArrowSquareOut size={12} /> Opening balance {CURRENCY(data?.opening_balance)} · click any row to view, edit or reverse it
        </div>
      </div>
    </div>

      {detail && (
        <TransactionDetail
          entry={detail}
          onClose={() => setDetail(null)}
          onChanged={() => { setDetail(null); load(); }}
        />
      )}
    </>,
    document.body
  );
};

const SummaryCell = ({ label, value, tint, strong, testid }) => (
  <div className="bg-white p-3" data-testid={testid}>
    <div className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">{label}</div>
    <div className={`font-mono ${strong ? "font-bold text-lg" : "text-sm font-semibold"}`} style={tint ? { color: tint } : undefined}>
      {value}
    </div>
  </div>
);
