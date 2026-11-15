import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { CaretLeft, CaretRight, X, Info } from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate } from "../lib/format";

const BAND = {
  off: "bg-white text-[var(--ink-3)]",
  light: "bg-[var(--surface-2)] text-[var(--ink-2)]",
  busy: "bg-[var(--info-soft)] text-[var(--ink)]",
  full: "bg-[var(--warning-soft)] text-[var(--warning)]",
  over: "bg-[var(--danger-soft)] text-[var(--danger)] font-semibold",
};
const LEGEND = [["light", "Under 50%"], ["busy", "50–85%"], ["full", "85–100%"], ["over", "Overbooked"]];

const toDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const toIso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const shift = (iso, weeks) => { const d = toDate(iso); d.setDate(d.getDate() + weeks * 7); return toIso(d); };
const label = (iso) => toDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const h = (n) => `${Math.round((n || 0) * 10) / 10}`.replace(/\.0$/, "");
const mondayBefore = (weeks) => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - weeks * 7); return toIso(d); };

function CellDetail({ row, cell, onClose }) {
  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`${row.name}, week of ${label(cell.week)}`}
        className="relative z-[291] w-full max-w-lg bg-white shadow-2xl max-h-[90vh] overflow-auto" data-testid="capacity-detail">
        <div className="flex items-start justify-between p-5 border-b border-[var(--line)]">
          <div>
            <div className="overline">WEEK OF {label(cell.week).toUpperCase()}</div>
            <div className="font-display font-bold text-xl">{row.name}</div>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4 text-sm">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
            <dt className="text-[var(--ink-2)]">Available</dt><dd className="font-mono text-right">{h(cell.capacity)} h</dd>
            {cell.holidays > 0 && <><dt className="text-[var(--ink-2)]">Holidays</dt><dd className="text-right">{cell.holidays} day{cell.holidays > 1 ? "s" : ""}</dd></>}
            {cell.leave_days > 0 && <><dt className="text-[var(--ink-2)]">On leave</dt><dd className="text-right">{cell.leave_days} day{cell.leave_days > 1 ? "s" : ""}</dd></>}
            <dt className="text-[var(--ink-2)]">Logged on timesheets</dt><dd className="font-mono text-right">{h(cell.logged)} h</dd>
            <dt className="text-[var(--ink-2)]">Planned from tasks</dt><dd className="font-mono text-right">{h(cell.planned)} h</dd>
            <dt className="font-semibold">Load</dt>
            <dd className="font-mono text-right font-semibold">{h(cell.load)} h{cell.pct != null ? ` · ${Math.round(cell.pct * 100)}%` : ""}</dd>
          </dl>
          {cell.tasks.length > 0 ? (
            <div>
              <div className="overline mb-1">Planned tasks</div>
              <ul className="divide-y divide-[var(--line-soft)] border-y border-[var(--line-soft)]">
                {cell.tasks.map((t) => (
                  <li key={t.id} className="py-2 flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <Link to={`/tasks/${t.id}`} className="font-semibold hover:underline [overflow-wrap:anywhere]">{t.title}</Link>
                      <div className="text-xs text-[var(--ink-2)]">
                        {t.project_name || "No project"} · due {formatDate(t.due_date)}
                        {t.overdue && <span className="text-[var(--danger)] font-semibold"> · overdue</span>}
                      </div>
                    </div>
                    <span className="font-mono text-xs whitespace-nowrap">{h(t.hours)} h</span>
                  </li>
                ))}
              </ul>
              {cell.more_tasks > 0 && <p className="text-xs text-[var(--ink-3)] mt-1">and {cell.more_tasks} smaller tasks</p>}
            </div>
          ) : <p className="text-[var(--ink-3)]">No planned task hours this week.</p>}
        </div>
      </div>
    </div>, document.body);
}

/** Team capacity: load vs available hours per person per week. */
export default function CapacityHeatmap() {
  const [start, setStart] = useState(() => mondayBefore(2));
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const boxRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setError("");
    api.get("/capacity", { params: { start, weeks: 10 } })
      .then(({ data: d }) => { if (alive) setData(d); })
      .catch((e) => { if (alive) { setData(null); setError(e?.response?.data?.detail || "Could not load capacity"); } });
    return () => { alive = false; };
  }, [start]);

  // On narrow screens bring this week into view instead of the past weeks.
  useEffect(() => {
    const box = boxRef.current;
    if (!data || !box) return;
    const current = box.querySelector('[data-current="true"]');
    const person = box.querySelector("thead th");
    if (current && person) box.scrollLeft = Math.max(0, current.offsetLeft - person.offsetWidth);
  }, [data]);

  return (
    <div className="space-y-4" data-testid="capacity">
      <div className="flex flex-wrap items-center gap-2">
        <div className="mr-auto">
          <div className="font-display font-bold text-lg">{data?.team_view ? "Team capacity" : "My capacity"}</div>
          <p className="text-xs text-[var(--ink-2)] max-w-2xl">
            Load against available hours (weekly offs, holidays and approved leave removed). Past weeks show hours logged on timesheets;
            coming weeks show task estimates spread between each task's start and due dates.
          </p>
        </div>
        <button type="button" className="btn-ghost text-xs" onClick={() => setStart(shift(start, -4))} aria-label="Earlier weeks"><CaretLeft size={13} /></button>
        <button type="button" className="btn-ghost text-xs" onClick={() => setStart(mondayBefore(2))}>This week</button>
        <button type="button" className="btn-ghost text-xs" onClick={() => setStart(shift(start, 4))} aria-label="Later weeks"><CaretRight size={13} /></button>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs" aria-label="Legend">
        {LEGEND.map(([k, text]) => (
          <span key={k} className="inline-flex items-center gap-1.5"><span className={`w-4 h-4 border border-[var(--line)] ${BAND[k]}`} />{text}</span>
        ))}
      </div>

      {error && <div className="border border-[var(--danger)] text-[var(--danger)] p-3 text-sm" role="alert">{error}</div>}
      {!data && !error && <div className="overline p-4">LOADING…</div>}
      {data && (
        <div ref={boxRef} className="border border-[var(--line)] overflow-x-auto">
          <table className="w-full text-sm border-collapse min-w-[900px]" data-testid="capacity-table">
            <thead>
              <tr className="bg-[var(--surface-2)]">
                <th className="sticky left-0 z-[1] bg-[var(--surface-2)] p-3 text-left overline min-w-[180px]">Person</th>
                {data.weeks.map((w) => (
                  <th key={w.week} data-current={w.is_current ? "true" : undefined} className={`p-2 text-center font-normal min-w-[78px] ${w.is_current ? "bg-[var(--hover)]" : ""}`}>
                    <div className="text-xs font-semibold">{label(w.week)}</div>
                    <div className="text-[10px] text-[var(--ink-3)]">{w.is_current ? "this week" : w.is_past ? "logged" : "planned"}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 && (
                <tr><td colSpan={data.weeks.length + 1} className="p-8 text-center text-[var(--ink-3)]">
                  No staff records to plan yet. Add employee records to see capacity.
                </td></tr>
              )}
              {data.rows.map((r) => (
                <tr key={r.id} className="border-t border-[var(--line-soft)]" data-testid={`capacity-row-${r.id}`}>
                  <th scope="row" className="sticky left-0 z-[1] bg-white p-3 text-left font-normal align-top">
                    <div className="font-semibold">{r.name}{r.is_me && <span className="ml-1.5 text-[10px] font-mono uppercase text-[var(--accent-strong)]">you</span>}</div>
                    <div className="text-[11px] text-[var(--ink-3)]">
                      {r.id === "_unassigned" ? "tasks with no current owner" : `${[r.designation, `${h(r.weekly_hours)} h/week`].filter(Boolean).join(" · ")}`}
                    </div>
                    {(r.unscheduled_hours > 0 || r.unestimated_tasks > 0) && (
                      <div className="text-[11px] text-[var(--warning)] mt-0.5 inline-flex items-start gap-1">
                        <Info size={11} className="mt-0.5 shrink-0" />
                        <span>{[r.unscheduled_hours > 0 && `${h(r.unscheduled_hours)} h without a due date`,
                          r.unestimated_tasks > 0 && `${r.unestimated_tasks} task${r.unestimated_tasks > 1 ? "s" : ""} without an estimate`].filter(Boolean).join(" · ")}</span>
                      </div>
                    )}
                  </th>
                  {r.cells.map((c) => (
                    <td key={c.week} className="p-1">
                      <button type="button" onClick={() => setOpen({ row: r, cell: c })}
                        className={`w-full h-full min-h-[48px] px-1 py-1.5 text-center border border-transparent hover:border-[var(--ink)] transition ${BAND[c.band] || BAND.light}`}
                        aria-label={`${r.name}, week of ${label(c.week)}: ${h(c.load)} of ${h(c.capacity)} hours`}
                        data-testid={`capacity-cell-${r.id}-${c.week}`}>
                        <div className="font-mono text-xs">{h(c.load)}{c.capacity ? <span className="opacity-60">/{h(c.capacity)}</span> : null}</div>
                        <div className="text-[10px]">
                          {c.pct != null ? `${Math.round(c.pct * 100)}%` : c.load ? "unowned" : "—"}
                          {(c.leave_days > 0 || c.holidays > 0) && <span className="opacity-70"> · {c.leave_days ? `${c.leave_days}L` : ""}{c.leave_days && c.holidays ? " " : ""}{c.holidays ? `${c.holidays}H` : ""}</span>}
                        </div>
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            {data.team_view && data.rows.length > 1 && (
              <tfoot>
                <tr className="border-t-2 border-[var(--line)] bg-[var(--surface-2)]">
                  <th scope="row" className="sticky left-0 z-[1] bg-[var(--surface-2)] p-3 text-left overline">Team</th>
                  {data.totals.map((t) => (
                    <td key={t.week} className="p-2 text-center text-xs">
                      <div className="font-mono">{h(t.load)}/{h(t.capacity)}</div>
                      <div className="text-[10px] text-[var(--ink-2)]">
                        {t.pct != null ? `${Math.round(t.pct * 100)}%` : "—"}{t.overbooked ? <span className="text-[var(--danger)] font-semibold"> · {t.overbooked} over</span> : null}
                      </div>
                    </td>
                  ))}
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
      {data && <p className="text-[11px] text-[var(--ink-3)]">L = days on approved leave, H = holidays. Set a task's estimate and dates on the task to plan it here.</p>}
      {open && <CellDetail row={open.row} cell={open.cell} onClose={() => setOpen(null)} />}
    </div>
  );
}
