import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { HandCoins, ArrowSquareOut, Notebook } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { formatDate } from "../lib/format";
import PageHero from "../components/PageHero";
import { SkeletonRows, EmptyRow } from "../components/TableState";
import { usePaged } from "../components/Pager";
import { MoneyInTabs, inr } from "../components/MoneyIn";
import RowActions from "../components/RowActions";
import { TransactionDetail } from "../components/TransactionDetail";

/** Money that actually arrived (posted once by Record Payment / Money In). Read-only. */
export default function ReceivedPayments() {
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [range, setRange] = useState({ from: "", to: "" });
  const [detail, setDetail] = useState(null);
  const navigate = useNavigate();

  const load = () => {
    const params = {};
    if (range.from) params.from_date = range.from;
    if (range.to) params.to_date = range.to;
    api.get("/accounting/received-payments", { params }).then(({ data: d }) => setData(d))
      .catch((e) => { setData({ rows: [], total: 0 }); toast.error(e?.response?.data?.detail || "Could not load payments"); });
  };
  useEffect(() => { load(); }, [range]);   // eslint-disable-line react-hooks/exhaustive-deps
  const openEntry = (r) => api.get(`/journal-entries/${r.id}`).then(({ data: d }) => setDetail(d))
    .catch((e) => toast.error(e?.response?.data?.detail || "Could not open the entry"));

  const rows = useMemo(() => (data?.rows || []).filter((r) => {
    const t = query.trim().toLowerCase();
    return !t || `${r.party || ""} ${r.project_name || ""} ${r.reference || ""} ${r.narration || ""} ${r.account}`.toLowerCase().includes(t);
  }), [data, query]);
  const total = rows.reduce((s, r) => s + r.amount, 0);
  const { pageRows, pager } = usePaged(rows, { key: "received-payments" });

  const sourceLink = (r) => r.source === "invoice_payment" ? "/invoices"
    : r.source === "other_receivable_income" ? "/accounting?tab=receivables"
    : r.project_id ? `/projects/${r.project_id}` : r.vendor_id ? `/vendors/${r.vendor_id}` : null;

  return (
    <div className="space-y-5" data-testid="received-payments-page">
      <PageHero title="Received Payments" count={data ? data.rows.length : undefined}
        kicker="Every rupee that actually came in, with the Cash/Bank account it went to. To correct one, open its entry from the ⋮ menu." />
      <MoneyInTabs />
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-[var(--ink-2)]">From<input type="date" className="input-flat mt-1 block" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></label>
        <label className="text-xs text-[var(--ink-2)]">To<input type="date" className="input-flat mt-1 block" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></label>
        <input className="input-flat min-w-[240px]" placeholder="Search client, project or reference" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="ml-auto text-right">
          <div className="overline">Total received</div>
          <div className="font-display font-bold text-2xl tabular-nums">{inr(total)}</div>
        </div>
      </div>
      <div className="border border-[var(--line)] overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]">
          <thead className="bg-[var(--surface-2)] text-left">
            <tr className="overline">
              <th className="p-3">Date</th><th className="p-3">From</th><th className="p-3">For</th>
              <th className="p-3">Into</th><th className="p-3">Reference</th><th className="p-3 text-right">Amount</th><th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {data === null && <SkeletonRows cols={7} />}
            {data && rows.length === 0 && <EmptyRow cols={7} icon={HandCoins} title="No payments received in this view" hint="Payments appear here once recorded with Receive in Collections Due." />}
            {pageRows.map((r) => {
              const link = sourceLink(r);
              return (
                <tr key={r.id} className="border-t border-[var(--line-soft)]">
                  <td className="p-3 text-xs whitespace-nowrap">{formatDate(r.date)}</td>
                  <td className="p-3"><div className="font-semibold">{r.party || "—"}</div><div className="text-xs text-[var(--ink-2)]">{r.project_name || ""}</div></td>
                  <td className="p-3">{link ? <Link to={link} className="text-[var(--accent-strong)] hover:underline">{r.source_label}</Link> : r.source_label}
                    <div className="text-xs text-[var(--ink-3)] truncate max-w-[260px]">{r.narration}</div></td>
                  <td className="p-3 text-xs">{r.account}</td>
                  <td className="p-3 text-xs font-mono">{r.reference || "—"}</td>
                  <td className="p-3 text-right tabular-nums font-semibold text-[var(--success)]">{inr(r.amount)}</td>
                  <td className="p-3 text-right">
                    <RowActions label={`payment ${r.reference || r.id}`} testid={`received-actions-${r.id}`} actions={[
                      { label: "Open entry", icon: Notebook, onSelect: () => openEntry(r), testid: `received-open-${r.id}` },
                      { label: r.source_label ? `Open ${r.source_label.toLowerCase()}` : "Open source", icon: ArrowSquareOut,
                        hidden: !link, onSelect: () => navigate(link) },
                    ]} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>{pager}
      </div>
      {detail && <TransactionDetail entry={detail} onClose={() => setDetail(null)} onChanged={() => { setDetail(null); load(); }} />}
    </div>
  );
}
