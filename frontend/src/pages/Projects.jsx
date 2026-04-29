import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { Plus } from "@phosphor-icons/react";

const STAGES = ["Requirement", "Concept", "Design Dev", "Tech Drawings", "Review", "Signoff", "Procurement", "Execution", "Handover"];
const TYPES = ["Residential", "Commercial"];

export default function Projects() {
  const [projects, setProjects] = useState([]);
  const [clients, setClients] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", client_id: "", project_type: "Residential", budget: 0, stage: "Requirement", description: "" });
  const navigate = useNavigate();

  const load = async () => {
    const [p, c] = await Promise.all([api.get("/projects"), api.get("/clients")]);
    setProjects(p.data);
    setClients(c.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/projects", { ...form, budget: Number(form.budget || 0) });
    setShowForm(false);
    setForm({ name: "", client_id: "", project_type: "Residential", budget: 0, stage: "Requirement", description: "" });
    load();
  };

  return (
    <div className="space-y-6" data-testid="projects-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline mb-1">STUDIO / PROJECTS</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">Active work.</h1>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-project-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New project"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="project-form">
          <input className="input-flat" placeholder="Project name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="project-name" />
          <select className="input-flat" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
            <option value="">Select client (optional)</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="input-flat" value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
            {TYPES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="input-flat" value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>
            {STAGES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <input className="input-flat" type="number" placeholder="Budget" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
          <input className="input-flat" placeholder="Short description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <button className="btn-primary md:col-span-2" data-testid="project-submit" type="submit">Create project</button>
        </form>
      )}

      <div className="border-t border-l border-[#E5E5E5] grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
        {projects.map((p) => {
          const idx = STAGES.indexOf(p.stage || "Requirement");
          const pct = Math.round(((idx + 1) / STAGES.length) * 100);
          return (
            <button
              key={p.id}
              onClick={() => navigate(`/projects/${p.id}`)}
              className="text-left border-r border-b border-[#E5E5E5] p-6 hover:bg-[#FAFAFA] transition"
              data-testid={`project-card-${p.id}`}
            >
              <div className="overline mb-2">{p.project_type}</div>
              <div className="font-display font-bold tracking-tight text-xl mb-1">{p.name}</div>
              <div className="text-sm text-[#5C5C5C] mb-4">{p.client_name || "Unassigned"}</div>

              <div className="flex items-center justify-between text-xs font-mono mb-2">
                <span>{p.stage}</span>
                <span>{pct}%</span>
              </div>
              <div className="h-1 bg-[#F0F0F0]">
                <div className="h-1 bg-[#002FA7]" style={{ width: `${pct}%` }} />
              </div>

              <div className="mt-4 flex items-center justify-between">
                <div className="font-mono text-sm font-semibold">₹{(p.budget || 0).toLocaleString("en-IN")}</div>
                <div className="overline">VIEW →</div>
              </div>
            </button>
          );
        })}
        {projects.length === 0 && (
          <div className="border-r border-b border-[#E5E5E5] p-8 col-span-full">
            <p className="text-[#5C5C5C]">No projects yet. Create one or seed demo data from the dashboard.</p>
          </div>
        )}
      </div>
    </div>
  );
}
