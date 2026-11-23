import { useEffect, useMemo, useState } from "react";
import { ArrowClockwise, Broom, CheckCircle, DownloadSimple, MagnifyingGlass, ShieldCheck, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "../lib/api";
import { dateForInput, formatDate, formatDateTime } from "../lib/format";
import PageHero from "../components/PageHero";

const humanize = (value) => (value || "Activity").replace(/[._-]+/g, " ")
  .replace(/\b\w/g, (letter) => letter.toUpperCase());

export default function AuditLog() {
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [exporting, setExporting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/audit-log", { params: { limit: 500 } });
      setRows(Array.isArray(data) ? data : []);
    } catch {
      toast.error("Could not load the audit log");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const verify = async () => {
    setVerifying(true);
    try {
      const { data } = await api.get("/audit-log/verify");
      setVerification(data);
      if (data.ok) toast.success("Audit chain verified");
      else toast.error("Audit chain needs review");
    } catch {
      toast.error("Could not verify the audit chain");
    } finally { setVerifying(false); }
  };

  const [cleanup, setCleanup] = useState(null);   // { months, preview }
  const openCleanup = async (months) => {
    try {
      const { data } = await api.get("/audit-log/cleanup-preview", { params: { months } });
      setCleanup({ months, preview: data });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not check what can be cleared");
    }
  };
  const runCleanup = async () => {
    try {
      const { data } = await api.post("/audit-log/cleanup", { months: cleanup.months, confirm: true });
      toast.success(`Cleared ${data.deleted} routine entries`);
      setCleanup(null); setVerification(null); load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not clear the entries");
    }
  };

  const download = async () => {
    setExporting(true);
    try {
      const { data } = await api.get("/audit-log/export", { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `audit-log-${dateForInput(new Date())}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success("Audit evidence exported");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not export the audit log");
    } finally { setExporting(false); }
  };

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => [row.action, row.actor_email, row.actor_role,
      row.target, row.target_type].some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [query, rows]);

  return (
    <div className="max-w-7xl mx-auto" data-testid="audit-log-page">
      <div className="mb-6"><PageHero title="Audit log" count={rows.length}
        kicker="Every create, change and delete in your studio, tamper-checked.">
        <div className="flex items-center gap-2">
          <button className="btn-secondary" onClick={load} disabled={loading} data-testid="audit-refresh">
            <ArrowClockwise size={15} /> Refresh
          </button>
          <button className="btn-secondary" onClick={download} disabled={exporting} data-testid="audit-export">
            <DownloadSimple size={15} /> {exporting ? "Exporting…" : "Export CSV"}
          </button>
          <button className="btn-secondary" onClick={() => openCleanup(3)} data-testid="audit-cleanup">
            <Broom size={15} /> Clean up
          </button>
          <button className="btn-primary" onClick={verify} disabled={verifying} data-testid="audit-verify">
            <ShieldCheck size={15} /> Verify integrity
          </button>
        </div>
      </PageHero></div>

      {cleanup && (
        <div className="mb-4 card-flat p-4 space-y-3" data-testid="audit-cleanup-panel">
          <div className="text-sm font-semibold">Clear routine entries</div>
          <p className="text-xs text-[var(--ink-2)]">
            Removes only sign-ins, PIN unlocks, check-ins/outs and calendar syncs older than the period you choose.
            Money, payroll, permission, deletion and export records are always kept: the law requires the audit
            trail of your books to be preserved for 8 years. Download the CSV first if you want a copy.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs">Older than</span>
            {[1, 3, 6, 12].map((m) => (
              <button key={m} className={m === cleanup.months ? "btn-primary text-xs" : "btn-ghost text-xs"}
                onClick={() => openCleanup(m)} data-testid={`audit-cleanup-${m}`}>{m === 12 ? "1 year" : `${m} month${m > 1 ? "s" : ""}`}</button>
            ))}
          </div>
          <div className="text-sm" data-testid="audit-cleanup-preview">
            {cleanup.preview.removable} routine entries before {formatDate(cleanup.preview.before)} can be cleared;
            {" "}{cleanup.preview.kept} entries stay.
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-ghost" onClick={() => setCleanup(null)}>Cancel</button>
            <button className="btn-primary bg-[var(--danger)]" disabled={!cleanup.preview.removable}
              onClick={runCleanup} data-testid="audit-cleanup-confirm">Clear {cleanup.preview.removable} entries</button>
          </div>
        </div>
      )}

      {verification && (
        <div className={`mb-4 px-4 py-3 border flex items-center gap-3 ${verification.ok
          ? "border-[#B8D8C0] bg-[#F1F8F2] text-[var(--success)]"
          : "border-[#E8B9B5] bg-[var(--danger-soft)] text-[var(--danger)]"}`} data-testid="audit-verification-result">
          {verification.ok ? <CheckCircle size={18} weight="fill" /> : <Warning size={18} weight="fill" />}
          <div className="text-sm font-semibold">
            {verification.ok ? `Verified ${verification.rows_checked} chained activities.`
              : `${verification.problems?.length || 0} integrity issue(s) require review.`}
          </div>
        </div>
      )}

      <div className="relative mb-4 max-w-lg">
        <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
        <input className="input-field !pl-9 w-full" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search action, actor or record" data-testid="audit-search" />
      </div>

      <div className="border border-[var(--line)] bg-white overflow-x-auto rounded-md">
        <table className="w-full min-w-[780px] text-left">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
            <tr className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-2)]">
              <th className="px-4 py-3">Time</th><th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Actor</th><th className="px-4 py-3">Record</th>
              <th className="px-4 py-3">Sequence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EEEEEB]">
            {loading && <tr><td colSpan="5" className="px-4 py-10 text-center text-sm text-[var(--ink-2)]">Loading activities...</td></tr>}
            {!loading && filtered.length === 0 && <tr><td colSpan="5" className="px-4 py-10 text-center text-sm text-[var(--ink-2)]">No matching activities.</td></tr>}
            {!loading && filtered.map((row) => (
              <tr key={row.id} className="hover:bg-[var(--surface-2)]" data-testid={`audit-row-${row.id}`}>
                <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">{formatDateTime(row.at)}</td>
                <td className="px-4 py-3 text-sm font-semibold">{humanize(row.action)}</td>
                <td className="px-4 py-3"><div className="text-sm">{row.actor_email || "System"}</div><div className="text-[10px] font-mono uppercase text-[var(--ink-3)]">{row.actor_role || "service"}</div></td>
                <td className="px-4 py-3"><div className="text-sm">{row.target || "-"}</div><div className="text-[10px] font-mono uppercase text-[var(--ink-3)]">{row.target_type || "record"}</div></td>
                <td className="px-4 py-3 font-mono text-xs">{row.seq ?? "legacy"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
