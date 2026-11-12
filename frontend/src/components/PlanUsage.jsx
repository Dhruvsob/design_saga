import { useEffect, useState } from "react";
import api from "../lib/api";

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
    </div>
  );
}
