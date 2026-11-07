import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { BellRinging, FilePdf, WhatsappLogo, Trash } from "@phosphor-icons/react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { formatDate } from "../lib/format";
import { confirmAction } from "../lib/confirm";
import PageHero from "../components/PageHero";
import RowActions from "../components/RowActions";
import PdfPreviewModal from "../components/PdfPreview";
import { SkeletonRows, EmptyRow } from "../components/TableState";
import { MoneyInTabs, inr, whatsappClick } from "../components/MoneyIn";

const STATE = {
  open: ["Open", "chip-sent"], overdue: ["Pay-by date passed", "chip-overdue"],
  settled: ["Paid since", "chip-paid"], cancelled: ["Cancelled", "chip-cancelled"],
};

export default function PaymentReminders() {
  const { hasPerm } = useAuth();
  const canCancel = hasPerm("finance.create") || hasPerm("invoices.update");
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState("active");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState(null);

  const load = () => api.get("/accounting/reminders").then(({ data }) => setRows(data))
    .catch((e) => { setRows([]); toast.error(e?.response?.data?.detail || "Could not load reminders"); });
  useEffect(() => { load(); }, []);

  const shown = useMemo(() => (rows || []).filter((r) => {
    if (filter === "active" && !["open", "overdue"].includes(r.state)) return false;
    if (filter === "settled" && r.state !== "settled") return false;
    const t = query.trim().toLowerCase();
    return !t || `${r.number} ${r.party_name || ""} ${r.project_name || ""} ${r.title || ""}`.toLowerCase().includes(t);
  }), [rows, filter, query]);

  const cancel = async (r) => {
    if (!await confirmAction(`Cancel reminder ${r.number}? The amount stays in Collections Due.`)) return;
    try { await api.delete(`/accounting/reminders/${r.id}`); toast.success("Reminder cancelled"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not cancel"); }
  };

  const linkFor = (r) => r.source_type === "invoice" ? "/invoices"
    : r.project_id ? `/projects/${r.project_id}` : r.vendor_id ? `/vendors/${r.vendor_id}` : "/accounting?tab=receivables";

  return (
    <div className="space-y-5" data-testid="reminders-page">
      <PageHero title="Payment Reminders" count={rows ? rows.length : undefined}
        kicker="Demand notes sent to clients. A reminder asks for payment; it is not a receipt and never touches Accounting." />
      <MoneyInTabs />
      <div className="flex flex-wrap items-center gap-2">
        {[["active", "Open"], ["settled", "Paid since"], ["all", "All"]].map(([id, label]) => (
          <button key={id} type="button" onClick={() => setFilter(id)}
            className={`px-3 py-1.5 text-xs border rounded-full ${filter === id ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--line)]"}`}>
            {label}
          </button>
        ))}
        <input className="input-flat ml-auto min-w-[240px]" placeholder="Search client, project or number"
               value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <div className="border border-[var(--line)] overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]" data-testid="reminders-table">
          <thead className="bg-[var(--surface-2)] text-left">
            <tr className="overline">
              <th className="p-3">Reminder</th><th className="p-3">Client / project</th><th className="p-3">For</th>
              <th className="p-3">Pay by</th><th className="p-3 text-right">Asked</th><th className="p-3 text-right">Still due</th>
              <th className="p-3">Status</th><th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {rows === null && <SkeletonRows cols={8} />}
            {rows && shown.length === 0 && (
              <EmptyRow cols={8} icon={BellRinging} title={rows.length ? "No reminders in this view" : "No payment reminders yet"}
                hint="Send one from an invoice's ⋮ menu or from Collections Due." />
            )}
            {shown.map((r) => {
              const [label, chip] = STATE[r.state] || [r.state, "chip-draft"];
              return (
                <tr key={r.id} className="border-t border-[var(--line-soft)]">
                  <td className="p-3 font-mono font-semibold">{r.number}<div className="text-[10px] font-normal text-[var(--ink-3)]">{formatDate(r.created_at)}</div></td>
                  <td className="p-3"><div className="font-semibold">{r.party_name || "—"}</div><div className="text-xs text-[var(--ink-2)]">{r.project_name || "No project"}</div></td>
                  <td className="p-3"><Link to={linkFor(r)} className="text-[var(--accent-strong)] hover:underline">{r.title || "Collection"}</Link></td>
                  <td className="p-3 text-xs">{formatDate(r.due_by)}</td>
                  <td className="p-3 text-right tabular-nums">{inr(r.amount_due)}</td>
                  <td className="p-3 text-right tabular-nums font-semibold">{inr(r.outstanding_now)}</td>
                  <td className="p-3"><span className={`status-chip ${chip}`}>{label}</span></td>
                  <td className="p-3 text-right whitespace-nowrap">
                    {r.state !== "cancelled" && r.state !== "settled" && (
                      <a href={r.whatsapp_url} target="_blank" rel="noreferrer" onClick={() => whatsappClick(r)}
                         className="btn-ghost text-xs mr-1" title="Open WhatsApp with the reminder message">
                        <WhatsappLogo size={14} /> WhatsApp
                      </a>
                    )}
                    <RowActions label={`reminder ${r.number}`} actions={[
                      { label: "Reminder PDF", icon: FilePdf, onSelect: () => setPreview(r) },
                      { label: "Cancel reminder", icon: Trash, danger: true, divider: true,
                        hidden: !canCancel || r.state === "cancelled", onSelect: () => cancel(r) },
                    ]} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {preview && <PdfPreviewModal path={`/accounting/reminders/${preview.id}/pdf`} title={`Payment reminder ${preview.number}`}
                                   filename={`${preview.number}.pdf`} onClose={() => setPreview(null)} />}
    </div>
  );
}
