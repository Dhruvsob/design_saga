import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import {
  Plus, X, Trash, DotsSixVertical, MagnifyingGlass, ListChecks,
  Table as TableIcon, SquaresFour, Warning, Bell, DownloadSimple,
} from "@phosphor-icons/react";

const LANES = [
  { id: "todo", label: "To do", color: "#5C5C5C" },
  { id: "in_progress", label: "In progress", color: "#002FA7" },
  { id: "review", label: "Review", color: "#FF8C00" },
  { id: "done", label: "Done", color: "#1D633E" },
];

const PRIORITY_COLORS = {
  low: "#5C5C5C", medium: "#0A0A0A", high: "#FF8C00",
  urgent: "#FF2A00", critical: "#B4001C",
};

const STATUS_COLORS = {
  "Pending": "#5C5C5C", "Selection Required": "#8A6DFF",
  "Reference Required": "#FF8C00", "Vendor Required": "#FF8C00",
  "Quotation Requested": "#F0A93A", "Quotation Received": "#3B82F6",
  "Ordered": "#0EA5E9", "Work Started": "#0891B2", "In Progress": "#002FA7",
  "On Hold": "#F59E0B", "Inspection Pending": "#EAB308",
  "Completed": "#1D633E", "Cancelled": "#B4001C",
};

const EMPTY_TASK = {
  title: "", description: "", project_id: "", task_type: "employee",
  area: "", category: "", item_description: "", quantity: "",
  priority: "medium", status_detail: "Pending",
  remarks: "", assignee_name: "", due_date: "",
  vendor_contact: { vendor_name: "", contact_person: "", phone: "", email: "", whatsapp: "" },
};

export default function TasksBoard() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [meta, setMeta] = useState(null);
  const [view, setView] = useState("kanban");   // kanban | table
  const [taskType, setTaskType] = useState("all");  // all | employee | vendor
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState({ project_id: "", area: "", category: "", priority: "", status_detail: "" });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_TASK);
  const [selected, setSelected] = useState(new Set());
  const [dragId, setDragId] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  const loadAll = async () => {
    const [t, p, m, v] = await Promise.all([
      api.get("/tasks"),
      api.get("/projects"),
      api.get("/tasks/meta"),
      api.get("/vendors").catch(() => ({ data: [] })),
    ]);
    setTasks(t.data);
    setProjects(p.data);
    setMeta(m.data);
    setVendors(v.data);
  };
  useEffect(() => { loadAll(); }, []);

  const filtered = useMemo(() => {
    let rows = tasks;
    if (taskType !== "all") rows = rows.filter((t) => (t.task_type || "employee") === taskType);
    if (filters.project_id) rows = rows.filter((t) => t.project_id === filters.project_id);
    if (filters.area) rows = rows.filter((t) => t.area === filters.area);
    if (filters.category) rows = rows.filter((t) => t.category === filters.category);
    if (filters.priority) rows = rows.filter((t) => t.priority === filters.priority);
    if (filters.status_detail) rows = rows.filter((t) => t.status_detail === filters.status_detail);
    if (q) {
      const s = q.toLowerCase();
      rows = rows.filter((t) =>
        [t.title, t.item_description, t.remarks, t.vendor_contact?.vendor_name, t.category, t.area]
          .filter(Boolean).some((v) => v.toLowerCase().includes(s))
      );
    }
    return rows;
  }, [tasks, taskType, filters, q]);

  const drop = async (lane) => {
    if (!dragId) return;
    await api.patch(`/tasks/${dragId}/status`, { status: lane });
    setDragId(null); setDragOver(null);
    loadAll();
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
    if (!window.confirm("Delete this task?")) return;
    await api.delete(`/tasks/${id}`);
    loadAll();
  };

  const bulkStatus = async (status_detail) => {
    if (!selected.size) return;
    await api.post("/tasks/bulk-update", { task_ids: [...selected], status_detail });
    setSelected(new Set());
    loadAll();
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

  const today = new Date().toISOString().slice(0, 10);
  const overdueCount = filtered.filter((t) => t.due_date && t.due_date < today && t.status !== "done").length;
  const areas = meta?.areas || [];
  const categories = taskType === "vendor" ? (meta?.categories_vendor || meta?.categories || [])
    : taskType === "employee" ? (meta?.categories_employee || meta?.categories || [])
    : (meta?.categories || []);

  return (
    <div className="space-y-6" data-testid="tasks-page">
      <PageHero
        eyebrow={`WORK / TASKS${overdueCount ? `  ·  ${overdueCount} OVERDUE` : ""}`}
        title="Ship without chaos."
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
      <div className="flex items-center gap-1 border-b border-[#E5E5E5]" data-testid="task-type-tabs">
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
              ? "border-[#002FA7] text-[#002FA7] font-semibold"
              : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"}`}
          >
            {t.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1 pb-2">
          <button onClick={() => setView("kanban")} data-testid="view-kanban-btn"
            className={`btn-icon ${view === "kanban" ? "bg-[#0A0A0A] text-white" : ""}`} aria-label="Kanban view">
            <SquaresFour size={16} />
          </button>
          <button onClick={() => setView("table")} data-testid="view-table-btn"
            className={`btn-icon ${view === "table" ? "bg-[#0A0A0A] text-white" : ""}`} aria-label="Table view">
            <TableIcon size={16} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2" data-testid="task-filters">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9A9A9A]" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, item, vendor…"
            className="input-flat pl-9 w-72" data-testid="task-search" />
        </div>
        <select className="input-flat" value={filters.project_id} onChange={(e) => setFilters({ ...filters, project_id: e.target.value })} data-testid="filter-project">
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select className="input-flat" value={filters.area} onChange={(e) => setFilters({ ...filters, area: e.target.value })} data-testid="filter-area">
          <option value="">All areas</option>
          {areas.map((a) => <option key={a}>{a}</option>)}
        </select>
        <select className="input-flat" value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })} data-testid="filter-category">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select className="input-flat" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })} data-testid="filter-priority">
          <option value="">All priorities</option>
          {(meta?.priorities || []).map((p) => <option key={p}>{p}</option>)}
        </select>
        <select className="input-flat" value={filters.status_detail} onChange={(e) => setFilters({ ...filters, status_detail: e.target.value })} data-testid="filter-status">
          <option value="">All statuses</option>
          {(meta?.status_detail || []).map((s) => <option key={s}>{s}</option>)}
        </select>
        {(q || Object.values(filters).some(Boolean)) && (
          <button onClick={() => { setQ(""); setFilters({ project_id: "", area: "", category: "", priority: "", status_detail: "" }); }}
            className="btn-ghost text-xs" data-testid="clear-filters">
            <X size={12} /> Clear
          </button>
        )}
      </div>

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 border border-[#0A0A0A] bg-[#0A0A0A] text-white px-4 py-2 text-sm scale-in" data-testid="bulk-bar">
          <ListChecks size={16} />
          <span className="font-mono">{selected.size} SELECTED</span>
          <select onChange={(e) => bulkStatus(e.target.value)} defaultValue="" className="bg-transparent border border-white/30 px-2 py-1 text-xs" data-testid="bulk-status">
            <option value="" disabled>Set status…</option>
            {(meta?.status_detail || []).map((s) => <option key={s} className="text-black">{s}</option>)}
          </select>
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs opacity-70 hover:opacity-100">Clear</button>
        </div>
      )}

      {/* Inline create form */}
      {showForm && (
        <TaskForm
          form={form} setForm={setForm} onSubmit={submit}
          projects={projects} vendors={vendors} meta={meta} areas={areas} categories={categories}
        />
      )}

      {/* Views */}
      {view === "kanban" ? (
        <KanbanView
          tasks={filtered} onDelete={del}
          onDragStart={setDragId} onDrop={drop}
          dragOver={dragOver} setDragOver={setDragOver}
          onOpen={(id) => navigate(`/tasks/${id}`)}
        />
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
// Kanban view
// ================================================================
function KanbanView({ tasks, onDelete, onDragStart, onDrop, dragOver, setDragOver, onOpen }) {
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 border-t border-l border-[#E5E5E5] stagger" data-testid="kanban-board">
      {LANES.map((c) => {
        const items = tasks.filter((t) => t.status === c.id);
        const isOver = dragOver === c.id;
        return (
          <div
            key={c.id}
            className={`fade-up border-r border-b border-[#E5E5E5] min-h-[500px] flex flex-col transition-all ${isOver ? "bg-[#F0F3FB]" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(c.id); }}
            onDragLeave={() => setDragOver(null)}
            onDrop={() => onDrop(c.id)}
            data-testid={`col-${c.id}`}
          >
            <div className="p-3 border-b border-[#E5E5E5] bg-[#FAFAFA] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: c.color }} />
                <div className="overline">{c.label}</div>
              </div>
              <div className="font-mono text-xs font-semibold bg-white px-1.5 border border-[#E5E5E5]">{items.length}</div>
            </div>
            <div className="p-3 flex-1 space-y-3">
              {items.map((t) => {
                const overdue = t.due_date && t.due_date < today && t.status !== "done";
                const isVendor = t.task_type === "vendor";
                return (
                  <div
                    key={t.id}
                    draggable
                    onDragStart={() => onDragStart(t.id)}
                    onClick={() => onOpen(t.id)}
                    className={`border p-3 bg-white cursor-grab active:cursor-grabbing transition-all hover:-translate-y-0.5 group ${overdue ? "border-[#FF2A00]" : "border-[#E5E5E5] hover:border-[#0A0A0A]"}`}
                    data-testid={`task-${t.id}`}
                  >
                    <div className="flex items-center gap-2 mb-2 text-[10px] font-mono uppercase tracking-wider">
                      <span className="px-1.5 py-0.5 border" style={{ borderColor: isVendor ? "#8A6DFF" : "#002FA7", color: isVendor ? "#8A6DFF" : "#002FA7" }}>
                        {isVendor ? "AGENCY" : "TEAM"}
                      </span>
                      <span style={{ color: PRIORITY_COLORS[t.priority] || "#000" }}>{t.priority}</span>
                      {overdue && <span className="text-[#FF2A00] flex items-center gap-1"><Warning size={10} weight="fill" /> OVERDUE</span>}
                      <DotsSixVertical size={12} className="text-[#CCCCCC] ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <div className="font-semibold text-sm leading-snug">{t.title}</div>
                    <div className="flex items-center gap-2 mt-1.5 text-[11px] text-[#5C5C5C]">
                      {t.area && <span>{t.area}</span>}
                      {t.category && <span>· {t.category}</span>}
                    </div>
                    {t.project_name && <div className="text-xs text-[#5C5C5C] mt-1.5">{t.project_name}</div>}
                    {t.status_detail && (
                      <div className="mt-2">
                        <span className="text-[10px] font-mono px-1.5 py-0.5" style={{ background: `${STATUS_COLORS[t.status_detail] || "#000"}15`, color: STATUS_COLORS[t.status_detail] || "#000" }}>
                          {t.status_detail}
                        </span>
                      </div>
                    )}
                    {(t.follow_up_date || t.reminder_date) && (
                      <div className="flex items-center gap-1 text-[10px] font-mono text-[#8A6DFF] mt-2">
                        <Bell size={10} /> FOLLOW-UP {t.follow_up_date || t.reminder_date}
                      </div>
                    )}
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#F0F0F0]">
                      <div className="text-[10px] font-mono tracking-wider uppercase text-[#5C5C5C]">
                        {t.due_date ? `DUE ${t.due_date}` : "NO DUE"}
                      </div>
                      <button onClick={(e) => { e.stopPropagation(); onDelete(t.id); }}
                        className="text-[#FF2A00] hover:scale-110 transition" data-testid={`delete-${t.id}`}>
                        <Trash size={12} />
                      </button>
                    </div>
                  </div>
                );
              })}
              {items.length === 0 && <div className="text-center py-8 text-xs text-[#9A9A9A]">—</div>}
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
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="border border-[#E5E5E5] overflow-x-auto" data-testid="task-table">
      <table className="w-full text-sm">
        <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
          <tr className="text-left text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
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
              <tr key={t.id} className={`border-b border-[#F0F0F0] hover:bg-[#FAFAFA] ${overdue ? "bg-[#FFF2F0]" : ""}`}
                data-testid={`row-${t.id}`}>
                <td className="p-2">
                  <input type="checkbox" checked={selected.has(t.id)} onChange={(e) => toggleOne(t.id, e.target.checked)} />
                </td>
                <td className="p-2 font-mono text-xs text-[#9A9A9A]">{i + 1}</td>
                <td className="p-2">
                  <InlineSelect value={t.area || ""} options={areas} onChange={(v) => onInline(t.id, "area", v)} />
                </td>
                <td className="p-2">
                  <InlineSelect value={t.category || ""} options={categories} onChange={(v) => onInline(t.id, "category", v)} />
                </td>
                <td className="p-2">
                  <button onClick={() => onOpen(t.id)} className="text-left font-semibold hover:text-[#002FA7]" data-testid={`open-${t.id}`}>
                    {t.title}
                  </button>
                  {t.item_description && <div className="text-xs text-[#5C5C5C]">{t.item_description}</div>}
                </td>
                <td className="p-2">
                  <InlineNumber value={t.quantity} onChange={(v) => onInline(t.id, "quantity", v)} />
                </td>
                <td className="p-2">
                  <InlineSelect value={t.status_detail || ""} options={meta?.status_detail || []}
                    onChange={(v) => onInline(t.id, "status_detail", v)}
                    style={{ color: STATUS_COLORS[t.status_detail] || "#000", fontWeight: 600 }} />
                </td>
                <td className="p-2">
                  <InlineSelect value={t.priority || "medium"} options={meta?.priorities || []}
                    onChange={(v) => onInline(t.id, "priority", v)}
                    style={{ color: PRIORITY_COLORS[t.priority] || "#000", fontWeight: 600 }} />
                </td>
                <td className="p-2 text-xs">
                  {t.task_type === "vendor" ? (t.vendor_contact?.vendor_name || "—") : (t.assignee_name || "—")}
                </td>
                <td className="p-2 text-xs">
                  {t.task_type === "vendor" ? (t.vendor_contact?.phone || "—") : "—"}
                </td>
                <td className="p-2 text-xs font-mono">{t.follow_up_date || t.reminder_date || "—"}</td>
                <td className={`p-2 text-xs font-mono ${overdue ? "text-[#FF2A00] font-semibold" : ""}`}>{t.due_date || "—"}</td>
                <td className="p-2 text-xs text-[#5C5C5C] max-w-[200px] truncate" title={t.remarks || ""}>{t.remarks || "—"}</td>
                <td className="p-2">
                  <button onClick={() => onDelete(t.id)} className="text-[#FF2A00] hover:scale-110" data-testid={`row-del-${t.id}`}>
                    <Trash size={12} />
                  </button>
                </td>
              </tr>
            );
          })}
          {tasks.length === 0 && (
            <tr><td colSpan={14} className="p-8 text-center text-sm text-[#9A9A9A]">No tasks match your filters.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function InlineSelect({ value, options, onChange, style }) {
  return (
    <select
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
function TaskForm({ form, setForm, onSubmit, projects, vendors, meta, areas, categories }) {
  const set = (k, v) => setForm({ ...form, [k]: v });
  const setVendor = (k, v) => setForm({ ...form, vendor_contact: { ...(form.vendor_contact || {}), [k]: v } });
  const isVendor = form.task_type === "vendor";

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
      <div className="flex items-center gap-2 border-b border-[#E5E5E5] pb-3">
        {["employee", "vendor"].map((tt) => (
          <button
            key={tt} type="button" onClick={() => set("task_type", tt)}
            data-testid={`form-tt-${tt}`}
            className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${form.task_type === tt
              ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "border-[#E5E5E5] text-[#5C5C5C] hover:border-[#0A0A0A]"}`}
          >
            {tt === "employee" ? "Employee Task" : "Agency / Vendor Task"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input required className="input-flat md:col-span-2" placeholder="Task title" value={form.title}
          onChange={(e) => set("title", e.target.value)} data-testid="task-title" />
        <select className="input-flat" value={form.project_id} onChange={(e) => set("project_id", e.target.value)}>
          <option value="">— No project —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <select className="input-flat" value={form.area} onChange={(e) => set("area", e.target.value)}>
          <option value="">Area</option>
          {areas.map((a) => <option key={a}>{a}</option>)}
        </select>
        <select className="input-flat" value={form.category} onChange={(e) => set("category", e.target.value)}>
          <option value="">Category</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input className="input-flat" placeholder="Item description" value={form.item_description}
          onChange={(e) => set("item_description", e.target.value)} />

        <input className="input-flat" placeholder="Quantity" type="number" value={form.quantity}
          onChange={(e) => set("quantity", e.target.value)} />
        <select className="input-flat" value={form.status_detail}
          onChange={(e) => set("status_detail", e.target.value)}>
          {(meta?.status_detail || []).map((s) => <option key={s}>{s}</option>)}
        </select>
        <select className="input-flat" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
          {(meta?.priorities || []).map((p) => <option key={p}>{p}</option>)}
        </select>

        <input type="date" className="input-flat" value={form.due_date}
          onChange={(e) => set("due_date", e.target.value)} placeholder="Due" />
        {isVendor ? (
          <>
            <select
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
            </select>
            <input className="input-flat" placeholder="Or type ad-hoc vendor name"
              value={form.vendor_contact?.vendor_name || ""}
              onChange={(e) => setVendor("vendor_name", e.target.value)} />
          </>
        ) : (
          <>
            <input className="input-flat" placeholder="Assignee (employee name)"
              value={form.assignee_name} onChange={(e) => set("assignee_name", e.target.value)} />
            <input className="input-flat" placeholder="Remarks / brief"
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
