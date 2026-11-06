import { useMemo, useState } from "react";
import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { dateForInput } from "../lib/format";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const PRIORITY_DOT = { low: "#6E6A63", medium: "#76705E", high: "#B87500", urgent: "#B22B22", critical: "#B22B22" };

function monthGrid(cursor) {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7;            // Monday first
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
}

/**
 * Work board calendar: the same task records, placed on their due date.
 * Drag a task onto a day to set its due date; undated work sits in
 * "Unscheduled". Clicking a task opens it.
 */
export default function TaskCalendar({ tasks, onOpen, onReschedule }) {
  const [cursor, setCursor] = useState(() => new Date());
  const [dragId, setDragId] = useState(null);
  const [overDay, setOverDay] = useState(null);
  const today = dateForInput(new Date());
  const days = useMemo(() => monthGrid(cursor), [cursor]);
  const byDay = useMemo(() => {
    const m = {};
    tasks.forEach((t) => {
      const d = (t.due_date || "").slice(0, 10);
      if (d) (m[d] = m[d] || []).push(t);
    });
    return m;
  }, [tasks]);
  const unscheduled = tasks.filter((t) => !t.due_date && t.status !== "done");
  const label = cursor.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const shift = (n) => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + n, 1));

  const drop = (day) => {
    if (dragId) onReschedule(dragId, day);
    setDragId(null);
    setOverDay(null);
  };

  const Chip = ({ t }) => {
    const overdue = t.due_date && t.due_date < today && t.status !== "done";
    return (
      <button type="button" draggable onDragStart={() => setDragId(t.id)} onClick={() => onOpen(t.id)}
              title={`${t.title}${t.project_name ? ` · ${t.project_name}` : ""}`}
              className={`w-full text-left text-[11.5px] leading-tight px-1.5 py-1 rounded-md border truncate flex items-center gap-1.5 transition-colors cursor-grab active:cursor-grabbing
                ${t.status === "done" ? "line-through text-[var(--ink-3)] bg-[var(--surface-2)] border-[var(--line)]"
                  : overdue ? "bg-[var(--danger-soft)] border-[#F1CFCF] text-[var(--danger)]"
                    : "bg-white border-[var(--line)] hover:border-[var(--accent)]"}`}
              data-testid={`cal-task-${t.id}`}>
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: PRIORITY_DOT[t.priority] || "#76705E" }} />
        <span className="truncate">{t.title}</span>
      </button>
    );
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-4" data-testid="task-calendar">
      <div className="card-flat !p-0 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--line)]">
          <div className="flex items-center gap-1">
            <button type="button" className="btn-icon" onClick={() => shift(-1)} aria-label="Previous month"><CaretLeft size={16} /></button>
            <button type="button" className="btn-ghost text-xs" onClick={() => setCursor(new Date())}>Today</button>
            <button type="button" className="btn-icon" onClick={() => shift(1)} aria-label="Next month"><CaretRight size={16} /></button>
          </div>
          <div className="font-display font-bold text-lg" data-testid="task-cal-label">{label}</div>
          <div className="text-xs text-[var(--ink-3)] hidden sm:block">Drag a task to a day to set its due date</div>
        </div>
        <div className="grid grid-cols-7 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--ink-3)] bg-[var(--surface-2)] border-b border-[var(--line)]">
          {WEEKDAYS.map((d) => <div key={d} className="px-2 py-2">{d}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d) => {
            const key = dateForInput(d);
            const inMonth = d.getMonth() === cursor.getMonth();
            const list = byDay[key] || [];
            return (
              <div key={key}
                   onDragOver={(e) => { e.preventDefault(); setOverDay(key); }}
                   onDragLeave={() => setOverDay(null)}
                   onDrop={() => drop(key)}
                   className={`min-h-[104px] border-b border-r border-[var(--line-soft)] p-1.5 space-y-1 transition-colors
                     ${inMonth ? "bg-white" : "bg-[var(--surface-2)]"} ${overDay === key ? "!bg-[var(--hover)]" : ""}`}
                   data-testid={`task-day-${key}`}>
                <div className={`text-[11px] w-6 h-6 flex items-center justify-center rounded-full
                  ${key === today ? "bg-[var(--accent-strong)] text-white font-semibold" : inMonth ? "text-[var(--ink)]" : "text-[var(--ink-3)]"}`}>
                  {d.getDate()}
                </div>
                {list.slice(0, 3).map((t) => <Chip key={t.id} t={t} />)}
                {list.length > 3 && <div className="text-[10.5px] text-[var(--ink-3)] px-1">+{list.length - 3} more</div>}
              </div>
            );
          })}
        </div>
      </div>
      <aside className="card-flat h-fit" data-testid="task-unscheduled"
             onDragOver={(e) => e.preventDefault()}>
        <h3 className="font-display font-bold text-lg">Unscheduled</h3>
        <p className="text-xs text-[var(--ink-3)] mt-0.5 mb-3">Work with no due date. Drag one onto a day.</p>
        {unscheduled.length === 0 ? (
          <p className="text-sm text-[var(--ink-3)]">Everything has a due date.</p>
        ) : (
          <div className="space-y-1.5 max-h-[520px] overflow-y-auto">
            {unscheduled.map((t) => <Chip key={t.id} t={t} />)}
          </div>
        )}
      </aside>
    </div>
  );
}
