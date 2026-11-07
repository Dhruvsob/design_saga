import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import { dateForInput, empName, formatDate } from "../lib/format";
import {
  Plus, X, Trash, DotsSixVertical, MagnifyingGlass, ListChecks,
  Table as TableIcon, SquaresFour, Warning, Bell, DownloadSimple,
  CheckSquare, Square, CalendarBlank,
} from "@phosphor-icons/react";
import TaskCalendar from "../components/TaskCalendar";
import SearchSelect from "../components/SearchSelect";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";

const LANES = [
  { id: "todo", label: "To do", color: "#5C5C5C" },
  { id: "in_progress", label: "In progress", color: "#8B7F6A" },
  { id: "review", label: "Review", color: "#B87500" },
  { id: "done", label: "Done", color: "#1D633E" },
];

const PRIORITY_COLORS = {
  low: "#5C5C5C", medium: "#0A0A0A", high: "#B87500",
  urgent: "#B22B22", critical: "#B22B22",
};

const STATUS_COLORS = {
  "Pending": "#5C5C5C", "Selection Required": "#2B5299",
  "Reference Required": "#B87500", "Vendor Required": "#B87500",
  "Quotation Requested": "#B87500", "Quotation Received": "#2B5299",
  "Ordered": "#0EA5E9", "Work Started": "#0891B2", "In Progress": "#8B7F6A",
  "On Hold": "#F59E0B", "Inspection Pending": "#EAB308",
  "Completed": "#1D633E", "Cancelled": "#B22B22",
};

const EMPTY_TASK = {
  title: "", description: "", project_id: "", task_type: "employee",
  area: "", category: "", item_description: "", quantity: "",
  priority: "medium", status_detail: "Pending",
  remarks: "", assignee_name: "", assignee_id: "", assignees: [], due_date: "",
  vendor_contact: { vendor_name: "", contact_person: "", phone: "", email: "", whatsapp: "" },
};

export default function TasksBoard() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [meta, setMeta] = useState(null);
  const [view, setView] = useState("kanban");   // kanban (Board) | table (List) | calendar
  const [groupBy, setGroupBy] = useState("status");  // status | category
  const [taskType, setTaskType] = useState("all");  // all | employee | vendor
  const [q, setQ] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [filters, setFilters] = useState({ project_id: "", area: "", category: "", priority: "", status_detail: "", assignee_id: "" });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_TASK);
  const [selected, setSelected] = useState(new Set());
  const [dragId, setDragId] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  const loadAll = async () => {
    const [t, p, m, v, e] = await Promise.all([
      api.get("/tasks"),
      api.get("/projects"),
      api.get("/tasks/meta"),
      api.get("/vendors").catch(() => ({ data: [] })),
      api.get("/employees").catch(() => ({ data: [] })),
    ]);
    setTasks(t.data);
    setProjects(p.data);
    setMeta(m.data);
    setVendors(v.data);
    setEmployees(Array.isArray(e.data) ? e.data : e.data?.employees || []);
  };
  useEffect(() => { loadAll(); }, []);

  const filtered = useMemo(() => {
    let rows = tasks;
    if (mineOnly) rows = rows.filter((t) => t.assigned_to_me);
    if (taskType !== "all") rows = rows.filter((t) => (t.task_type || "employee") === taskType);
    if (filters.project_id) rows = rows.filter((t) => t.project_id === filters.project_id);
    if (filters.area) rows = rows.filter((t) => t.area === filters.area);
    if (filters.category) rows = rows.filter((t) => t.category === filters.category);
    if (filters.priority) rows = rows.filter((t) => t.priority === filters.priority);
    if (filters.status_detail) rows = rows.filter((t) => t.status_detail === filters.status_detail);
    if (filters.assignee_id) rows = rows.filter((t) => t.assignee_id === filters.assignee_id
      || (t.assignees || []).some((a) => (a?.id || a?.employee_id || a) === filters.assignee_id));
    if (q) {
      const s = q.toLowerCase();
      rows = rows.filter((t) =>
        [t.title, t.item_description, t.remarks, t.vendor_contact?.vendor_name, t.category, t.area]
          .filter(Boolean).some((v) => v.toLowerCase().includes(s))
      );
    }
    return rows;
  }, [tasks, taskType, filters, q, mineOnly]);

  const drop = async (lane) => {
    if (!dragId) return;
    const id = dragId;
    setDragId(null); setDragOver(null);
    try {
      if (groupBy === "category") {
        if (!lane) { toast.message("Pick a category lane to categorise a task"); return; }
        await api.put(`/tasks/${id}`, { category: lane });
      } else {
        await api.patch(`/tasks/${id}/status`, { status: lane });
      }
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not move the task");
    }
    loadAll();
  };

  const quickAdd = async (lane, title) => {
    const payload = { title, task_type: "employee", priority: "medium", status_detail: "Pending",
                      project_id: filters.project_id || undefined };
    if (groupBy === "category" && lane) payload.category = lane;
    try {
      const { data } = await api.post("/tasks", payload);
      if (groupBy === "status" && lane && lane !== "todo" && data?.id) {
        await api.patch(`/tasks/${data.id}/status`, { status: lane });
      }
      toast.success("Task added");
      loadAll();
      return true;
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not add the task");
      return false;
    }
  };

  const reschedule = async (id, day) => {
    try {
      await api.put(`/tasks/${id}`, { due_date: day });
      toast.success(`Due date set to ${formatDate(day)}`);
      loadAll();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not change the due date");
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form, quantity: form.quantity === "" ? null : Number(form.quantity) };
    if (payload.task_type !== "vendor") delete payload.vendor_contact;
    await api.post("/tasks", payload);
    setForm(EMPTY_TASK); setShowForm(false);
    loadAll();
  };

  const del = async (id) => {
    if (!await confirmAction("Delete this task?")) return;
    await api.delete(`/tasks/${id}`);
    loadAll();
  };

  const bulkApply = async (patch) => {
    if (!selected.size) return;
    const clean = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== "" && v != null));
    if (!Object.keys(clean).length) {
      toast.error("Pick at least one change to apply");
      return;
    }
    try {
      await api.post("/tasks/bulk-update", { task_ids: [...selected], ...clean });
      toast.success(`Updated ${selected.size} task${selected.size > 1 ? "s" : ""}`);
      setSelected(new Set());
      loadAll();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Bulk update failed");
    }
  };

  const toggleSelect = (id) => {
    setSelected((cur) => {
      const n = new Set(cur);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const inlineUpdate = async (id, field, value) => {
    await api.put(`/tasks/${id}`, { [field]: value });
    loadAll();
  };

  const exportCSV = () => {
    const cols = ["area", "category", "title", "item_description", "quantity",
      "status_detail", "priority", "assignee_name", "vendor_contact.vendor_name",
      "due_date", "follow_up_date", "reminder_date", "remarks"];
    const rows = filtered.map((t) => cols.map((c) => {
      const v = c.includes(".")
        ? c.split(".").reduce((acc, k) => (acc || {})[k], t)
        : t[c];
      return `"${(v ?? "").toString().replace(/"/g, '""')}"`;
    }).join(","));
    const csv = [cols.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `tasks-${Date.now()}.csv`;
    link.click();
  };

  const today = dateForInput(new Date());
  const overdueCount = filtered.filter((t) => t.due_date && t.due_date < today && t.status !== "done").length;
  const areas = meta?.areas || [];
  const categories = taskType === "vendor" ? (meta?.categories_vendor || meta?.categories || [])
    : taskType === "employee" ? (meta?.categories_employee || meta?.categories || [])
    : (meta?.categories || []);

  return (
    <div className="space-y-6" data-testid="tasks-page">
      <PageHero
        eyebrow={`WORK / TASKS${overdueCount ? `  ·  ${overdueCount} OVERDUE` : ""}`}
        title="Tasks"
        kicker="Employee & Agency tasks, one board. Filter, follow-up, and audit — end-to-end."
        count={filtered.length}
      >
        <button onClick={exportCSV} className="btn-ghost" data-testid="export-csv-btn">
          <DownloadSimple size={14} /> Export CSV
        </button>
        <button onClick={() => setShowForm((s) => !s)} className="btn-primary" data-testid="new-task-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New task"}
        </button>
      </PageHero>

      {/* Task-type tabs */}
      <div className="flex flex-wrap items-center gap-1 border-b border-[var(--line)]" data-testid="task-type-tabs">
        {[
          { id: "all", label: "All" },
          { id: "employee", label: "Employee tasks" },
          { id: "vendor", label: "Agency / Vendor" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTaskType(t.id)}
            data-testid={`tab-${t.id}`}
            className={`px-4 py-2.5 text-sm border-b-2 -mb-px transition-all ${taskType === t.id
              ? "border-[var(--accent)] text-[var(--accent-strong)] font-semibold"
              : "border-transparent text-[var(--ink-2)] hover:text-[var(--ink)]"}`}
          >
            {t.label}
          </button>
        ))}
        <div className="w-full sm:w-auto sm:ml-auto flex flex-wrap items-center gap-2 pb-2">
          {view === "kanban" && (
            <select aria-label="Group board by" className="input-flat !w-auto !h-8 text-xs" value={groupBy}
                    onChange={(e) => setGroupBy(e.target.value)} data-testid="board-group-by">
              <option value="status">Group by status</option>
              <option value="category">Group by category</option>
            </select>
          )}
          <div className="flex rounded-lg border border-[var(--line)] bg-[var(--surface-2)] p-0.5" role="tablist" aria-label="Work board view">
            {[["kanban", "Board", SquaresFour], ["table", "List", TableIcon], ["calendar", "Calendar", CalendarBlank]].map(([v, label, Icon]) => (
              <button key={v} type="button" role="tab" aria-selected={view === v} onClick={() => setView(v)}
                      data-testid={`view-${v === "kanban" ? "kanban" : v === "table" ? "table" : "calendar"}-btn`}
                      className={`flex items-center gap-1.5 px-3 h-8 rounded-md text-xs font-semibold transition-colors ${view === v
                        ? "bg-white text-[var(--ink)] shadow-[0_1px_2px_rgba(17,17,17,0.06)]" : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2" data-testid="task-filters">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, item, vendor…"
            className="input-flat pl-9 !w-72" data-testid="task-search" />
        </div>
        <SearchSelect className="input-flat !w-auto min-w-[150px]" value={filters.project_id} onChange={(e) => setFilters({ ...filters, project_id: e.target.value })} data-testid="filter-project">
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </SearchSelect>
        <select aria-label="Area" className="input-flat !w-auto min-w-[120px]" value={filters.area} onChange={(e) => setFilters({ ...filters, area: e.target.value })} data-testid="filter-area">
          <option value="">All areas</option>
          {areas.map((a) => <option key={a}>{a}</option>)}
        </select>
        <select aria-label="Category" className="input-flat !w-auto min-w-[130px]" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })} data-testid="filter-category">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select aria-label="Priority" className="input-flat !w-auto min-w-[120px]" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })} data-testid="filter-priority">
          <option value="">All priorities</option>
          {(meta?.priorities || []).map((p) => <option key={p}>{p}</option>)}
        </select>
        <select aria-label="Member" className="input-flat !w-auto min-w-[140px]" value={filters.assignee_id}
                onChange={(e) => setFilters({ ...filters, assignee_id: e.target.value })} data-testid="filter-member">
          <option value="">All members</option>
          {employees.map((e) => <option key={e.id} value={e.id}>{empName(e)}</option>)}
        </select>
        <select aria-label="Status" className="input-flat !w-auto min-w-[120px]" value={filters.status_detail} onChange={(e) => setFilters({ ...filters, status_detail: e.target.value })} data-testid="filter-status">
          <option value="">All statuses</option>
          {(meta?.status_detail || []).map((s) => <option key={s}>{s}</option>)}
        </select>
        {(q || Object.values(filters).some(Boolean)) && (
          <button onClick={() => { setQ(""); setFilters({ project_id: "", area: "", category: "", priority: "", status_detail: "" }); }}
            className="btn-ghost text-xs" data-testid="clear-filters">
            <X size={12} /> Clear
          </button>
        )}
        <button onClick={() => setMineOnly((v) => !v)}
          className={`text-xs px-3 py-2 rounded-md border transition ${mineOnly
            ? "border-[var(--info)] bg-[var(--info-soft)] text-[var(--info)] font-semibold"
            : "border-[var(--line)] text-[var(--ink-2)] hover:border-[var(--info)]"}`}
          data-testid="filter-assigned-to-me">
          Assigned to me
        </button>
      </div>

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <BulkBar
          count={selected.size}
          meta={meta}
          employees={employees}
          onApply={bulkApply}
          onClear={() => setSelected(new Set())}
        />
      )}

      {/* Inline create form */}
      {showForm && (
        <TaskForm
          form={form} setForm={setForm} onSubmit={submit}
          projects={projects} vendors={vendors} employees={employees} meta={meta} areas={areas} categories={categories}
        />
      )}

      {/* Views */}
      {view === "kanban" ? (
        <KanbanView
          tasks={filtered} onDelete={del}
          lanes={groupBy === "category"
            ? [...categories.map((c, i) => ({ id: c, label: c, color: ["#8B7F6A", "#2B5299", "#1D633E", "#B87500", "#76705E", "#B22B22"][i % 6] })),
               { id: "", label: "No category", color: "#C9C9C9" }]
            : LANES}
          laneOf={groupBy === "category" ? (t) => (categories.includes(t.category) ? t.category : "") : (t) => t.status}
          onQuickAdd={quickAdd}
          onDragStart={setDragId} onDrop={drop}
          dragOver={dragOver} setDragOver={setDragOver}
          onOpen={(id) => navigate(`/tasks/${id}`)}
          selected={selected} onToggleSelect={toggleSelect}
        />
      ) : view === "calendar" ? (
        <TaskCalendar tasks={filtered} onOpen={(id) => navigate(`/tasks/${id}`)} onReschedule={reschedule} />
      ) : (
        <TableView
          tasks={filtered} meta={meta} areas={areas} categories={categories}
          selected={selected} setSelected={setSelected}
          onInline={inlineUpdate} onOpen={(id) => navigate(`/tasks/${id}`)}
          onDelete={del}
        />
      )}
    </div>
  );
}

// ================================================================
// Bulk actions bar — status, assignee, due date, priority in one go
// ================================================================
function BulkBar({ count, meta, employees, onApply, onClear }) {
  const [patch, setPatch] = useState({ status_detail: "", priority: "", assignee_id: "", due_date: "" });

  const apply = () => {
    const emp = employees.find((e) => e.id === patch.assignee_id);
    onApply({
      status_detail: patch.status_detail,
      priority: patch.priority,
      assignee_id: patch.assignee_id,
      assignee_name: emp ? empName(emp) : "",
      due_date: patch.due_date,
    });
    setPatch({ status_detail: "", priority: "", assignee_id: "", due_date: "" });
  };

  return (
    <div className="border border-[var(--ink)] bg-[var(--ink)] text-white px-4 py-3 scale-in space-y-2" data-testid="bulk-bar">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <ListChecks size={16} />
        <span className="font-mono text-xs tracking-wider">{count} SELECTED</span>
        <select aria-label="Status" value={patch.status_detail} onChange={(e) => setPatch({ ...patch, status_detail: e.target.value })}
          className="bg-transparent border border-white/30 px-2 py-1.5 text-xs" data-testid="bulk-status">
          <option value="" className="text-black">Status — no change</option>
          {(meta?.status_detail || []).map((s) => <option key={s} className="text-black">{s}</option>)}
        </select>
        <select aria-label="Priority" value={patch.priority} onChange={(e) => setPatch({ ...patch, priority: e.target.value })}
          className="bg-transparent border border-white/30 px-2 py-1.5 text-xs" data-testid="bulk-priority">
          <option value="" className="text-black">Priority — no change</option>
          {(meta?.priorities || []).map((p) => <option key={p} className="text-black">{p}</option>)}
        </select>
        <select aria-label="Assignee" value={patch.assignee_id} onChange={(e) => setPatch({ ...patch, assignee_id: e.target.value })}
          className="bg-transparent border border-white/30 px-2 py-1.5 text-xs max-w-[200px]" data-testid="bulk-assignee">
          <option value="" className="text-black">Assignee — no change</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id} className="text-black">{empName(e)}{e.designation ? ` · ${e.designation}` : ""}</option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs">
          <span className="opacity-70 font-mono uppercase">Due</span>
          <input type="date" value={patch.due_date} onChange={(e) => setPatch({ ...patch, due_date: e.target.value })}
            className="bg-transparent border border-white/30 px-2 py-1 text-xs [color-scheme:dark]" data-testid="bulk-due-date" />
        </label>
        <button onClick={apply} className="bg-white text-[var(--ink)] px-4 py-1.5 text-xs font-semibold hover:bg-[var(--line-soft)] transition"
          data-testid="bulk-apply">
          Apply to {count}
        </button>
        <button onClick={onClear} className="ml-auto text-xs opacity-70 hover:opacity-100" data-testid="bulk-clear">
          <X size={12} className="inline mr-1" />Clear selection
        </button>
      </div>
    </div>
  );
}

// ================================================================
// Kanban view
// ================================================================
function KanbanView({ tasks, lanes = LANES, laneOf = (t) => t.status, onQuickAdd, onDelete, onDragStart, onDrop, dragOver, setDragOver, onOpen, selected, onToggleSelect }) {
  const today = dateForInput(new Date());
  const cols = lanes.length <= 4 ? "md:grid-cols-4" : "md:grid-flow-col md:auto-cols-[minmax(240px,1fr)] md:overflow-x-auto";
  return (
    <div className={`grid grid-cols-1 ${cols} border-t border-l border-[var(--line)] stagger`} data-testid="kanban-board">
      {lanes.map((c) => {
        const items = tasks.filter((t) => laneOf(t) === c.id);
        const isOver = dragOver === c.id;
        return (
          <div
            key={c.id}
            className={`fade-up relative border-r border-b border-[var(--line)] min-h-[500px] flex flex-col transition-all ${isOver ? "bg-[var(--hover)]" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(c.id); }}
            onDragLeave={() => setDragOver(null)}
            onDrop={() => onDrop(c.id)}
            data-testid={`col-${c.id}`}
          >
            <div className="p-3 border-b border-[var(--line)] bg-[var(--surface-2)] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: c.color }} />
                <div className="overline">{c.label}</div>
              </div>
              <div className="flex items-center gap-1">
                <div className="font-mono text-xs font-semibold bg-white px-1.5 border border-[var(--line)]">{items.length}</div>
                {onQuickAdd && <QuickAdd lane={c.id} label={c.label} onAdd={onQuickAdd} />}
              </div>
            </div>
            <div className="p-3 flex-1 space-y-3">
              {items.map((t) => {
                const overdue = t.due_date && t.due_date < today && t.status !== "done";
                const isVendor = t.task_type === "vendor";
                const isSel = selected?.has(t.id);
                return (
                  <div
                    key={t.id}
                    draggable
                    onDragStart={() => onDragStart(t.id)}
                    onClick={() => onOpen(t.id)}
                    className={`border p-3 bg-white cursor-grab active:cursor-grabbing transition-all hover:-translate-y-0.5 group ${
                      isSel ? "border-[var(--accent)] ring-1 ring-[var(--accent)]" :
                      overdue ? "border-[var(--danger)]" : "border-[var(--line)] hover:border-[var(--ink)]"}`}
                    data-testid={`task-${t.id}`}
                  >
                    <div className="flex items-center gap-2 mb-2 text-[10px] font-mono uppercase tracking-wider">
                      <button
                        onClick={(e) => { e.stopPropagation(); onToggleSelect(t.id); }}
                        title={isSel ? "Deselect" : "Select for bulk actions"}
                        className={`transition ${isSel ? "text-[var(--accent-strong)]" : "text-[var(--line-strong)] hover:text-[var(--ink)]"}`}
                        data-testid={`select-${t.id}`}
                      >
                        {isSel ? <CheckSquare size={14} weight="fill" /> : <Square size={14} />}
                      </button>
                      <span className="px-1.5 py-0.5 border" style={{ borderColor: isVendor ? "#2B5299" : "#8B7F6A", color: isVendor ? "#2B5299" : "#76705E" }}>
                        {isVendor ? "AGENCY" : "TEAM"}
                      </span>
                      <span style={{ color: PRIORITY_COLORS[t.priority] || "#000" }}>{t.priority}</span>
                      {overdue && <span className="text-[var(--danger)] flex items-center gap-1"><Warning size={10} weight="fill" /> OVERDUE</span>}
                      <DotsSixVertical size={12} className="text-[var(--line-strong)] ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <div className="font-semibold text-sm leading-snug">{t.title}</div>
                    {t.assigned_to_me && (
                      <div className="mt-1.5">
                        <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[var(--info-soft)] text-[var(--info)] border border-[#C7D7FE]" data-testid={`assigned-to-me-${t.id}`}>
                          Assigned to me
                        </span>
                      </div>
                    )}
                    <div className="flex items-center gap-2 mt-1.5 text-[11px] text-[var(--ink-2)]">
                      {t.area && <span>{t.area}</span>}
                      {t.category && <span>· {t.category}</span>}
                    </div>
                    {t.project_name && <div className="text-xs text-[var(--ink-2)] mt-1.5">{t.project_name}</div>}
                    {t.assigned_to_me && t.assigned_by_name && (
                      <div className="text-[10px] text-[var(--accent-strong)] mt-1">Assigned by {t.assigned_by_name}</div>
                    )}
                    {t.status_detail && (
                      <div className="mt-2">
                        <span className="text-[10px] font-mono px-1.5 py-0.5" style={{ background: `${STATUS_COLORS[t.status_detail] || "#000"}15`, color: STATUS_COLORS[t.status_detail] || "#000" }}>
                          {t.status_detail}
                        </span>
                      </div>
                    )}
                    {(t.follow_up_date || t.reminder_date) && (
                      <div className="flex items-center gap-1 text-[10px] font-mono text-[#8A6DFF] mt-2">
                        <Bell size={10} /> FOLLOW-UP {formatDate(t.follow_up_date || t.reminder_date)}
                      </div>
                    )}
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--line-soft)]">
                      <div className="text-[10px] font-mono tracking-wider uppercase text-[var(--ink-2)]">
                        {t.due_date ? `DUE ${formatDate(t.due_date)}` : "NO DUE"}
                        {(t.assignee_name || t.vendor_contact?.vendor_name) && (
                          <span className="ml-2 text-[var(--ink)]">· {t.task_type === "vendor" ? t.vendor_contact?.vendor_name : t.assignee_name}</span>
                        )}
                      </div>
                      <span onPointerDown={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
                        <RowActions label={t.title} testid={`task-actions-${t.id}`} actions={[
                          { label: "Delete task", icon: Trash, danger: true, onSelect: () => onDelete(t.id), testid: `delete-${t.id}` },
                        ]} />
                      </span>
                    </div>
                  </div>
                );
              })}
              {items.length === 0 && <div className="text-center py-8 text-xs text-[var(--ink-3)]">—</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ================================================================
// Excel-style Table view (inline edit)
// ================================================================
function TableView({ tasks, meta, areas, categories, selected, setSelected, onInline, onOpen, onDelete }) {
  const toggleAll = (checked) => setSelected(checked ? new Set(tasks.map((t) => t.id)) : new Set());
  const toggleOne = (id, checked) => {
    const n = new Set(selected);
    if (checked) n.add(id); else n.delete(id);
    setSelected(n);
  };
  const today = dateForInput(new Date());

  return (
    <div className="border border-[var(--line)] overflow-x-auto" data-testid="task-table">
      <table className="w-full text-sm">
        <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
          <tr className="text-left text-[10px] font-mono uppercase tracking-wider text-[var(--ink-2)]">
            <th className="p-2 w-8"><input type="checkbox" onChange={(e) => toggleAll(e.target.checked)} data-testid="tbl-select-all" /></th>
            <th className="p-2 w-8">#</th>
            <th className="p-2">Area</th>
            <th className="p-2">Category</th>
            <th className="p-2 min-w-[180px]">Item / Title</th>
            <th className="p-2 w-16">Qty</th>
            <th className="p-2">Status</th>
            <th className="p-2">Priority</th>
            <th className="p-2">Vendor / Assignee</th>
            <th className="p-2">Contact</th>
            <th className="p-2">Follow-up</th>
            <th className="p-2">Due</th>
            <th className="p-2">Remarks</th>
            <th className="p-2 w-8"></th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t, i) => {
            const overdue = t.due_date && t.due_date < today && t.status !== "done";
            return (
              <tr key={t.id} className={`border-b border-[var(--line-soft)] hover:bg-[var(--surface-2)] ${overdue ? "bg-[var(--danger-soft)]" : ""}`}
                data-testid={`row-${t.id}`}>
                <td className="p-2">
                  <input type="checkbox" checked={selected.has(t.id)} onChange={(e) => toggleOne(t.id, e.target.checked)} />
                </td>
                <td className="p-2 font-mono text-xs text-[var(--ink-3)]">{i + 1}</td>
                <td className="p-2">
                  <InlineSelect label="Area" value={t.area || ""} options={areas} onChange={(v) => onInline(t.id, "area", v)} />
                </td>
                <td className="p-2">
                  <InlineSelect label="Category" value={t.category || ""} options={categories} onChange={(v) => onInline(t.id, "category", v)} />
                </td>
                <td className="p-2">
                  <button onClick={() => onOpen(t.id)} className="text-left font-semibold hover:text-[var(--accent-strong)]" data-testid={`open-${t.id}`}>
                    {t.title}
                  </button>
                  {t.item_description && <div className="text-xs text-[var(--ink-2)]">{t.item_description}</div>}
                </td>
                <td className="p-2">
                  <InlineNumber value={t.quantity} onChange={(v) => onInline(t.id, "quantity", v)} />
                </td>
                <td className="p-2">
                  <InlineSelect label="Status" value={t.status_detail || ""} options={meta?.status_detail || []}
                    onChange={(v) => onInline(t.id, "status_detail", v)}
                    style={{ color: STATUS_COLORS[t.status_detail] || "#000", fontWeight: 600 }} />
                </td>
                <td className="p-2">
                  <InlineSelect label="Priority" value={t.priority || "medium"} options={meta?.priorities || []}
                    onChange={(v) => onInline(t.id, "priority", v)}
                    style={{ color: PRIORITY_COLORS[t.priority] || "#000", fontWeight: 600 }} />
                </td>
                <td className="p-2 text-xs">
                  {t.task_type === "vendor" ? (t.vendor_contact?.vendor_name || "—") : (t.assignee_name || "—")}
                </td>
                <td className="p-2 text-xs">
                  {t.task_type === "vendor" ? (t.vendor_contact?.phone || "—") : "—"}
                </td>
                <td className="p-2 text-xs font-mono">{formatDate(t.follow_up_date || t.reminder_date)}</td>
                <td className={`p-2 text-xs font-mono ${overdue ? "text-[var(--danger)] font-semibold" : ""}`}>{formatDate(t.due_date)}</td>
                <td className="p-2 text-xs text-[var(--ink-2)] max-w-[200px] truncate" title={t.remarks || ""}>{t.remarks || "—"}</td>
                <td className="p-2">
                  <RowActions label={t.title} testid={`task-row-actions-${t.id}`} actions={[
                    { label: "Delete task", icon: Trash, danger: true, onSelect: () => onDelete(t.id), testid: `row-del-${t.id}` },
                  ]} />
                </td>
              </tr>
            );
          })}
          {tasks.length === 0 && (
            <tr><td colSpan={14} className="p-8 text-center text-sm text-[var(--ink-3)]">No tasks match your filters.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function InlineSelect({ value, options, onChange, style, label }) {
  return (
    <select aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-transparent border-none outline-none text-xs w-full hover:bg-white focus:bg-white px-1 py-0.5"
      style={style}
    >
      <option value="">—</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function InlineNumber({ value, onChange }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  return (
    <input
      type="number" value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={() => { if (String(v) !== String(value ?? "")) onChange(v === "" ? null : Number(v)); }}
      className="bg-transparent border-none outline-none text-xs w-14 hover:bg-white focus:bg-white px-1 py-0.5"
    />
  );
}

// ================================================================
// New task form (with employee/vendor variants)
// ================================================================
function TaskForm({ form, setForm, onSubmit, projects, vendors, employees = [], meta, areas, categories }) {
  const set = (k, v) => setForm({ ...form, [k]: v });
  const setVendor = (k, v) => setForm({ ...form, vendor_contact: { ...(form.vendor_contact || {}), [k]: v } });
  const isVendor = form.task_type === "vendor";

  // Toggle an employee in the assignees list; keep primary assignee_id/name in
  // sync (first selected) so display + notifications keep working.
  const toggleAssignee = (empId) => {
    const cur = form.assignees || [];
    const next = cur.includes(empId) ? cur.filter((x) => x !== empId) : [...cur, empId];
    const primary = employees.find((e) => e.id === next[0]);
    setForm({
      ...form,
      assignees: next,
      assignee_id: next[0] || "",
      assignee_name: primary ? empName(primary) : "",
    });
  };

  // Pick vendor from master → auto-fill contact card so the task detail shows the right info,
  // and store vendor_id so the vendor's "assigned tasks" tab lights up automatically.
  const pickVendor = (vendorId) => {
    if (!vendorId) {
      setForm({ ...form, vendor_id: "", vendor_contact: { vendor_name: "", contact_person: "", phone: "", email: "", whatsapp: "", company_name: "" } });
      return;
    }
    const v = vendors.find((x) => x.id === vendorId);
    if (!v) return;
    setForm({
      ...form,
      vendor_id: v.id,
      vendor_contact: {
        vendor_name: v.name || "",
        company_name: v.company || "",
        contact_person: v.contact_person || "",
        phone: v.phone || "",
        email: v.email || "",
        whatsapp: form.vendor_contact?.whatsapp || "",
      },
    });
  };

  return (
    <form onSubmit={onSubmit} className="card-flat space-y-4 scale-in" data-testid="task-form">
      <div className="flex items-center gap-2 border-b border-[var(--line)] pb-3">
        {["employee", "vendor"].map((tt) => (
          <button
            key={tt} type="button" onClick={() => set("task_type", tt)}
            data-testid={`form-tt-${tt}`}
            className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${form.task_type === tt
              ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "border-[var(--line)] text-[var(--ink-2)] hover:border-[var(--ink)]"}`}
          >
            {tt === "employee" ? "Employee Task" : "Agency / Vendor Task"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input required className="input-flat md:col-span-2" placeholder="Task title" value={form.title}
          onChange={(e) => set("title", e.target.value)} data-testid="task-title" />
        <SearchSelect className="input-flat" value={form.project_id} onChange={(e) => set("project_id", e.target.value)}>
          <option value="">— No project —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </SearchSelect>

        <select aria-label="Area" className="input-flat" value={form.area} onChange={(e) => set("area", e.target.value)}>
          <option value="">Area</option>
          {areas.map((a) => <option key={a}>{a}</option>)}
        </select>
        <select aria-label="Category" className="input-flat" value={form.category} onChange={(e) => set("category", e.target.value)}>
          <option value="">Category</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input className="input-flat" placeholder="Item description" value={form.item_description}
          onChange={(e) => set("item_description", e.target.value)} />

        <input className="input-flat" placeholder="Quantity" type="number" value={form.quantity}
          onChange={(e) => set("quantity", e.target.value)} />
        <select aria-label="Status" className="input-flat" value={form.status_detail}
          onChange={(e) => set("status_detail", e.target.value)}>
          {(meta?.status_detail || []).map((s) => <option key={s}>{s}</option>)}
        </select>
        <select aria-label="Priority" className="input-flat" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
          {(meta?.priorities || []).map((p) => <option key={p}>{p}</option>)}
        </select>

        <input type="date" className="input-flat" value={form.due_date}
          onChange={(e) => set("due_date", e.target.value)} placeholder="Due" />
        {isVendor ? (
          <>
            <SearchSelect
              data-testid="task-vendor-picker"
              className="input-flat"
              value={form.vendor_id || ""}
              onChange={(e) => pickVendor(e.target.value)}
            >
              <option value="">— Pick from Vendor master —</option>
              {vendors.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}{v.company ? ` · ${v.company}` : ""}{v.agency_type ? ` · ${v.agency_type}` : ""}
                </option>
              ))}
            </SearchSelect>
            <input className="input-flat" placeholder="Or type ad-hoc vendor name"
              value={form.vendor_contact?.vendor_name || ""}
              onChange={(e) => setVendor("vendor_name", e.target.value)} />
          </>
        ) : (
          <>
            <div className="md:col-span-2">
              <div className="text-[11px] text-[var(--ink-2)] mb-1">Assign to employee(s) — they'll see it as "Assigned to me"</div>
              <div className="border border-[var(--line)] rounded-md max-h-28 overflow-y-auto p-2 flex flex-wrap gap-1.5" data-testid="task-assignee-picker">
                {employees.length === 0 && <span className="text-xs text-[var(--ink-3)]">No employees yet — type a name below.</span>}
                {employees.map((emp) => {
                  const on = (form.assignees || []).includes(emp.id);
                  return (
                    <button type="button" key={emp.id} onClick={() => toggleAssignee(emp.id)}
                      className={`px-2.5 py-1 text-xs rounded-full border transition ${on
                        ? "border-[var(--accent)] bg-[var(--hover)] text-[#5F5A4B] font-semibold"
                        : "border-[var(--line)] text-[var(--ink-2)] hover:border-[var(--accent)]"}`}
                      data-testid={`assignee-opt-${emp.id}`}>
                      {empName(emp)}
                    </button>
                  );
                })}
              </div>
            </div>
            <input className="input-flat md:col-span-2" placeholder="Remarks / brief"
              value={form.remarks} onChange={(e) => set("remarks", e.target.value)} />
          </>
        )}

        <textarea className="input-flat md:col-span-3" rows={2} placeholder="Description / scope"
          value={form.description} onChange={(e) => set("description", e.target.value)} />
      </div>

      <div className="flex items-center justify-end gap-3">
        <button className="btn-primary" data-testid="task-submit">Create task</button>
      </div>
    </form>
  );
}

// Quick task creation from a board lane: "+" opens a one-line input.
function QuickAdd({ lane, label, onAdd }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    const ok = await onAdd(lane, title.trim());
    setBusy(false);
    if (ok) { setTitle(""); setOpen(false); }
  };
  if (!open) {
    return (
      <button type="button" className="btn-icon !w-6 !h-6" onClick={() => setOpen(true)}
              aria-label={`Add a task to ${label}`} title={`Add a task to ${label}`} data-testid={`quick-add-${lane || "none"}`}>
        <Plus size={13} />
      </button>
    );
  }
  return (
    <form onSubmit={submit} className="absolute left-2 right-2 top-11 z-10 bg-white border border-[var(--line)] rounded-lg p-2 shadow-[var(--shadow-2)] scale-in">
      <input autoFocus className="input-flat !h-8 text-sm" placeholder="Task title, then Enter" value={title}
             onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
             aria-label="New task title" disabled={busy} data-testid={`quick-add-input-${lane || "none"}`} />
    </form>
  );
}
