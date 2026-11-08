import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CheckCircle, WarningCircle, XCircle, FileXls, LockSimple, LockSimpleOpen } from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate, formatINR } from "../lib/format";
import { askForm, confirmAction } from "../lib/confirm";

// Quarters of an Indian financial year (April-March).
const PERIODS = [
  ["year", "Full year"], ["q1", "Q1 · Apr–Jun"], ["q2", "Q2 · Jul–Sep"], ["q3", "Q3 · Oct–Dec"], ["q4", "Q4 · Jan–Mar"],
];

function rangeFor(fy, period) {
  const start = Number(String(fy).split("-")[0]);
  if (!start) return null;
  const pad = (n) => String(n).padStart(2, "0");
  const last = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();   // m is 1-12
  const q = { q1: [start, 4, 6], q2: [start, 7, 9], q3: [start, 10, 12], q4: [start + 1, 1, 3] }[period];
  if (!q) return { from: `${start}-04-01`, to: `${start + 1}-03-31` };
  const [y, m1, m2] = q;
  return { from: `${y}-${pad(m1)}-01`, to: `${y}-${pad(m2)}-${pad(last(y, m2))}` };
}

const dayAfter = (iso) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
};

/**
 * Close & export: check the period, download its books as Excel, then lock it.
 * Nothing is deleted - closed periods stay visible in every report.
 */
export default function PeriodClose({ fyChoices = [], currentFy, isAdmin }) {
  const [status, setStatus] = useState(null);
  const [fy, setFy] = useState("");
  const [period, setPeriod] = useState("year");
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState("");
  const [exported, setExported] = useState(null);   // {id, sha256, from, to}
  const [accept, setAccept] = useState(false);

  const load = () => api.get("/accounting/periods").then(({ data }) => setStatus(data))
    .catch((e) => toast.error(e?.response?.data?.detail || "Could not load closing status"));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (fy || !fyChoices.length) return;
    // Default to the last finished year.
    const idx = fyChoices.indexOf(currentFy);
    setFy(fyChoices[idx + 1] || fyChoices[idx] || fyChoices[0]);
  }, [fyChoices, currentFy, fy]);

  const range = useMemo(() => rangeFor(fy, period), [fy, period]);
  const lock = status?.locked_through || null;
  // The export for a close starts the day after the last closing, so no day is skipped.
  const exportFrom = range && lock && lock >= range.from && lock < range.to ? dayAfter(lock) : range?.from;
  useEffect(() => { setCheck(null); setExported(null); setAccept(false); }, [fy, period]);

  const qs = () => new URLSearchParams({ from_date: exportFrom, to_date: range.to }).toString();
  const runCheck = async () => {
    setBusy("check");
    try { const { data } = await api.get(`/accounting/periods/check?${qs()}`); setCheck(data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Check failed"); }
    finally { setBusy(""); }
  };
  const runExport = async () => {
    setBusy("export");
    try {
      const res = await api.post(`/accounting/periods/export?${qs()}`, null, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `books-${exportFrom}-to-${range.to}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      setExported({ id: res.headers["x-export-id"], sha256: res.headers["x-export-sha256"], from: exportFrom, to: range.to });
      toast.success("Excel downloaded. Keep it with your records.");
    } catch (e) {
      let msg = "Export failed";
      try { msg = JSON.parse(await e.response.data.text()).detail || msg; } catch { /* not JSON */ }
      toast.error(msg);
    } finally { setBusy(""); }
  };
  const close = async () => {
    if (!await confirmAction(`Close the books up to ${formatDate(range.to)}? Nothing dated on or before that day can then be added, deleted or corrected in place. Corrections are made with today's date. An administrator can reopen with a reason.`)) return;
    setBusy("close");
    try {
      await api.post("/accounting/periods/close", { through_date: range.to, export_id: exported.id, acknowledge_warnings: accept });
      toast.success(`Books closed up to ${formatDate(range.to)}`);
      setCheck(null); setExported(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not close"); }
    finally { setBusy(""); }
  };
  const reopen = async () => {
    const v = await askForm({
      title: "Reopen closed books",
      body: `Books are closed up to ${formatDate(lock)}. Reopening lets entries on those days change again. Every reopen is recorded with your reason.`,
      fields: [
        { name: "locked_through", label: "Keep closed up to (leave empty to open everything)", type: "date" },
        { name: "reason", label: "Reason (required)", required: true },
      ],
      confirmLabel: "Reopen", danger: true,
    });
    if (!v) return;
    try {
      await api.post("/accounting/periods/reopen", { locked_through: v.locked_through || null, reason: v.reason });
      toast.success("Books reopened"); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not reopen"); }
  };

  const alreadyClosed = Boolean(range && lock && range.to <= lock);
  const canClose = isAdmin && check?.ok && exported && exported.to === range?.to && (!check.warnings.length || accept);

  return (
    <div className="space-y-5" data-testid="period-close">
      <div className="flex flex-wrap items-center gap-3 border border-[var(--line)] bg-[var(--surface-2)] px-4 py-3" data-testid="period-lock-status">
        {lock ? <LockSimple size={20} className="text-[var(--accent-strong)]" /> : <LockSimpleOpen size={20} className="text-[var(--ink-3)]" />}
        <div className="flex-1 min-w-[220px]">
          <div className="font-semibold">{lock ? `Books closed up to ${formatDate(lock)}` : "No period is closed yet"}</div>
          <div className="text-xs text-[var(--ink-2)]">Closed periods stay visible in every report and ledger. They just can't change.</div>
        </div>
        {lock && isAdmin && <button type="button" className="btn-ghost text-xs" onClick={reopen} data-testid="period-reopen">Reopen…</button>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3 items-end">
        <label className="text-xs text-[var(--ink-2)]">Financial year
          <select className="input-flat w-full mt-1" value={fy} onChange={(e) => setFy(e.target.value)} data-testid="period-fy">
            {fyChoices.map((c) => <option key={c} value={c}>FY {c}</option>)}
          </select>
        </label>
        <label className="text-xs text-[var(--ink-2)]">Period
          <select className="input-flat w-full mt-1" value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="period-part">
            {PERIODS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <div className="text-xs text-[var(--ink-2)] pb-2">{range && `${formatDate(exportFrom)} – ${formatDate(range.to)}`}</div>
      </div>

      <ol className="space-y-4">
        <li className="border border-[var(--line)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="overline">1 · Check</span>
            <span className="text-sm text-[var(--ink-2)] flex-1">Entries balance, every entry has its source record, Cash/Bank matches the payment method.</span>
            <button type="button" className="btn-ghost text-xs" onClick={runCheck} disabled={!range || busy} data-testid="period-check">
              {busy === "check" ? "Checking…" : "Run check"}
            </button>
          </div>
          {check && (
            <div className="mt-3 space-y-2 text-sm" data-testid="period-check-result">
              <div className="flex items-center gap-2">
                {check.ok ? <CheckCircle size={18} className="text-[var(--success)]" /> : <XCircle size={18} className="text-[var(--danger)]" />}
                <span className="font-semibold">{check.ok ? "Ready to close" : "Fix these before closing"}</span>
                <span className="text-xs text-[var(--ink-3)] ml-auto">{check.entries} entries · debit {formatINR(check.debit_total)} · credit {formatINR(check.credit_total)}</span>
              </div>
              {check.blockers.map((b) => (
                <div key={b.code} className="flex gap-2 text-[var(--danger)]"><XCircle size={16} className="shrink-0 mt-0.5" />{b.message}</div>
              ))}
              {check.warnings.map((w) => (
                <div key={w.code} className="flex gap-2 text-[var(--ink-2)]"><WarningCircle size={16} className="shrink-0 mt-0.5 text-[var(--warning,#9A6B12)]" />{w.message}</div>
              ))}
              {!check.ok && check.blockers.some((b) => b.code === "integrity") && (
                <div className="text-xs text-[var(--ink-3)]">Details are under Overview › Health check › Data check.</div>
              )}
            </div>
          )}
        </li>

        <li className="border border-[var(--line)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="overline">2 · Export</span>
            <span className="text-sm text-[var(--ink-2)] flex-1">One Excel file: Daybook, journal lines, trial balance, P&amp;L, chart of accounts, invoices, receipts, collections, vendor bills and payments, payroll, expenses, attachments and audit log, with a checksum manifest. Exporting never deletes anything.</span>
            <button type="button" className="btn-ghost text-xs" onClick={runExport} disabled={!range || busy} data-testid="period-export">
              <FileXls size={14} /> {busy === "export" ? "Preparing…" : "Download Excel"}
            </button>
          </div>
          {exported && <div className="mt-2 text-[11px] text-[var(--ink-3)] break-all" data-testid="period-export-done">Downloaded · SHA-256 {exported.sha256}</div>}
        </li>

        <li className="border border-[var(--line)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="overline">3 · Close</span>
            <span className="text-sm text-[var(--ink-2)] flex-1">
              {alreadyClosed ? "This period is already closed." : isAdmin
                ? "Lock the books up to the period end. Earlier days are locked too."
                : "Only an administrator can close the books."}
            </span>
            {isAdmin && !alreadyClosed && (
              <button type="button" className="btn-primary text-xs" onClick={close} disabled={!canClose || busy} data-testid="period-close-btn">
                <LockSimple size={14} /> {busy === "close" ? "Closing…" : `Close up to ${range ? formatDate(range.to) : ""}`}
              </button>
            )}
          </div>
          {check?.warnings?.length > 0 && isAdmin && !alreadyClosed && (
            <label className="mt-3 flex items-center gap-2 text-xs">
              <input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} data-testid="period-accept" />
              I have read the warnings above.
            </label>
          )}
          {isAdmin && !alreadyClosed && !canClose && (
            <div className="mt-2 text-[11px] text-[var(--ink-3)]">Run the check and download the Excel for this period first.</div>
          )}
        </li>
      </ol>

      {status?.history?.length > 0 && (
        <div className="border border-[var(--line)] overflow-x-auto">
          <table className="w-full text-sm min-w-[620px]" data-testid="period-history">
            <thead className="bg-[var(--surface-2)]"><tr className="overline text-left">
              <th className="p-2">When</th><th className="p-2">Action</th><th className="p-2">Closed up to</th><th className="p-2">By</th><th className="p-2">Reason / export</th>
            </tr></thead>
            <tbody>{status.history.map((h) => (
              <tr key={h.id} className="border-t border-[var(--line-soft)]">
                <td className="p-2 text-xs whitespace-nowrap">{formatDate(h.at)}</td>
                <td className="p-2">{h.action === "close" ? "Closed" : "Reopened"}</td>
                <td className="p-2">{h.locked_through ? formatDate(h.locked_through) : "Nothing closed"}</td>
                <td className="p-2 text-xs">{h.by_name}</td>
                <td className="p-2 text-xs text-[var(--ink-2)] break-all">{h.reason || (h.export_sha256 ? `Export ${h.export_sha256.slice(0, 12)}…` : "")}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
