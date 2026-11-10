import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle, Clock, Kanban, CalendarCheck, CaretRight } from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate } from "../lib/format";

const time = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
  } catch { return ""; }
};

/** Everyone's own day, whatever their role: tasks, check-in and free leave. */
export default function MyDay() {
  const [d, setD] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { api.get("/dashboard/my-day").then(({ data }) => setD(data)).catch(() => setD(null)); }, []);
  if (!d) return null;
  const t = d.tasks || {};
  const a = d.attendance;
  const l = d.leave;
  if (!t.open && !a && !l) return null;   // nothing personal to show (e.g. an owner with no staff record)
  return (
    <section className="fade-up card-flat" data-testid="my-day" aria-label="My day">
      <div className="flex items-center justify-between mb-4">
        <div className="overline">MY DAY</div>
        <button type="button" onClick={() => navigate("/tasks")} className="overline hover:text-[var(--accent-strong)] flex items-center gap-1">
          ALL MY TASKS <CaretRight size={10} weight="bold" />
        </button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <div className="flex flex-wrap gap-2 mb-3 text-xs">
            <span className="px-2 py-1 rounded-full bg-[var(--hover)]"><b>{t.open || 0}</b> open</span>
            <span className={`px-2 py-1 rounded-full ${t.overdue ? "bg-[var(--danger-soft)] text-[var(--danger)]" : "bg-[var(--hover)]"}`}><b>{t.overdue || 0}</b> overdue</span>
            <span className="px-2 py-1 rounded-full bg-[var(--hover)]"><b>{t.due_today || 0}</b> due today</span>
          </div>
          {(t.focus || []).length === 0 ? (
            <div className="text-sm text-[var(--ink-3)] py-3 flex items-center gap-2"><CheckCircle size={16} className="text-[var(--success)]" /> Nothing assigned to you right now.</div>
          ) : (
            <ul className="divide-y divide-[var(--line-soft)]" data-testid="my-day-tasks">
              {t.focus.map((task) => {
                const late = task.due_date && task.due_date < d.date;
                return (
                  <li key={task.id}>
                    <button type="button" onClick={() => navigate(`/tasks/${task.id}`)}
                      className="w-full flex items-center gap-3 py-2 text-left hover:bg-[var(--surface-2)] px-1">
                      <Kanban size={14} className="text-[var(--ink-3)] shrink-0" />
                      <span className="flex-1 min-w-0">
                        <span className="block text-sm font-medium truncate">{task.title}</span>
                        {task.project_name && <span className="block text-[11px] text-[var(--ink-3)] truncate">{task.project_name}</span>}
                      </span>
                      <span className={`text-[11px] shrink-0 ${late ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-2)]"}`}>
                        {task.due_date ? (late ? `was due ${formatDate(task.due_date)}` : task.due_date === d.date ? "today" : formatDate(task.due_date)) : "no date"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="space-y-3">
          {a && (
            <button type="button" onClick={() => navigate("/attendance")} data-testid="my-day-attendance"
              className="w-full text-left border border-[var(--line)] rounded-md p-3 hover:border-[var(--accent-strong)] transition">
              <div className="flex items-center gap-2 text-xs text-[var(--ink-2)]"><Clock size={14} /> Attendance today</div>
              <div className="mt-1 text-sm font-semibold">
                {a.checked_out ? "Checked out" : a.checked_in ? `Checked in at ${time(a.check_in)}` : "Not checked in yet"}
              </div>
              {!a.checked_in && <div className="text-[11px] text-[var(--accent-strong)] mt-0.5">Open Attendance to check in</div>}
            </button>
          )}
          {l && (
            <div className="border border-[var(--line)] rounded-md p-3" data-testid="my-day-leave">
              <div className="flex items-center gap-2 text-xs text-[var(--ink-2)]"><CalendarCheck size={14} /> Leave this month</div>
              <div className="mt-1 text-sm font-semibold">
                {l.free_left > 0 ? "Your free leave is still available" : `${l.used_this_month} day${l.used_this_month === 1 ? "" : "s"} taken`}
              </div>
              <div className="text-[11px] text-[var(--ink-3)] mt-0.5">One leave a month is free; extra days are deducted from salary.</div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
