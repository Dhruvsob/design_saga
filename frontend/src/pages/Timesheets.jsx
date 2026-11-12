import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { CaretLeft, CaretRight, Check, Plus, X, ArrowUUpLeft } from "@phosphor-icons/react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import { formatDate } from "../lib/format";
import { confirmAction } from "../lib/confirm";
import { useAuth } from "../context/AuthContext";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const STATUS = {
  empty: ["No hours", "bg-[var(--surface-2)] text-[var(--ink-3)]"],
  draft: ["Draft", "bg-[var(--surface-2)] text-[var(--ink-2)]"],
  submitted: ["Submitted", "bg-[var(--hover)] text-[#5F5A4B]"],
  approved: ["Approved", "bg-[var(--success-soft)] text-[var(--success)]"],
  rejected: ["Returned", "bg-[var(--warning-soft)] text-[var(--warning)]"],
};
const inr = (n) => `Rs. ${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

/** 6 -> "6", 2.5 -> "2.5", 1.25 -> "1.25" */
const fmtH = (n) => String(Math.round(Number(n || 0) * 100) / 100);

function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || String(x)).join(" · ");
  return fallback;
}

function shiftWeek(iso, weeks) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + weeks * 7);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Turn saved entries into grid rows: one row per project + phase + billable + note. */
function toRows(entries, days) {
  const rows = new Map();
  for (const e of entries) {
    const key = [e.project_id, e.phase_id || "", e.billable ? 1 : 0, e.note || ""].join("|");
    if (!rows.has(key)) {
      rows.set(key, { key, project_id: e.project_id, phase_id: e.phase_id || "", billable: !!e.billable,
        note: e.note || "", hours: Object.fromEntries(days.map((d) => [d, ""])), reason: e.rejection_reason });
    }
    const row = rows.get(key);
    row.hours[e.date] = String(Number(row.hours[e.date] || 0) + Number(e.hours));
  }
  return [...rows.values()];
}

function blankRow(days, projectId = "") {
  return { key: `new-${Math.random().toString(36).slice(2)}`, project_id: projectId, phase_id: "", billable: true,
    note: "", hours: Object.fromEntries(days.map((d) => [d, ""])) };
}

function WeekGrid({ data, rows, setRows, locked }) {
  const phasesFor = (pid) => data.phases.filter((p) => p.project_id === pid);
  const set = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const dayTotals = data.days.map((d) => rows.reduce((a, r) => a + (Number(r.hours[d]) || 0), 0));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-sm" data-testid="timesheet-grid">
        <thead>
          <tr className="text-left text-[10px] font-mono uppercase text-[var(--ink-3)] border-b border-[var(--line)]">
            <th className="py-2 pr-2 w-56">Project</th><th className="py-2 pr-2 w-40">Phase</th>
            <th className="py-2 pr-2 w-16 text-center">Billable</th>
            {data.days.map((d, i) => (
              <th key={d} className="py-2 px-1 text-center w-16">{DAY_NAMES[i]}<div className="font-sans normal-case text-[10px]">{d.slice(8)}/{d.slice(5, 7)}</div></th>
            ))}
            <th className="py-2 px-1 text-right w-14">Total</th><th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const total = data.days.reduce((a, d) => a + (Number(r.hours[d]) || 0), 0);
            return (
              <tr key={r.key} className="border-b border-[var(--line-soft)] align-top">
                <td className="py-1.5 pr-2">
                  <select className="input-flat w-full !py-1 !text-xs" value={r.project_id} disabled={locked}
                          aria-label={`Row ${i + 1} project`} onChange={(e) => set(i, { project_id: e.target.value, phase_id: "" })}>
                    <option value="">Choose project…</option>
                    {data.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <input className="input-flat w-full !py-1 !text-xs mt-1" placeholder="Note (optional)" maxLength={300}
                         value={r.note} disabled={locked} aria-label={`Row ${i + 1} note`} onChange={(e) => set(i, { note: e.target.value })} />
                </td>
                <td className="py-1.5 pr-2">
                  <select className="input-flat w-full !py-1 !text-xs" value={r.phase_id} disabled={locked || !r.project_id}
                          aria-label={`Row ${i + 1} phase`} onChange={(e) => set(i, { phase_id: e.target.value })}>
                    <option value="">No phase</option>
                    {phasesFor(r.project_id).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </td>
                <td className="py-1.5 pr-2 text-center">
                  <input type="checkbox" checked={r.billable} disabled={locked} aria-label={`Row ${i + 1} billable`}
                         onChange={(e) => set(i, { billable: e.target.checked })} className="mt-2" />
                </td>
                {data.days.map((d, di) => (
                  <td key={d} className="py-1.5 px-1">
                    <input type="number" min="0" max="24" step="0.25" inputMode="decimal" disabled={locked}
                           className="input-flat w-full !px-1 !py-1 text-center font-mono !text-xs" value={r.hours[d]}
                           aria-label={`Row ${i + 1} ${DAY_NAMES[di]} hours`}
                           onChange={(e) => set(i, { hours: { ...r.hours, [d]: e.target.value } })} />
                  </td>
                ))}
                <td className="py-1.5 px-1 text-right font-mono text-xs pt-3">{total ? fmtH(total) : "—"}</td>
                <td className="py-1.5 pt-2">
                  {!locked && (
                    <button type="button" className="btn-ghost text-xs !px-1.5" aria-label={`Remove row ${i + 1}`}
                            onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><X size={12} /></button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="text-xs font-mono">
            <td className="py-2 pr-2" colSpan={3}>
              {!locked && (
                <button type="button" className="btn-ghost text-xs font-sans" onClick={() => setRows((rs) => [...rs, blankRow(data.days)])}
                        data-testid="timesheet-add-row"><Plus size={12} /> Add row</button>
              )}
            </td>
            {dayTotals.map((t, i) => (
              <td key={i} className={`py-2 px-1 text-center ${t > 24 ? "text-[var(--danger)]" : "text-[var(--ink-2)]"}`}>{t ? fmtH(t) : ""}</td>
            ))}
            <td className="py-2 px-1 text-right font-semibold">{fmtH(dayTotals.reduce((a, b) => a + b, 0))}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function MyWeek({ week, setWeek, userId, onLoaded }) {
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const load = useCallback(async () => {
    const { data: d } = await api.get("/timesheets/week", { params: { week, ...(userId ? { user_id: userId } : {}) } });
    setData(d);
    const r = toRows(d.entries, d.days);
    setRows(r.length || d.status !== "empty" ? r : [blankRow(d.days)]);
    setDirty(false);
    onLoaded?.(d);
  }, [week, userId, onLoaded]);
  useEffect(() => { load().catch(() => setData(false)); }, [load]);
  const update = (fn) => { setRows(fn); setDirty(true); };

  const payload = () => {
    const entries = [];
    for (const r of rows) {
      for (const d of data.days) {
        const h = Number(r.hours[d]);
        if (!h) continue;
        if (!r.project_id) throw new Error("Choose a project for every row with hours.");
        entries.push({ date: d, project_id: r.project_id, phase_id: r.phase_id || null, hours: h, billable: r.billable, note: r.note });
      }
    }
    return { week: data.week, entries };
  };
  const save = async (quiet = false) => {
    setBusy(true);
    try {
      await api.put("/timesheets/week", payload());
      if (!quiet) toast.success("Week saved");
      await load();
      return true;
    } catch (e) {
      toast.error(e instanceof Error && !e.response ? e.message : errText(e, "Could not save"));
      return false;
    } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!await confirmAction({ title: "Submit this week?", body: "Your approver is notified. You can't change the hours unless they return the week.", confirmLabel: "Submit week" })) return;
    if (dirty && !await save(true)) return;
    try {
      await api.post("/timesheets/week/submit", { week: data.week });
      toast.success("Week submitted for approval");
      load();
    } catch (e) { toast.error(errText(e, "Could not submit")); }
  };

  if (data === false) return <div className="text-sm text-[var(--danger)]">Could not load the timesheet.</div>;
  if (!data) return <div className="skeleton h-48 w-full" />;
  const locked = ["submitted", "approved"].includes(data.status) || !!userId;
  const [label, tone] = STATUS[data.status] || STATUS.empty;
  const reason = data.entries.find((e) => e.rejection_reason)?.rejection_reason;
  return (
    <div className="card-flat space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost text-xs" aria-label="Previous week" onClick={() => setWeek(shiftWeek(week, -1))}><CaretLeft size={12} /></button>
          <div className="font-semibold text-sm" data-testid="timesheet-week">Week of {formatDate(data.week)}</div>
          <button type="button" className="btn-ghost text-xs" aria-label="Next week" onClick={() => setWeek(shiftWeek(week, 1))}><CaretRight size={12} /></button>
          <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded ${tone}`} data-testid="timesheet-status">{label}</span>
        </div>
        {!locked && (
          <div className="flex gap-2">
            <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={() => save()} data-testid="timesheet-save">Save</button>
            <button type="button" className="btn-primary text-xs" disabled={busy} onClick={submit} data-testid="timesheet-submit">Submit week</button>
          </div>
        )}
      </div>
      {data.status === "rejected" && reason && (
        <div className="text-xs border-l-4 border-l-[var(--warning)] bg-[var(--warning-soft)] text-[var(--warning)] px-3 py-2">Returned: {reason}</div>
      )}
      {data.projects.length === 0 ? (
        <div className="text-sm text-[var(--ink-3)]">You are not on any project yet, so there is nothing to log time against.</div>
      ) : (
        <WeekGrid data={data} rows={rows} setRows={update} locked={locked} />
      )}
      {!locked && <p className="text-[11px] text-[var(--ink-3)]">Hours round to the nearest quarter hour. Save as you go; submit once the week is complete.</p>}
    </div>
  );
}

function Approvals({ onView }) {
  const { hasPerm } = useAuth();
  const canApproveOwn = hasPerm("*.*");
  const [rows, setRows] = useState(null);
  const [returning, setReturning] = useState(null);
  const [reason, setReason] = useState("");
  const load = () => api.get("/timesheets/approvals").then(({ data }) => setRows(data)).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  const approve = async (r) => {
    try { await api.post("/timesheets/approve", { user_id: r.user_id, week: r.week }); toast.success(`Approved ${r.name}'s week`); load(); }
    catch (e) { toast.error(errText(e, "Could not approve")); }
  };
  const sendBack = async () => {
    try {
      await api.post("/timesheets/return", { user_id: returning.user_id, week: returning.week, reason });
      toast.success("Week returned"); setReturning(null); setReason(""); load();
    } catch (e) { toast.error(errText(e, "Could not return")); }
  };
  if (!rows) return <div className="skeleton h-32 w-full" />;
  return (
    <div className="card-flat" data-testid="timesheet-approvals">
      <div className="overline mb-3">WAITING FOR APPROVAL</div>
      {rows.length === 0 ? <div className="text-sm text-[var(--ink-3)]">Nothing to approve.</div> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr className="text-left text-[10px] font-mono uppercase text-[var(--ink-3)] border-b border-[var(--line)]">
              <th className="py-2 pr-3">Person</th><th className="py-2 pr-3">Week of</th><th className="py-2 pr-3 text-right">Hours</th>
              <th className="py-2 pr-3 text-right">Billable</th><th className="py-2 text-right">Actions</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.user_id}-${r.week}`} className="border-b border-[var(--line-soft)]">
                  <td className="py-2 pr-3">{r.name}</td>
                  <td className="py-2 pr-3">{formatDate(r.week)}</td>
                  <td className="py-2 pr-3 text-right font-mono">{r.hours}</td>
                  <td className="py-2 pr-3 text-right font-mono">{r.billable_hours}</td>
                  <td className="py-2 text-right whitespace-nowrap">
                    <button type="button" className="btn-ghost text-xs" onClick={() => onView(r)}>View</button>
                    {r.own && !canApproveOwn ? <span className="text-[10px] text-[var(--ink-3)] ml-2">needs another approver</span> : <>
                      <button type="button" className="btn-ghost text-xs" onClick={() => setReturning(r)}><ArrowUUpLeft size={12} /> Return</button>
                      <button type="button" className="btn-primary text-xs" onClick={() => approve(r)} data-testid={`approve-${r.user_id}`}><Check size={12} /> Approve</button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {returning && (
        <div className="mt-4 border border-[var(--line)] rounded-md p-3 space-y-2">
          <label className="text-xs block space-y-1"><span className="font-mono uppercase text-[var(--ink-3)]">Why return {returning.name}&apos;s week?</span>
            <input className="input-flat w-full" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Split the hours by phase" />
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-ghost text-xs" onClick={() => setReturning(null)}>Cancel</button>
            <button type="button" className="btn-primary text-xs" onClick={sendBack}>Return week</button>
          </div>
        </div>
      )}
    </div>
  );
}

function CostRates({ canSet }) {
  const [rows, setRows] = useState(null);
  const [edit, setEdit] = useState({});
  const load = () => api.get("/timesheets/cost-rates").then(({ data }) => setRows(data)).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  const save = async (r) => {
    const v = edit[r.id];
    try {
      await api.patch(`/employees/${r.id}/cost-rate`, { cost_rate_hourly: v === "" ? null : Number(v) });
      toast.success(`Rate saved for ${r.name}`);
      setEdit((s) => { const n = { ...s }; delete n[r.id]; return n; });
      load();
    } catch (e) { toast.error(errText(e, "Could not save the rate")); }
  };
  if (!rows) return <div className="skeleton h-32 w-full" />;
  return (
    <div className="card-flat" data-testid="cost-rates">
      <div className="overline mb-1">HOURLY COST PER PERSON</div>
      <p className="text-xs text-[var(--ink-2)] mb-3">
        Used when hours are approved. Without a set rate it is worked out from monthly gross pay × 12 ÷ (weekly hours × 52).
        Changing a rate affects only weeks approved after the change.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead><tr className="text-left text-[10px] font-mono uppercase text-[var(--ink-3)] border-b border-[var(--line)]">
            <th className="py-2 pr-3">Person</th><th className="py-2 pr-3 text-right">From salary</th>
            <th className="py-2 pr-3 text-right">Set rate</th><th className="py-2 pr-3 text-right">In use</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[var(--line-soft)]">
                <td className="py-2 pr-3">{r.name}<div className="text-[10px] text-[var(--ink-3)]">{r.designation}</div></td>
                <td className="py-2 pr-3 text-right font-mono">{r.derived_rate != null ? inr(r.derived_rate) : "—"}</td>
                <td className="py-2 pr-3 text-right">
                  {canSet ? (
                    <input type="number" min="0" step="1" className="input-flat !w-28 !py-1 text-right font-mono !text-xs"
                           aria-label={`Hourly rate for ${r.name}`} placeholder="Use salary"
                           value={edit[r.id] ?? (r.cost_rate_hourly ?? "")}
                           onChange={(e) => setEdit((s) => ({ ...s, [r.id]: e.target.value }))} />
                  ) : <span className="font-mono">{r.cost_rate_hourly != null ? inr(r.cost_rate_hourly) : "—"}</span>}
                </td>
                <td className="py-2 pr-3 text-right font-mono">{r.effective_rate != null ? inr(r.effective_rate) : "Not set"}</td>
                <td className="py-2 text-right">
                  {canSet && edit[r.id] !== undefined && <button type="button" className="btn-primary text-xs" onClick={() => save(r)}>Save</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function thisMonday() {
  const d = new Date();
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function Timesheets() {
  const [params, setParams] = useSearchParams();
  const [week, setWeekState] = useState(params.get("week") || thisMonday());
  const [tab, setTab] = useState(params.get("tab") || "week");
  const [viewing, setViewing] = useState(null);
  const [caps, setCaps] = useState(null);
  const setWeek = (w) => { setWeekState(w); setParams((p) => { p.set("week", w); return p; }, { replace: true }); };
  const onLoaded = useCallback((d) => setCaps((c) => c || { approve: d.can_approve, costs: d.can_see_costs, rates: d.can_set_rates }), []);
  useEffect(() => { if (tab !== "week") api.get("/timesheets/week").then(({ data }) => onLoaded(data)).catch(() => {}); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const tabs = useMemo(() => [["week", "My week"], ...(caps?.approve ? [["approvals", "Approvals"]] : []),
    ...(caps?.costs ? [["rates", "Cost rates"]] : [])], [caps]);
  return (
    <div className="space-y-6" data-testid="timesheets-page">
      <PageHero eyebrow="PROJECTS / TIME" title="Timesheets"
                kicker="Log hours against projects and phases each week; approvers sign them off and project costs follow." />
      <div className="flex flex-wrap gap-1 border-b border-[var(--line)]" role="tablist" aria-label="Timesheet sections">
        {tabs.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setViewing(null); }}
                  className={`px-4 py-2.5 text-sm border-b-2 -mb-px transition ${tab === k ? "border-[var(--accent)] text-[var(--accent-strong)] font-semibold" : "border-transparent text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === "week" && <MyWeek week={week} setWeek={setWeek} onLoaded={onLoaded} />}
      {tab === "approvals" && (viewing ? (
        <div className="space-y-3">
          <button type="button" className="btn-ghost text-xs" onClick={() => setViewing(null)}><CaretLeft size={12} /> Back to approvals · {viewing.name}</button>
          <MyWeek week={viewing.week} setWeek={(w) => setViewing({ ...viewing, week: w })} userId={viewing.user_id} />
        </div>
      ) : <Approvals onView={setViewing} />)}
      {tab === "rates" && <CostRates canSet={!!caps?.rates} />}
    </div>
  );
}
