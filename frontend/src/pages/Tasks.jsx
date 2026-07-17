import { useEffect, useState } from "react";
import api from "../lib/api";
import { Plus, Trash, DotsSixVertical } from "@phosphor-icons/react";
import PageHero from "../components/PageHero";

const COLS = [
  { id: "todo", label: "To do", color: "#5C5C5C" },
  { id: "in_progress", label: "In progress", color: "#002FA7" },
  { id: "review", label: "Review", color: "#FF8C00" },
  { id: "done", label: "Done", color: "#1D633E" },
];
const PRIORITIES = ["low", "medium", "high"];

export default function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [dragId, setDragId] = useState(null);
  const [dragOver, setDragOver] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", project_id: "", priority: "medium", status: "todo", due_date: "" });

  const load = async () => {
    const [t, p] = await Promise.all([api.get("/tasks"), api.get("/projects")]);
    setTasks(t.data);
    setProjects(p.data);
  };
  useEffect(() => { load(); }, []);

  const drop = async (status) => {
    if (!dragId) return;
    await api.patch(`/tasks/${dragId}/status`, { status });
    setDragId(null);
    setDragOver(null);
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Delete this task?")) return;
    await api.delete(`/tasks/${id}`);
    load();
  };

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/tasks", form);
    setForm({ title: "", project_id: "", priority: "medium", status: "todo", due_date: "" });
    setShowForm(false);
    load();
  };

  const today = new Date().toISOString().slice(0, 10);
  const overdueCount = tasks.filter((t) => t.due_date && t.due_date < today && t.status !== "done").length;

  return (
    <div className="space-y-8" data-testid="tasks-page">
      <PageHero
        eyebrow={`WORK / TASKS${overdueCount > 0 ? `  ·  ${overdueCount} OVERDUE` : ""}`}
        title="Ship without chaos."
        kicker="Tasks live close to projects. Drag between columns to update status."
        count={tasks.length}
      >
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-task-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New task"}
        </button>
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3 scale-in" data-testid="task-form">
          <input required className="input-flat md:col-span-2" placeholder="Task title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="task-title" />
          <select className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
            <option value="">— No project —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select className="input-flat" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
          </select>
          <input type="date" className="input-flat" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          <button className="btn-primary" data-testid="task-submit">Create task</button>
        </form>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 border-t border-l border-[#E5E5E5] stagger">
        {COLS.map((c) => {
          const items = tasks.filter((t) => t.status === c.id);
          const isOver = dragOver === c.id;
          return (
            <div
              key={c.id}
              className={`fade-up border-r border-b border-[#E5E5E5] min-h-[500px] flex flex-col transition-all ${isOver ? "bg-[#F0F3FB]" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(c.id); }}
              onDragLeave={() => setDragOver(null)}
              onDrop={() => drop(c.id)}
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
                  return (
                    <div
                      key={t.id}
                      draggable
                      onDragStart={() => setDragId(t.id)}
                      className={`border p-3 bg-white cursor-grab active:cursor-grabbing transition-all hover:-translate-y-0.5 group ${overdue ? "border-[#FF2A00]" : "border-[#E5E5E5] hover:border-[#0A0A0A]"}`}
                      data-testid={`task-${t.id}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`status-chip chip-${t.priority} no-dot`}>{t.priority}</span>
                        {overdue && <span className="status-chip chip-overdue">Overdue</span>}
                        <DotsSixVertical size={14} className="text-[#CCCCCC] ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <div className="font-semibold text-sm leading-snug">{t.title}</div>
                      {t.project_name && <div className="text-xs text-[#5C5C5C] mt-1.5">{t.project_name}</div>}
                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#F0F0F0]">
                        <div className="text-[10px] font-mono tracking-wider uppercase text-[#5C5C5C]">
                          {t.due_date ? `DUE ${t.due_date}` : "NO DUE"}
                        </div>
                        <button onClick={() => del(t.id)} className="text-[#FF2A00] hover:scale-110 transition"><Trash size={12} /></button>
                      </div>
                    </div>
                  );
                })}
                {items.length === 0 && (
                  <div className="text-center py-8 text-xs text-[#9A9A9A]">—</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
