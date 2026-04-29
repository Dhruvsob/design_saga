import { useEffect, useState } from "react";
import api from "../lib/api";
import { Plus, Trash } from "@phosphor-icons/react";

const COLS = [
  { id: "todo", label: "To do" },
  { id: "in_progress", label: "In progress" },
  { id: "review", label: "Review" },
  { id: "done", label: "Done" },
];
const PRIORITIES = ["low", "medium", "high"];

export default function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [dragId, setDragId] = useState(null);
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

  return (
    <div className="space-y-6" data-testid="tasks-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline mb-1">WORK / TASKS</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">Ship without chaos.</h1>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-task-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New task"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="task-form">
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

      <div className="grid grid-cols-1 md:grid-cols-4 border-t border-l border-[#E5E5E5]">
        {COLS.map((c) => {
          const items = tasks.filter((t) => t.status === c.id);
          return (
            <div
              key={c.id}
              className="border-r border-b border-[#E5E5E5] min-h-[400px] flex flex-col"
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => drop(c.id)}
              data-testid={`col-${c.id}`}
            >
              <div className="p-3 border-b border-[#E5E5E5] bg-[#FAFAFA] flex items-center justify-between">
                <div className="overline">{c.label}</div>
                <div className="font-mono text-xs font-semibold">{items.length}</div>
              </div>
              <div className="p-3 flex-1 space-y-3">
                {items.map((t) => {
                  const overdue = t.due_date && t.due_date < today && t.status !== "done";
                  return (
                    <div
                      key={t.id}
                      draggable
                      onDragStart={() => setDragId(t.id)}
                      className={`border p-3 bg-white cursor-grab active:cursor-grabbing transition ${overdue ? "border-[#FF2A00]" : "border-[#E5E5E5] hover:border-[#0A0A0A]"}`}
                      data-testid={`task-${t.id}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`status-chip chip-${t.priority}`}>{t.priority}</span>
                        {overdue && <span className="status-chip chip-overdue">Overdue</span>}
                      </div>
                      <div className="font-semibold text-sm">{t.title}</div>
                      {t.project_name && <div className="text-xs text-[#5C5C5C] mt-1">{t.project_name}</div>}
                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#F0F0F0]">
                        <div className="text-[10px] font-mono tracking-wider uppercase text-[#5C5C5C]">
                          {t.due_date ? `DUE ${t.due_date}` : "NO DUE"}
                        </div>
                        <button onClick={() => del(t.id)} className="text-[#FF2A00]"><Trash size={12} /></button>
                      </div>
                    </div>
                  );
                })}
                {items.length === 0 && <div className="text-xs text-[#5C5C5C]">—</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
