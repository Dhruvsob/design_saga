import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { PERIOD_PRESETS, computeRange, periodLabel } from "../lib/period";
import {
  MagnifyingGlass, ArrowDown, ArrowUp, ArrowsLeftRight,
  X, ArrowSquareOut, CaretRight,
} from "@phosphor-icons/react";

const CURRENCY = (n) =>
  `₹${(Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function classify(entry) {
  const lines = entry.lines || [];
  const src = entry.source || "";
  const hasIncome = lines.some((l) => l.account_type === "income" && (l.credit || 0) > 0);
  const hasExpense = lines.some((l) => l.account_type === "expense" && (l.debit || 0) > 0);
  if (hasIncome || ["income", "invoice_payment", "milestone_payment"].includes(src)) return "in";
  if (hasExpense || src === "expense") return "out";
  return "je";
}

// Daybook — a single-place, plain-language transaction timeline.
// Reuses GET /journal-entries (server-side date range); search + party
// resolution + money-in/out totals are computed on the client.
export const Daybook = ({ accounts = [], clients = [], vendors = [], projects = [], employees = [] }) => {
  const navigate = useNavigate();
  const [preset, setPreset] = useState("month");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);

  const nameMaps = useMemo(() => {
    const m = (arr, key = "name") => Object.fromEntries((arr || []).map((x) => [x.id, x[key]]));
    return {
      client: m(clients),
      vendor: m(vendors),
      project: m(projects),
      employee: m(employees),
    };
  }, [clients, vendors, projects, employees]);

  useEffect(() => {
    const r = computeRange(preset);
    const fromDate = r ? r.from : from;
    const toDate = r ? r.to : to;
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const qs = params.toString() ? `?${params.toString()}` : "";
    setLoading(true);
    api
      .get(`/journal-entries${qs}`)
      .then(({ data }) => setEntries(Array.isArray(data) ? data : []))
      .finally(() => setLoading(false));
  }, [preset, from, to]);

  const enriched = useMemo(() => {
    return entries.map((e) => {
      const dir = classify(e);
      const lines = e.lines || [];
      const incomeAcc = lines.filter((l) => l.account_type === "income").map((l) => l.account_name);
      const expenseAcc = lines.filter((l) => l.account_type === "expense").map((l) => l.account_name);
      let accountsLabel =
        dir === "in" ? incomeAcc.join(", ") : dir === "out" ? expenseAcc.join(", ") : "";
      if (!accountsLabel) accountsLabel = [...new Set(lines.map((l) => l.account_name))].join(", ");
      const party = [
        nameMaps.client[e.client_id],
        nameMaps.vendor[e.vendor_id],
        nameMaps.project[e.project_id],
        nameMaps.employee[e.employee_id],
      ]
        .filter(Boolean)
        .join(" · ");
      return { ...e, _dir: dir, _accounts: accountsLabel, _party: party };
    });
  }, [entries, nameMaps]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    const num = term.replace(/[₹,\s]/g, "");
    return enriched.filter((e) => {
      if (typeFilter !== "all" && e._dir !== typeFilter) return false;
      if (!term) return true;
      const hay = `${e.narration || ""} ${e.reference || ""} ${e.source || ""} ${e._party} ${e._accounts}`.toLowerCase();
      const amountMatch = num && String(e.total).includes(num);
      return hay.includes(term) || amountMatch;
    });
  }, [enriched, q, typeFilter]);

  const totals = useMemo(() => {
    let inc = 0, out = 0;
    for (const e of filtered) {
      if (e._dir === "in") inc += Number(e.total) || 0;
      else if (e._dir === "out") out += Number(e.total) || 0;
    }
    return { inc, out, count: filtered.length };
  }, [filtered]);

  const openSource = (e) => {
    if (e.project_id) return navigate(`/projects/${e.project_id}`);
    if (["invoice_payment", "invoice"].includes(e.source)) return navigate("/invoices");
    if (e.client_id) return navigate(`/clients/${e.client_id}`);
  };

  return (
    <div className="space-y-4" data-testid="daybook-tab">
      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="card-flat" data-testid="daybook-summary-count">
          <div className="overline">{periodLabel(preset, from, to)}</div>
          <div className="font-display font-bold text-3xl">{loading ? "…" : totals.count}</div>
          <div className="text-xs text-[#5C5C5C]">transactions</div>
        </div>
        <div className="card-flat" data-testid="daybook-summary-in">
          <div className="overline text-[#1D633E]">MONEY IN</div>
          <div className="font-display font-bold text-3xl text-[#1D633E]">{CURRENCY(totals.inc)}</div>
        </div>
        <div className="card-flat" data-testid="daybook-summary-out">
          <div className="overline text-[#B4001C]">MONEY OUT</div>
          <div className="font-display font-bold text-3xl text-[#B4001C]">{CURRENCY(totals.out)}</div>
        </div>
      </div>

      {/* Controls */}
      <div className="card-flat space-y-3">
        <div className="flex flex-wrap gap-1.5" data-testid="daybook-presets">
          {PERIOD_PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPreset(p.id)}
              data-testid={`daybook-preset-${p.id}`}
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
        {preset === "custom" && (
          <div className="flex items-center gap-2 text-xs">
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="input-flat" data-testid="daybook-from" />
            <span className="text-[#9A9A9A]">→</span>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="input-flat" data-testid="daybook-to" />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9A9A9A]" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder='Try "Rent", "Tea", a name, a project, or 30000…'
              className="input-flat w-full pl-9"
              data-testid="daybook-search"
            />
          </div>
          <div className="flex gap-1" data-testid="daybook-type-filter">
            {[
              { id: "all", label: "All" },
              { id: "in", label: "Money In" },
              { id: "out", label: "Money Out" },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTypeFilter(t.id)}
                data-testid={`daybook-type-${t.id}`}
                className={`px-3 py-1 text-xs border transition-colors ${
                  typeFilter === t.id
                    ? "bg-[#8B7F6A] text-white border-[#8B7F6A]"
                    : "bg-white text-[#5C5C5C] border-[#E5E5E5] hover:border-[#8B7F6A]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Timeline table */}
      <div className="border border-[#E5E5E5] overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr>
              <th className="p-3 text-left">Date</th>
              <th className="p-3 text-left">Type</th>
              <th className="p-3 text-left">Description</th>
              <th className="p-3 text-left">Account</th>
              <th className="p-3 text-left">Party / Project</th>
              <th className="p-3 text-right">Amount</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody data-testid="daybook-rows">
            {filtered.map((e) => (
              <tr
                key={e.id}
                onClick={() => setDetail(e)}
                className="border-t border-[#F0F0F0] hover:bg-[#FAFAF7] cursor-pointer"
                data-testid={`daybook-row-${e.id}`}
              >
                <td className="p-3 font-mono text-xs whitespace-nowrap">{e.date}</td>
                <td className="p-3"><DirBadge dir={e._dir} /></td>
                <td className="p-3 max-w-[280px]">
                  <div className="truncate">{e.narration || "—"}</div>
                  {e.reference && <div className="text-[10px] text-[#9A9A9A] font-mono">Ref: {e.reference}</div>}
                </td>
                <td className="p-3 text-xs text-[#5C5C5C] max-w-[180px] truncate">{e._accounts || "—"}</td>
                <td className="p-3 text-xs text-[#5C5C5C] max-w-[180px] truncate">{e._party || "—"}</td>
                <td className={`p-3 text-right font-mono font-semibold ${e._dir === "in" ? "text-[#1D633E]" : e._dir === "out" ? "text-[#B4001C]" : ""}`}>
                  {CURRENCY(e.total)}
                </td>
                <td className="p-3 text-[#C5C5C5]"><CaretRight size={14} /></td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="p-10 text-center text-[#9A9A9A]">
                  {entries.length === 0 ? "No transactions in this period." : "No matches — try a different search or period."}
                </td>
              </tr>
            )}
            {loading && <tr><td colSpan={7} className="p-10 text-center overline">LOADING…</td></tr>}
          </tbody>
        </table>
      </div>

      {detail && (
        <TransactionDetail entry={detail} onClose={() => setDetail(null)} onOpenSource={openSource} />
      )}
    </div>
  );
};

const DirBadge = ({ dir }) => {
  if (dir === "in")
    return <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#1D633E]"><ArrowDown size={12} /> IN</span>;
  if (dir === "out")
    return <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#B4001C]"><ArrowUp size={12} /> OUT</span>;
  return <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#8B7F6A]"><ArrowsLeftRight size={12} /> JE</span>;
};

// "Simple outside, professional underneath" — the full double-entry detail.
const TransactionDetail = ({ entry, onClose, onOpenSource }) => {
  const lines = entry.lines || [];
  const totalDr = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalCr = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const canOpen = entry.project_id || entry.client_id || ["invoice_payment", "invoice"].includes(entry.source);
  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" data-testid="txn-detail-modal" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[201] w-full max-w-xl bg-white shadow-2xl max-h-[90vh] overflow-auto">
        <div className="flex items-start justify-between p-5 border-b border-[#E5E5E5]">
          <div>
            <div className="overline text-[#8B7F6A]">TRANSACTION DETAIL</div>
            <div className="font-display font-bold text-xl" data-testid="txn-detail-narration">{entry.narration || "Journal entry"}</div>
            <div className="text-xs text-[#5C5C5C] mt-0.5 font-mono">
              {entry.date}{entry.reference ? ` · Ref ${entry.reference}` : ""}{entry.created_by_name ? ` · by ${entry.created_by_name}` : ""}
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost" data-testid="txn-detail-close"><X size={16} /></button>
        </div>

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
          {entry.reversed && (
            <div className="mt-3 text-xs text-[#B4001C]">This entry has been reversed.</div>
          )}
        </div>

        {canOpen && (
          <div className="p-4 border-t border-[#E5E5E5] flex justify-end">
            <button onClick={() => onOpenSource(entry)} className="btn-ghost text-sm" data-testid="txn-open-source">
              <ArrowSquareOut size={14} /> Open related record
            </button>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};
