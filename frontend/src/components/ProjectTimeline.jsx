import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { FlagBanner, X } from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate } from "../lib/format";
import { confirmAction } from "../lib/confirm";

const ROW = 34;
const NAME_W = 230;
const DAY = 86400000;
const toDate = (iso) => new Date(`${iso}T00:00:00`);
const days = (a, b) => Math.round((toDate(b) - toDate(a)) / DAY);
const addDays = (iso, n) => {
  const d = toDate(iso);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const localIso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const todayIso = () => localIso(new Date());

function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || String(x)).join(" · ");
  return fallback;
}

function Editor({ task, tasks, onClose, onSaved }) {
  const [start, setStart] = useState(task.start_date || task.start || "");
  const [due, setDue] = useState(task.due_date || task.finish || "");
  const [deps, setDeps] = useState(new Set(task.depends_on || []));
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const others = tasks.filter((t) => t.id !== task.id && (!q || (t.title || "").toLowerCase().includes(q.toLowerCase())));
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const { data } = await api.patch(`/tasks/${task.id}/schedule`, {
        start_date: start || null, due_date: due || null, depends_on: [...deps],
      });
      const msgs = [];
      if (data.moved_self) msgs.push("this task moved after the tasks it waits for");
      if (data.moved.length) msgs.push(`${data.moved.length} dependent task${data.moved.length === 1 ? "" : "s"} moved`);
      toast.success(msgs.length ? `Saved: ${msgs.join("; ")}` : "Schedule saved");
      onSaved();
    } catch (ex) { toast.error(errText(ex, "Could not save the schedule")); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <form role="dialog" aria-modal="true" aria-label={`Schedule ${task.title}`} onSubmit={save} onClick={(e) => e.stopPropagation()}
            className="bg-[var(--surface)] w-full max-w-lg max-h-[90vh] overflow-y-auto border border-[var(--line)] rounded-xl p-6 space-y-4"
            data-testid="schedule-editor">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="overline">SCHEDULE</div>
            <h2 className="font-display font-bold tracking-tight text-xl">{task.title}</h2>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost text-xs" aria-label="Close"><X size={14} /></button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs space-y-1"><span className="font-mono uppercase text-[var(--ink-3)]">Start</span>
            <input type="date" className="input-flat w-full" value={start} onChange={(e) => setStart(e.target.value)} data-testid="schedule-start" /></label>
          <label className="text-xs space-y-1"><span className="font-mono uppercase text-[var(--ink-3)]">Due</span>
            <input type="date" className="input-flat w-full" value={due} min={start || undefined} onChange={(e) => setDue(e.target.value)} data-testid="schedule-due" /></label>
        </div>
        <div>
          <div className="text-xs font-mono uppercase text-[var(--ink-3)] mb-1">Starts after these are due</div>
          <input className="input-flat w-full mb-2 !text-xs" placeholder="Find a task…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a task" />
          <div className="max-h-48 overflow-y-auto border border-[var(--line-soft)] rounded-md divide-y divide-[var(--line-soft)]">
            {others.length === 0 && <div className="text-xs text-[var(--ink-3)] p-3">No other dated tasks in this project.</div>}
            {others.map((t) => (
              <label key={t.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer">
                <input type="checkbox" checked={deps.has(t.id)} onChange={() => setDeps((s) => {
                  const n = new Set(s); if (n.has(t.id)) n.delete(t.id); else n.add(t.id); return n;
                })} />
                <span className="flex-1">{t.title}</span>
                <span className="text-[10px] font-mono text-[var(--ink-3)]">due {formatDate(t.finish)}</span>
              </label>
            ))}
          </div>
          <p className="text-[11px] text-[var(--ink-3)] mt-1">If one of them runs late, this task and anything after it move later automatically.</p>
        </div>
        <div className="flex justify-between gap-2">
          <Link to={`/tasks/${task.id}`} className="btn-ghost text-xs">Open task</Link>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
            <button disabled={busy} className="btn-primary" data-testid="schedule-save">{busy ? "Saving…" : "Save"}</button>
          </div>
        </div>
      </form>
    </div>
  );
}

/** Gantt-style project timeline with phases, dependencies and baseline (P2.8). */
export default function ProjectTimeline({ projectId }) {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => api.get(`/projects/${projectId}/timeline`).then(({ data: d }) => setData(d)).catch(() => setData(false)), [projectId]);
  useEffect(() => { load(); }, [load]);

  const layout = useMemo(() => {
    if (!data || !data.tasks.length) return null;
    const isos = [];
    for (const t of data.tasks) {
      isos.push(t.start, t.finish);
      if (t.baseline?.start_date) isos.push(t.baseline.start_date, t.baseline.due_date);
    }
    for (const p of data.phases) if (p.planned_start && p.planned_end) isos.push(p.planned_start, p.planned_end);
    const sorted = isos.filter(Boolean).sort();
    const from = addDays(sorted[0], -2);
    const to = addDays(sorted[sorted.length - 1], 4);
    const total = days(from, to) + 1;
    const dayW = total <= 45 ? 28 : total <= 120 ? 14 : total <= 365 ? 6 : 3;
    const x = (iso) => days(from, iso) * dayW;
    const phases = data.phases.filter((p) => p.planned_start && p.planned_end);
    const rowOf = {};
    data.tasks.forEach((t, i) => { rowOf[t.id] = phases.length + i; });
    return { from, to, total, dayW, x, phases, rowOf, width: total * dayW };
  }, [data]);

  const saveBaseline = async () => {
    if (!await confirmAction({ title: data.project.baseline_set_at ? "Replace the baseline?" : "Save a baseline?",
      body: "Every task's current dates become the plan to compare against. Later slips show as +days.", confirmLabel: "Save baseline" })) return;
    try {
      const { data: d } = await api.post(`/projects/${projectId}/baseline`);
      toast.success(`Baseline saved for ${d.tasks} task${d.tasks === 1 ? "" : "s"}`);
      load();
    } catch (e) { toast.error(errText(e, "Could not save the baseline")); }
  };

  if (data === false) return <div className="text-sm text-[var(--danger)]">Could not load the timeline.</div>;
  if (!data) return <div className="skeleton h-64 w-full" />;
  const { summary } = data;
  const months = [];
  if (layout) {
    let cur = layout.from;
    while (cur <= layout.to) {
      const d = toDate(cur);
      const nextMonth = localIso(new Date(d.getFullYear(), d.getMonth() + 1, 1));
      const segEnd = nextMonth > layout.to ? addDays(layout.to, 1) : nextMonth;
      months.push({ label: d.toLocaleDateString("en-IN", { month: "short", year: "numeric" }),
        x: layout.x(cur), w: days(cur, segEnd) * layout.dayW });
      cur = segEnd;
    }
  }
  const today = todayIso();
  const rows = (layout?.phases.length || 0) + data.tasks.length;
  return (
    <div className="space-y-4" data-testid="project-timeline">
      <div className="card-flat">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div>
            <div className="overline">TIMELINE</div>
            <div className="text-xs text-[var(--ink-2)] mt-1">
              {summary.dated} dated task{summary.dated === 1 ? "" : "s"}
              {data.project.baseline_set_at
                ? <> · baseline {formatDate(data.project.baseline_set_at)} · {summary.behind_baseline
                  ? <span className="text-[var(--danger)]">{summary.behind_baseline} behind, up to {summary.worst_slip_days} day{summary.worst_slip_days === 1 ? "" : "s"}</span>
                  : "on plan"}</>
                : " · no baseline yet"}
            </div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-3 text-[10px] font-mono uppercase text-[var(--ink-3)]" aria-hidden="true">
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-2 rounded-sm bg-[var(--accent-strong)]" />Task</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-1 rounded-sm bg-[var(--line-strong)]" />Baseline</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-2 rounded-sm bg-[var(--hover)] border border-[var(--line)]" />Phase</span>
            </div>
            {data.can_edit && (
              <button type="button" className="btn-ghost text-xs" onClick={saveBaseline} data-testid="save-baseline">
                <FlagBanner size={12} /> {data.project.baseline_set_at ? "Re-save baseline" : "Save baseline"}
              </button>
            )}
          </div>
        </div>
        {!layout ? (
          <div className="text-sm text-[var(--ink-3)] py-6 text-center">
            No task in this project has a due date yet. Give tasks dates to see them here.
          </div>
        ) : (
          <div className="overflow-x-auto border border-[var(--line-soft)] rounded-md" role="region" aria-label="Project timeline chart" tabIndex={0}>
            <div className="relative" style={{ width: NAME_W + layout.width, minWidth: "100%" }}>
              {/* header */}
              <div className="flex sticky top-0 bg-[var(--surface)] z-10 border-b border-[var(--line)]" style={{ height: 30 }}>
                <div className="sticky left-0 bg-[var(--surface)] z-20 border-r border-[var(--line)] text-[10px] font-mono uppercase text-[var(--ink-3)] px-3 flex items-center"
                     style={{ width: NAME_W, minWidth: NAME_W }}>Task</div>
                <div className="relative" style={{ width: layout.width }}>
                  {months.map((m) => (
                    <div key={m.label + m.x} className="absolute top-0 h-full border-l border-[var(--line-soft)] text-[10px] font-mono text-[var(--ink-2)] px-1.5 flex items-center"
                         style={{ left: m.x, width: m.w }}>{m.label}</div>
                  ))}
                </div>
              </div>
              {/* rows */}
              <div className="relative" style={{ height: rows * ROW }}>
                {/* today line */}
                {today >= layout.from && today <= layout.to && (
                  <div className="absolute top-0 bottom-0 w-px bg-[var(--danger)] opacity-60 z-[5]" style={{ left: NAME_W + layout.x(today) + layout.dayW / 2 }}
                       title={`Today ${formatDate(today)}`} />
                )}
                {layout.phases.map((p, i) => (
                  <div key={p.id} className="absolute left-0 right-0 flex items-center border-b border-[var(--line-soft)] bg-[var(--surface-2)]/40" style={{ top: i * ROW, height: ROW }}>
                    <div className="sticky left-0 bg-[var(--surface-2)] z-[6] h-full px-3 flex items-center text-xs font-semibold text-[var(--ink-2)] border-r border-[var(--line)] truncate"
                         style={{ width: NAME_W, minWidth: NAME_W }} title={p.name}>Phase · {p.name}</div>
                    <div className="absolute rounded bg-[var(--hover)] border border-[var(--line)]" title={`${p.name}: ${formatDate(p.planned_start)} – ${formatDate(p.planned_end)}`}
                         style={{ left: NAME_W + layout.x(p.planned_start), width: (days(p.planned_start, p.planned_end) + 1) * layout.dayW, top: 9, height: ROW - 18 }} />
                  </div>
                ))}
                {data.tasks.map((t) => {
                  const r = layout.rowOf[t.id];
                  const done = t.status === "done";
                  const late = (t.variance_days || 0) > 0 && !done;
                  const overdue = !done && t.finish < today;
                  return (
                    <div key={t.id} className="absolute left-0 right-0 border-b border-[var(--line-soft)]" style={{ top: r * ROW, height: ROW }}>
                      <button type="button" onClick={() => data.can_edit && setEditing(t)} disabled={!data.can_edit}
                              className="sticky left-0 bg-[var(--surface)] z-[6] h-full px-3 flex items-center gap-2 text-left text-xs border-r border-[var(--line)] w-full disabled:cursor-default hover:bg-[var(--hover)]"
                              style={{ width: NAME_W, minWidth: NAME_W }} data-testid={`timeline-task-${t.id}`}
                              aria-label={`${t.title}, ${formatDate(t.start)} to ${formatDate(t.finish)}${late ? `, ${t.variance_days} days behind baseline` : ""}`}>
                        <span className={`truncate flex-1 ${done ? "line-through text-[var(--ink-3)]" : ""}`}>{t.title}</span>
                        {late && <span className="text-[10px] font-mono text-[var(--danger)] shrink-0">+{t.variance_days}d</span>}
                      </button>
                      {t.baseline?.start_date && (
                        <div className="absolute rounded-full bg-[var(--line-strong)]" title={`Baseline ${formatDate(t.baseline.start_date)} – ${formatDate(t.baseline.due_date)}`}
                             style={{ left: NAME_W + layout.x(t.baseline.start_date), width: Math.max(layout.dayW, (days(t.baseline.start_date, t.baseline.due_date) + 1) * layout.dayW), top: ROW - 9, height: 3 }} />
                      )}
                      <div className={`absolute rounded-md ${done ? "bg-[var(--success)] opacity-60" : overdue ? "bg-[var(--danger)]" : "bg-[var(--accent-strong)]"}`}
                           title={`${t.title}: ${formatDate(t.start)} – ${formatDate(t.finish)}${t.assignee_name ? ` · ${t.assignee_name}` : ""}`}
                           style={{ left: NAME_W + layout.x(t.start), width: Math.max(layout.dayW - 2, (days(t.start, t.finish) + 1) * layout.dayW - 2), top: 8, height: ROW - 20 }} />
                    </div>
                  );
                })}
                {/* dependency lines */}
                <svg className="absolute top-0 left-0 pointer-events-none z-[4]" width={NAME_W + layout.width} height={rows * ROW} aria-hidden="true">
                  <defs>
                    <marker id="tl-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                      <path d="M0,0 L6,3 L0,6 z" fill="#8B7F6A" />
                    </marker>
                  </defs>
                  {data.tasks.flatMap((t) => (t.depends_on || []).filter((d) => layout.rowOf[d] !== undefined).map((d) => {
                    const p = data.tasks.find((x) => x.id === d);
                    const x1 = NAME_W + layout.x(p.finish) + layout.dayW - 2;
                    const y1 = layout.rowOf[d] * ROW + ROW / 2;
                    const x2 = NAME_W + layout.x(t.start);
                    const y2 = layout.rowOf[t.id] * ROW + ROW / 2;
                    const mid = Math.max(x1 + 6, Math.min(x2 - 6, x1 + 10));
                    return <path key={`${d}-${t.id}`} d={`M${x1},${y1} H${mid} V${y2} H${x2 - 1}`} fill="none" stroke="#8B7F6A" strokeWidth="1.2" markerEnd="url(#tl-arrow)" />;
                  }))}
                </svg>
              </div>
            </div>
          </div>
        )}
        {data.can_edit && layout && <p className="text-[11px] text-[var(--ink-3)] mt-2">Select a task name to change its dates or what it waits for.</p>}
      </div>
      {data.undated.length > 0 && (
        <div className="card-flat">
          <div className="overline mb-2">NOT ON THE TIMELINE · {data.undated.length}</div>
          <p className="text-xs text-[var(--ink-2)] mb-2">These tasks have no due date yet.</p>
          <div className="flex flex-wrap gap-2">
            {data.undated.slice(0, 30).map((t) => <Link key={t.id} to={`/tasks/${t.id}`} className="text-xs px-2 py-1 border border-[var(--line)] rounded-md hover:bg-[var(--hover)]">{t.title}</Link>)}
          </div>
        </div>
      )}
      {editing && <Editor task={editing} tasks={data.tasks} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </div>
  );
}
