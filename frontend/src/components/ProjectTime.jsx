import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";

const inr = (n) => `Rs. ${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const hrs = (n) => `${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })} h`;

function Bar({ value, max }) {
  const pct = max ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden w-full">
      <div className="h-full rounded-full bg-[var(--accent-strong)]" style={{ width: `${pct}%` }} />
    </div>
  );
}

function Profitability({ projectId }) {
  const [p, setP] = useState(null);
  useEffect(() => {
    api.get(`/projects/${projectId}/profitability`).then(({ data }) => setP(data)).catch(() => setP(false));
  }, [projectId]);
  if (p === false) return null;
  if (!p) return <div className="skeleton h-28 w-full" />;
  const margin = p.margin_on_invoiced;
  return (
    <div className="card-flat space-y-4" data-testid="project-profitability">
      <div className="overline">PROFITABILITY · SO FAR</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[["Fee", p.fee ? inr(p.fee) : "Not set"], ["Invoiced", inr(p.invoiced)], ["Costs so far", inr(p.costs.total)],
          ["Margin on invoiced", `${inr(margin)}${p.margin_on_invoiced_pct != null ? ` · ${p.margin_on_invoiced_pct}%` : ""}`]]
          .map(([label, value]) => (
            <div key={label} className="border border-[var(--line)] rounded-md p-3">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">{label}</div>
              <div className={`font-mono text-base mt-0.5 ${label.startsWith("Margin") && margin < 0 ? "text-[var(--danger)]" : ""}`}>{value}</div>
            </div>
          ))}
      </div>
      <dl className="grid grid-cols-[1fr,auto] gap-x-6 gap-y-1 text-sm max-w-md">
        <dt className="text-[var(--ink-2)]">Vendor bills</dt><dd className="font-mono text-right">{inr(p.costs.vendor_bills)}</dd>
        <dt className="text-[var(--ink-2)]">Project expenses</dt><dd className="font-mono text-right">{inr(p.costs.expenses)}</dd>
        <dt className="text-[var(--ink-2)]">Team time ({hrs(p.approved_hours)} approved)</dt><dd className="font-mono text-right">{inr(p.costs.labour)}</dd>
      </dl>
      {p.fee_used_pct != null && (
        <div className="max-w-md">
          <div className="flex justify-between text-xs text-[var(--ink-2)] mb-1"><span>Fee used by costs</span><span className="font-mono">{p.fee_used_pct}%</span></div>
          <Bar value={p.fee_used_pct} max={100} />
        </div>
      )}
      {p.unpriced_hours > 0 && (
        <p className="text-xs text-[var(--warning)]">
          {hrs(p.unpriced_hours)} were approved for people without a salary or cost rate, so they add no cost.
          Set rates under <Link className="underline" to="/timesheets?tab=rates">Timesheets → Cost rates</Link>.
        </p>
      )}
      <p className="text-[11px] text-[var(--ink-3)]">
        Costs count approved vendor bills, approved project expense claims and approved timesheet hours at each person&apos;s
        hourly cost when approved.
      </p>
    </div>
  );
}

/** Hours on this project by phase and person; profitability for finance roles. */
export default function ProjectTime({ projectId, canSeeFinancials }) {
  const [t, setT] = useState(null);
  useEffect(() => {
    api.get(`/projects/${projectId}/time`).then(({ data }) => setT(data)).catch(() => setT(false));
  }, [projectId]);
  if (t === false) return <div className="text-sm text-[var(--danger)]">Could not load time for this project.</div>;
  if (!t) return <div className="skeleton h-40 w-full" />;
  const maxPhase = Math.max(0, ...t.by_phase.map((r) => r.hours));
  const maxPerson = Math.max(0, ...t.by_person.map((r) => r.hours));
  return (
    <div className="space-y-6" data-testid="project-time">
      {canSeeFinancials && <Profitability projectId={projectId} />}
      <div className="card-flat">
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
          <div className="overline">TIME LOGGED</div>
          <div className="text-xs text-[var(--ink-2)]">
            {hrs(t.totals.hours)} submitted · {hrs(t.totals.billable_hours)} billable · {hrs(t.totals.approved_hours)} approved
            {t.can_see_costs && <> · cost {inr(t.totals.cost)}</>}
          </div>
        </div>
        {t.totals.hours === 0 ? (
          <div className="text-sm text-[var(--ink-3)]">
            No submitted hours yet. The team logs time in <Link className="underline" to="/timesheets">Timesheets</Link>.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {[["BY PHASE", t.by_phase, "phase", maxPhase], ["BY PERSON", t.by_person, "name", maxPerson]].map(([title, rows, key, max]) => (
              <div key={title}>
                <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)] mb-2">{title}</div>
                <div className="space-y-2.5">
                  {rows.map((r) => (
                    <div key={r[key]}>
                      <div className="flex justify-between text-sm mb-1">
                        <span>{r[key]}</span>
                        <span className="font-mono text-xs text-[var(--ink-2)]">
                          {hrs(r.hours)}{r.billable_hours !== r.hours ? ` (${hrs(r.billable_hours)} billable)` : ""}
                          {t.can_see_costs && r.cost ? ` · ${inr(r.cost)}` : ""}
                        </span>
                      </div>
                      <Bar value={r.hours} max={max} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
