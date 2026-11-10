import { useEffect, useMemo, useState } from "react";
import { ArrowClockwise, CheckCircle, DownloadSimple, MagnifyingGlass, ShieldCheck, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "../lib/api";
import { dateForInput, formatDateTime } from "../lib/format";
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
          <button className="btn-primary" onClick={verify} disabled={verifying} data-testid="audit-verify">
            <ShieldCheck size={15} /> Verify integrity
          </button>
        </div>
      </PageHero></div>

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
