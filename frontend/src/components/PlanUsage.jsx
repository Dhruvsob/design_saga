import { Fragment, useEffect, useState } from "react";
import api, { API } from "../lib/api";
import { formatDate } from "../lib/format";

function fmtBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024 * 1024) return `${Math.round(v / 1024)} KB`;
  if (v < 1024 ** 3) return `${(v / 1024 ** 2).toFixed(1)} MB`;
  return `${(v / 1024 ** 3).toFixed(2)} GB`;
}

function Meter({ label, used, limit, show = (v) => v, testid }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const tone = pct >= 100 ? "var(--danger)" : pct >= 80 ? "var(--warning)" : "var(--accent-strong)";
  return (
    <div className="border border-[var(--line)] rounded-md p-4" data-testid={testid}>
      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">{label}</div>
      <div className="font-mono text-lg mt-1">
        {show(used)}
        <span className="text-xs text-[var(--ink-3)]">{limit != null ? ` / ${show(limit)}` : " · no limit"}</span>
      </div>
      {limit != null && limit > 0 && (
        <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden mt-2"
             role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: tone }} />
        </div>
      )}
      {limit != null && pct >= 100 && (
        <div className="text-[11px] text-[var(--danger)] mt-2">Limit reached: contact the platform team to raise it.</div>
      )}
    </div>
  );
}

const inr = (n) => `Rs. ${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const INVOICE_STATUS = { issued: "Due", overdue: "Overdue", partially_paid: "Part paid", paid: "Paid", void: "Void" };

function subscriptionLine(s) {
  if (!s?.status) return "No subscription dates are set for this workspace.";
  if (s.status === "trial") return s.trial_ends_on ? `Trial until ${formatDate(s.trial_ends_on)}.` : "Trial.";
  if (s.status === "grace") return `Payment overdue: everything works until ${formatDate(s.grace_ends_on)}, then editing pauses.`;
  if (s.read_only) return "Editing is paused until the renewal is paid. Your work is safe and can be viewed or downloaded.";
  if (s.paid_through) return `Paid up to ${formatDate(s.paid_through)}.`;
  return "Active.";
}

/** The studio's subscription, its invoices from Gamaa and how to pay. */
function Billing() {
  const [b, setB] = useState(null);
  useEffect(() => { api.get("/org/current/billing").then(({ data }) => setB(data)).catch(() => setB(false)); }, []);
  if (b === false) return null;
  if (!b) return <div className="skeleton h-24 w-full" />;
  const due = b.invoices.filter((i) => ["issued", "overdue", "partially_paid"].includes(i.status));
  const p = b.pay_to || {};
  const payRows = [["Account name", p.account_name || p.name], ["Bank", p.bank], ["Account no.", p.account],
    ["IFSC", p.ifsc], ["UPI", p.upi]].filter(([, v]) => v);
  return (
    <div className="card-flat space-y-4" data-testid="studio-billing">
      <div>
        <div className="overline mb-1">SUBSCRIPTION</div>
        <div className={`text-sm ${b.subscription?.read_only ? "text-[var(--danger)]" : b.subscription?.status === "grace" ? "text-[var(--warning)]" : ""}`}>
          {subscriptionLine(b.subscription)}
        </div>
      </div>
      {due.length > 0 && payRows.length > 0 && (
        <div className="border border-[var(--line)] rounded-md p-3">
          <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)] mb-2">How to pay {b.seller?.name}</div>
          <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
            {payRows.map(([k, v]) => (
              <Fragment key={k}><dt className="text-[var(--ink-3)]">{k}</dt><dd className="font-mono break-all">{v}</dd></Fragment>
            ))}
          </dl>
          <p className="text-[11px] text-[var(--ink-3)] mt-2">Quote the invoice number with your payment.</p>
        </div>
      )}
      <div>
        <div className="overline mb-2">INVOICES FROM {String(b.seller?.name || "GAMAA").toUpperCase()}</div>
        {b.invoices.length === 0 ? (
          <div className="text-sm text-[var(--ink-3)]">No invoices yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="text-left text-[10px] font-mono uppercase text-[var(--ink-3)] border-b border-[var(--line)]">
                  <th className="py-2 pr-3">Invoice</th><th className="py-2 pr-3">Period</th>
                  <th className="py-2 pr-3 text-right">Total</th><th className="py-2 pr-3">Status</th><th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {b.invoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-[var(--line-soft)]">
                    <td className="py-2 pr-3 font-mono text-xs">{inv.number}<div className="text-[10px] text-[var(--ink-3)] font-sans">due {formatDate(inv.due_on)}</div></td>
                    <td className="py-2 pr-3 text-xs">{formatDate(inv.period_start)} – {formatDate(inv.period_end)}</td>
                    <td className="py-2 pr-3 text-right font-mono">{inr(inv.total)}</td>
                    <td className={`py-2 pr-3 text-xs ${inv.status === "overdue" ? "text-[var(--danger)]" : ""}`}>
                      {INVOICE_STATUS[inv.status] || inv.status}{inv.status === "partially_paid" ? ` · ${inr(inv.balance)} left` : ""}
                    </td>
                    <td className="py-2 text-right">
                      <a className="btn-ghost text-xs inline-flex" target="_blank" rel="noreferrer"
                         href={`${API}/org/current/billing/invoices/${inv.id}/pdf`}>PDF</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/** The studio's own plan and how much of it is in use (Company Settings). */
export default function PlanUsage() {
  const [u, setU] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get("/org/current/usage").then(({ data }) => setU(data))
      .catch(() => setErr("Could not load your plan."));
  }, []);
  if (err) return <div className="text-sm text-[var(--danger)]">{err}</div>;
  if (!u) return <div className="skeleton h-40 w-full" />;
  const ai = u.ai.allowance === 0 ? "Not included" : null;
  return (
    <div className="space-y-6" data-testid="plan-usage">
      <div className="card-flat">
        <div className="overline mb-1">YOUR PLAN</div>
        <div className="font-display font-bold text-2xl tracking-tight">{u.plan_name}</div>
        <div className="text-sm text-[var(--ink-2)] mt-1">Support: {u.support || "—"}</div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Meter label="Active users" used={u.users.used} limit={u.users.limit} testid="usage-users" />
        <Meter label="Projects" used={u.projects.used} limit={u.projects.limit} testid="usage-projects" />
        <Meter label="File storage" used={u.storage.bytes} limit={u.storage.quota_bytes} show={fmtBytes} testid="usage-storage" />
        {ai ? (
          <div className="border border-[var(--line)] rounded-md p-4">
            <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">AI requests this month</div>
            <div className="font-mono text-lg mt-1">{ai}</div>
          </div>
        ) : (
          <Meter label="AI requests this month" used={u.ai.calls} limit={u.ai.allowance} testid="usage-ai" />
        )}
      </div>
      <p className="text-xs text-[var(--ink-3)]">
        Need more room or a module that isn&apos;t switched on? Ask the platform team; your data is never removed when a
        limit is reached, only new additions pause.
      </p>
      <Billing />
    </div>
  );
}
