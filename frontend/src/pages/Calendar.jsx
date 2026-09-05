import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import { useAuth } from "../context/AuthContext";
import {
  CaretLeft, CaretRight, Plus, X, Trash, MapPin, Clock as ClockIcon,
} from "@phosphor-icons/react";

/* ---------- constants ---------- */
const KIND_META = {
  task:             { label: "Tasks",       color: "#8B7F6A" },
  meeting:          { label: "Meetings",    color: "#1D633E" },
  reminder:         { label: "Reminders",   color: "#B87500" },
  milestone:        { label: "Milestones",  color: "#8A6DFF" },
  project_deadline: { label: "Deadlines",   color: "#0A0A0A" },
  invoice_due:      { label: "Invoices",    color: "#B4001C" },
  holiday:          { label: "Holidays",    color: "#3B82F6" },
  leave:            { label: "Leaves",      color: "#F0A93A" },
  deadline:         { label: "Deadlines",   color: "#0A0A0A" },
  other:            { label: "Other",       color: "#5C5C5C" },
};
const kindColor = (k) => (KIND_META[k] || KIND_META.other).color;

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const WEEKDAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

/* Local YYYY-MM-DD (never use toISOString — TZ shifts the day) */
const ymd = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const mondayOf = (d) => { const x = new Date(d); const wd = (x.getDay() + 6) % 7; return addDays(x, -wd); };
const fmtNice = (s) => {
  if (!s) return "";
  const [y, m, dd] = s.split("-").map(Number);
  return new Date(y, m - 1, dd).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
};

export default function CalendarPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [view, setView] = useState("month");            // month | week | agenda
  const [cursor, setCursor] = useState(() => new Date());
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hiddenKinds, setHiddenKinds] = useState({});   // kind -> true (hidden)
  const [selectedDay, setSelectedDay] = useState(null); // YYYY-MM-DD
  const [modal, setModal] = useState(null);             // null | {mode:"create"|"edit", data}

  /* ---- visible range for the current view ---- */
  const range = useMemo(() => {
    if (view === "week") {
      const start = mondayOf(cursor);
      return { start, end: addDays(start, 6) };
    }
    if (view === "agenda") {
      return { start: new Date(cursor), end: addDays(cursor, 29) };
    }
    // month grid — Monday-start, 6 rows
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const gridStart = mondayOf(first);
    return { start: gridStart, end: addDays(gridStart, 41) };
  }, [view, cursor]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/calendar/feed?start=${ymd(range.start)}&end=${ymd(range.end)}`);
      setItems(data.items || []);
    } catch {
      toast.error("Could not load the calendar feed");
    } finally { setLoading(false); }
  }, [range.start, range.end]);
  useEffect(() => { load(); }, [load]);

  const visible = useMemo(
    () => items.filter((i) => !hiddenKinds[i.kind === "deadline" ? "project_deadline" : i.kind]),
    [items, hiddenKinds],
  );
  const byDate = useMemo(() => {
    const m = {};
    for (const it of visible) {
      if (!it.date) continue;
      (m[it.date] = m[it.date] || []).push(it);
    }
    return m;
  }, [visible]);

  /* ---- navigation ---- */
  const go = (dir) => {
    const x = new Date(cursor);
    if (view === "month") {
      // Normalise to the 1st before shifting months — otherwise e.g.
      // Aug 31 + 1 month rolls over to Oct 1 (Sep 31 doesn't exist).
      x.setDate(1);
      x.setMonth(x.getMonth() + dir);
    }
    else if (view === "week") x.setDate(x.getDate() + dir * 7);
    else x.setDate(x.getDate() + dir * 30);
    setCursor(x);
    setSelectedDay(null);
  };
  const goToday = () => { setCursor(new Date()); setSelectedDay(null); };

  const headerLabel = view === "month"
    ? `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`
    : view === "week"
      ? `${fmtNice(ymd(mondayOf(cursor)))} → ${fmtNice(ymd(addDays(mondayOf(cursor), 6)))}`
      : `${fmtNice(ymd(cursor))} → ${fmtNice(ymd(addDays(cursor, 29)))}`;

  /* ---- item interaction ---- */
  const openItem = (it) => {
    if (it.event) {
      setModal({ mode: "edit", data: { ...it.event } });
    } else if (it.link) {
      navigate(it.link);
    }
  };

  const todayStr = ymd(new Date());

  return (
    <div className="space-y-6" data-testid="calendar-page">
      <PageHero
        eyebrow="STUDIO / CALENDAR"
        title="Everything, on time."
        kicker="Tasks, meetings, deadlines, invoices, holidays and reminders — one unified studio calendar."
      >
        <button className="btn-primary" onClick={() => setModal({ mode: "create", data: { kind: "meeting", date: selectedDay || todayStr } })}
                data-testid="new-event-btn">
          <Plus size={14} /> New event
        </button>
      </PageHero>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div className="flex items-center gap-2">
          <button onClick={() => go(-1)} className="btn-ghost px-2" data-testid="cal-prev"><CaretLeft size={16} /></button>
          <button onClick={goToday} className="btn-ghost text-xs font-mono uppercase" data-testid="cal-today">Today</button>
          <button onClick={() => go(1)} className="btn-ghost px-2" data-testid="cal-next"><CaretRight size={16} /></button>
          <div className="font-display font-bold text-lg ml-2" data-testid="cal-header-label">{headerLabel}</div>
        </div>
        <div className="flex items-center gap-1 border border-[#E5E5E5]">
          {["month", "week", "agenda"].map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider ${view === v ? "bg-[#0A0A0A] text-white" : "text-[#5C5C5C] hover:text-[#0A0A0A]"}`}
              data-testid={`view-${v}`}>{v}</button>
          ))}
        </div>
      </div>

      {/* Kind filters */}
      <div className="flex flex-wrap items-center gap-2" data-testid="kind-filters">
        {Object.entries(KIND_META).filter(([k]) => k !== "deadline" && k !== "other").map(([k, meta]) => {
          const off = hiddenKinds[k];
          return (
            <button key={k}
              onClick={() => setHiddenKinds((h) => ({ ...h, [k]: !h[k] }))}
              className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-mono uppercase tracking-wider border transition ${off ? "border-[#E5E5E5] text-[#9A9A9A] line-through" : "border-transparent"}`}
              style={off ? {} : { background: `${meta.color}14`, color: meta.color }}
              data-testid={`filter-${k}`}>
              <span className="w-2 h-2 rounded-full" style={{ background: off ? "#C9C9C9" : meta.color }} />
              {meta.label}
            </button>
          );
        })}
      </div>

      {loading && <div className="skeleton h-96 w-full" data-testid="calendar-loading" />}

      {/* ============ MONTH ============ */}
      {!loading && view === "month" && (
        <div data-testid="month-grid">
          <div className="grid grid-cols-7 border-l border-t border-[#E5E5E5]">
            {WEEKDAYS.map((d) => (
              <div key={d} className="bg-[#FAFAFA] border-r border-b border-[#E5E5E5] p-1.5 text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C] text-center">{d}</div>
            ))}
            {Array.from({ length: 42 }).map((_, i) => {
              const d = addDays(range.start, i);
              const ds = ymd(d);
              const inMonth = d.getMonth() === cursor.getMonth();
              const dayItems = byDate[ds] || [];
              const isToday = ds === todayStr;
              return (
                <button key={ds} onClick={() => setSelectedDay(selectedDay === ds ? null : ds)}
                  className={`min-h-[92px] border-r border-b border-[#E5E5E5] p-1 text-left align-top transition hover:bg-[#F7F8FA] ${inMonth ? "bg-white" : "bg-[#FCFCFC]"} ${selectedDay === ds ? "ring-2 ring-inset ring-[#8B7F6A]" : ""}`}
                  data-testid={`day-${ds}`}>
                  <div className={`text-[11px] font-mono mb-1 w-6 h-6 flex items-center justify-center ${isToday ? "bg-[#8B7F6A] text-white rounded-full" : inMonth ? "text-[#0A0A0A]" : "text-[#C9C9C9]"}`}>
                    {d.getDate()}
                  </div>
                  <div className="space-y-0.5">
                    {dayItems.slice(0, 3).map((it) => (
                      <div key={it.id} className="truncate text-[10px] leading-4 px-1 rounded-sm"
                           style={{ background: `${kindColor(it.kind)}14`, color: kindColor(it.kind) }}>
                        {it.time ? `${it.time} · ` : ""}{it.title}
                      </div>
                    ))}
                    {dayItems.length > 3 && (
                      <div className="text-[10px] text-[#5C5C5C] px-1">+{dayItems.length - 3} more</div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Selected day detail */}
          {selectedDay && (
            <div className="card-flat mt-4" data-testid="selected-day-panel">
              <div className="flex items-center justify-between mb-3">
                <div className="overline">{fmtNice(selectedDay).toUpperCase()} · {(byDate[selectedDay] || []).length} items</div>
                <div className="flex items-center gap-2">
                  <button className="btn-ghost text-xs" onClick={() => setModal({ mode: "create", data: { kind: "meeting", date: selectedDay } })}
                          data-testid="day-add-event"><Plus size={12} /> Add event</button>
                  <button className="btn-ghost text-xs" onClick={() => setSelectedDay(null)}><X size={12} /></button>
                </div>
              </div>
              {(byDate[selectedDay] || []).length === 0 && (
                <div className="text-sm text-[#9A9A9A] py-4 text-center">Nothing scheduled on this day.</div>
              )}
              <div className="space-y-1.5">
                {(byDate[selectedDay] || []).map((it) => <AgendaRow key={it.id} it={it} onOpen={openItem} />)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ============ WEEK ============ */}
      {!loading && view === "week" && (
        <div className="grid grid-cols-1 md:grid-cols-7 border-l border-t border-[#E5E5E5]" data-testid="week-grid">
          {Array.from({ length: 7 }).map((_, i) => {
            const d = addDays(range.start, i);
            const ds = ymd(d);
            const dayItems = byDate[ds] || [];
            const isToday = ds === todayStr;
            return (
              <div key={ds} className="border-r border-b border-[#E5E5E5] bg-white min-h-[160px]">
                <div className={`p-2 border-b border-[#F0F0F0] flex items-center justify-between ${isToday ? "bg-[#F5F4F0]" : "bg-[#FAFAFA]"}`}>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">{WEEKDAYS[i]}</span>
                  <span className={`text-xs font-mono ${isToday ? "text-[#8B7F6A] font-bold" : ""}`}>{d.getDate()}</span>
                </div>
                <div className="p-1.5 space-y-1">
                  {dayItems.map((it) => (
                    <button key={it.id} onClick={() => openItem(it)}
                      className="w-full text-left text-[11px] leading-4 px-1.5 py-1 rounded-sm hover:opacity-80"
                      style={{ background: `${kindColor(it.kind)}14`, color: kindColor(it.kind) }}
                      data-testid={`week-item-${it.id}`}>
                      {it.time && <span className="font-mono">{it.time} · </span>}{it.title}
                    </button>
                  ))}
                  {dayItems.length === 0 && <div className="text-[10px] text-[#D5D5D5] px-1 py-2">—</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ============ AGENDA ============ */}
      {!loading && view === "agenda" && (
        <div className="space-y-4" data-testid="agenda-list">
          {Object.keys(byDate).sort().map((ds) => (
            <div key={ds}>
              <div className={`overline mb-1.5 ${ds === todayStr ? "text-[#8B7F6A]" : ""}`}>
                {fmtNice(ds).toUpperCase()}{ds === todayStr ? " · TODAY" : ""}
              </div>
              <div className="space-y-1.5">
                {byDate[ds].map((it) => <AgendaRow key={it.id} it={it} onOpen={openItem} />)}
              </div>
            </div>
          ))}
          {visible.length === 0 && (
            <div className="card-flat text-center py-14 text-[#9A9A9A]" data-testid="agenda-empty">
              Nothing scheduled in the next 30 days.
              <div className="mt-3">
                <button className="btn-primary" onClick={() => setModal({ mode: "create", data: { kind: "meeting", date: todayStr } })}>
                  <Plus size={13} /> Schedule something
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {modal && (
        <EventModal
          mode={modal.mode}
          initial={modal.data}
          me={user}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(); }}
        />
      )}
    </div>
  );
}

/* ---------- agenda row ---------- */
function AgendaRow({ it, onOpen }) {
  const c = kindColor(it.kind);
  return (
    <button onClick={() => onOpen(it)}
      className="w-full card-flat !py-2.5 flex items-center gap-3 text-left hover:border-[#0A0A0A] transition"
      data-testid={`agenda-item-${it.id}`}>
      <span className="w-1 self-stretch rounded-full" style={{ background: c }} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold truncate">{it.title}</div>
        {(it.subtitle || it.meta?.status) && (
          <div className="text-xs text-[#5C5C5C] truncate">
            {[it.subtitle, it.meta?.status, it.meta?.priority].filter(Boolean).join(" · ")}
          </div>
        )}
      </div>
      {it.time && <span className="text-xs font-mono text-[#5C5C5C] flex items-center gap-1"><ClockIcon size={12} />{it.time}</span>}
      <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5"
            style={{ background: `${c}14`, color: c }}>
        {(KIND_META[it.kind] || KIND_META.other).label.replace(/s$/, "")}
      </span>
    </button>
  );
}

/* ---------- create / edit event modal ---------- */
function EventModal({ mode, initial, me, onClose, onSaved }) {
  const isEdit = mode === "edit";
  const [f, setF] = useState({
    title: initial?.title || "",
    kind: initial?.kind || "meeting",
    date: initial?.date || "",
    start_time: initial?.start_time || "",
    end_time: initial?.end_time || "",
    location: initial?.location || "",
    notes: initial?.notes || "",
  });
  const [busy, setBusy] = useState(false);
  const canDelete = isEdit && (initial?.created_by === me?.user_id || me?.role === "Admin" || me?.is_super_admin);

  const save = async (e) => {
    e.preventDefault();
    if (!f.title.trim() || !f.date) { toast.error("Title and date are required"); return; }
    setBusy(true);
    try {
      if (isEdit) {
        await api.patch(`/calendar/events/${initial.id}`, f);
        toast.success("Event updated");
      } else {
        await api.post("/calendar/events", f);
        toast.success("Event added to the calendar");
      }
      onSaved();
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Could not save the event");
    } finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete(`/calendar/events/${initial.id}`);
      toast.success("Event deleted");
      onSaved();
    } catch {
      toast.error("Could not delete this event");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <form onSubmit={save} className="relative bg-white border border-[#E5E5E5] w-full max-w-md p-6 space-y-4 shadow-xl"
            data-testid="event-modal">
        <div className="flex items-center justify-between">
          <div className="overline">{isEdit ? "EDIT EVENT" : "NEW EVENT"}</div>
          <button type="button" onClick={onClose} className="btn-ghost px-1" data-testid="event-modal-close"><X size={16} /></button>
        </div>

        <div className="flex gap-2">
          {[["meeting", "Meeting"], ["reminder", "Reminder"], ["other", "Other"]].map(([k, l]) => (
            <button type="button" key={k} onClick={() => setF({ ...f, kind: k })}
              className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${f.kind === k ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "border-[#E5E5E5] text-[#5C5C5C]"}`}
              data-testid={`event-kind-${k}`}>{l}</button>
          ))}
        </div>

        <input className="input-flat w-full" placeholder="Title — e.g. Client design review"
               value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })}
               data-testid="event-title-input" autoFocus />

        <div className="grid grid-cols-3 gap-2">
          <div className="col-span-1">
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Date</label>
            <input type="date" required className="input-flat w-full" value={f.date}
                   onChange={(e) => setF({ ...f, date: e.target.value })} data-testid="event-date-input" />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Start</label>
            <input type="time" className="input-flat w-full" value={f.start_time}
                   onChange={(e) => setF({ ...f, start_time: e.target.value })} data-testid="event-start-input" />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">End</label>
            <input type="time" className="input-flat w-full" value={f.end_time}
                   onChange={(e) => setF({ ...f, end_time: e.target.value })} />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <MapPin size={14} className="text-[#5C5C5C]" />
          <input className="input-flat flex-1" placeholder="Location (optional)"
                 value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })}
                 data-testid="event-location-input" />
        </div>

        <textarea className="input-flat w-full" rows={2} placeholder="Notes (optional)"
                  value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />

        <div className="flex items-center justify-between pt-1">
          {canDelete ? (
            <button type="button" onClick={remove} disabled={busy}
                    className="btn-ghost text-[#B4001C] text-xs" data-testid="event-delete-btn">
              <Trash size={13} /> Delete
            </button>
          ) : <span />}
          <button type="submit" disabled={busy} className="btn-primary" data-testid="event-save-btn">
            {busy ? "Saving…" : isEdit ? "Save changes" : "Add to calendar"}
          </button>
        </div>
      </form>
    </div>
  );
}
