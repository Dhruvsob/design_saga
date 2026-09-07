import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import { Plus, ArrowRight, CaretRight } from "@phosphor-icons/react";
import PageHero from "../components/PageHero";
import { formatINR, empName } from "../lib/format";

const FALLBACK_STAGES = ["Requirement", "Concept", "Design Dev", "Tech Drawings", "Review", "Signoff", "Procurement", "Execution", "Handover"];
const FALLBACK_TYPES = ["Residential", "Commercial"];

export default function Projects() {
  const { currentOrg } = useAuth();
  const { values } = useMasterData();
  const STAGES = values("project_stage", FALLBACK_STAGES);
  const TYPES = values("project_type", FALLBACK_TYPES);
  const businessMode = currentOrg?.business_mode || "hybrid";
  const isHybrid = businessMode === "hybrid";
  const defaultEng = businessMode === "consultancy" ? "consultancy"
                   : businessMode === "turnkey" ? "turnkey" : "consultancy";
  const [projects, setProjects] = useState([]);
  const [clients, setClients] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "", client_id: "", project_type: "Residential",
    engagement_type: defaultEng, budget: "", stage: "Requirement", description: "",
    project_manager_id: "", team_ids: [],
  });
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  const load = async () => {
    const [p, c, e] = await Promise.all([
      api.get("/projects"),
      api.get("/clients"),
      api.get("/employees").catch(() => ({ data: [] })),
    ]);
    setProjects(p.data);
    setClients(c.data);
    setEmployees(Array.isArray(e.data) ? e.data : e.data?.employees || []);
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { setForm((f) => ({ ...f, engagement_type: defaultEng })); }, [defaultEng]);

  const toggleTeam = (id) =>
    setForm((f) => ({
      ...f,
      team_ids: f.team_ids.includes(id) ? f.team_ids.filter((x) => x !== id) : [...f.team_ids, id],
    }));

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      await api.post("/projects", {
        ...form,
        budget: form.budget === "" ? 0 : Number(form.budget),
        project_manager_id: form.project_manager_id || undefined,
        team_ids: form.team_ids,
      });
      setShowForm(false);
      setForm({ name: "", client_id: "", project_type: "Residential",
                engagement_type: defaultEng, budget: "", stage: "Requirement", description: "",
                project_manager_id: "", team_ids: [] });
      load();
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(typeof d === "string" ? d : (d?.msg || "Create failed"));
    }
  };

  return (
    <div className="space-y-8" data-testid="projects-page">
      <PageHero
        eyebrow="STUDIO / PROJECTS"
        title="Active work."
        kicker="Track every brief from concept to handover. Click any tile to dive in."
        count={projects.length}
      >
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-project-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New project"}
        </button>
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-2 gap-4 scale-in" data-testid="project-form">
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
          {isHybrid && (
            <label className="md:col-span-2">
              <div className="overline text-[10px] mb-1">ENGAGEMENT TYPE *</div>
              <div className="grid grid-cols-2 gap-2">
                {[
                  {k:"consultancy", t:"Consultancy", d:"Design only — no procurement, invoicing on retainer/milestones."},
                  {k:"turnkey",     t:"Turnkey",     d:"End-to-end delivery — POs, GRN, material costs, full project P&L."},
                ].map((o) => (
                  <button type="button" key={o.k}
                    onClick={() => setForm({...form, engagement_type: o.k})}
                    className={`text-left p-3 border transition ${form.engagement_type === o.k ? "border-[#8B7F6A] bg-[#F5F4F0]" : "border-[#E5E5E5]"}`}
                    data-testid={`engagement-${o.k}`}>
                    <div className="font-display font-bold text-sm">{o.t}</div>
                    <div className="text-[10px] text-[#5C5C5C]">{o.d}</div>
                  </button>
                ))}
              </div>
            </label>
          )}
          <input className="input-flat" type="number" placeholder="Enter Budget (₹)" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} data-testid="project-budget" />
          <input className="input-flat" placeholder="Short description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

          {/* Project Team — controls who can see this project's tasks */}
          <div className="md:col-span-2 border-t border-[#EFEDE8] pt-3">
            <div className="overline text-[10px] mb-2">PROJECT TEAM</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[11px] text-[#5C5C5C] mb-1 block">Project Manager</span>
                <select className="input-flat w-full" value={form.project_manager_id}
                  onChange={(e) => setForm({ ...form, project_manager_id: e.target.value })}
                  data-testid="project-pm-select">
                  <option value="">— Select PM (optional) —</option>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {empName(emp)}{emp.designation ? ` · ${emp.designation}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <div className="block">
                <span className="text-[11px] text-[#5C5C5C] mb-1 block">Team members (can see project tasks)</span>
                <div className="border border-[#E5E5E5] rounded-md max-h-32 overflow-y-auto p-2 flex flex-wrap gap-1.5" data-testid="project-team-picker">
                  {employees.length === 0 && <span className="text-xs text-[#9A9A9A]">No employees yet.</span>}
                  {employees.map((emp) => {
                    const on = form.team_ids.includes(emp.id);
                    return (
                      <button type="button" key={emp.id} onClick={() => toggleTeam(emp.id)}
                        className={`px-2.5 py-1 text-xs rounded-full border transition ${on
                          ? "border-[#8B7F6A] bg-[#F5F4F0] text-[#8B7F6A] font-semibold"
                          : "border-[#E5E5E5] text-[#5C5C5C] hover:border-[#8B7F6A]"}`}
                        data-testid={`team-opt-${emp.id}`}>
                        {empName(emp)}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
          {err && <div className="md:col-span-2 border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
          <button className="btn-primary md:col-span-2" data-testid="project-submit" type="submit">Create project</button>
        </form>
      )}

      <div className="border-t border-l border-[#E5E5E5] grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 stagger">
        {projects.map((p, i) => {
          const idx = STAGES.indexOf(p.stage || "Requirement");
          const pct = Math.round(((idx + 1) / STAGES.length) * 100);
          return (
            <button
              key={p.id}
              onClick={() => navigate(`/projects/${p.id}`)}
              className="fade-up text-left border-r border-b border-[#E5E5E5] p-6 hover:bg-[#FAFAFA] transition group relative"
              data-testid={`project-card-${p.id}`}
            >
              {/* index number */}
              <div className="absolute top-4 right-4 font-mono text-[10px] text-[#9A9A9A] tracking-widest">
                #{String(i + 1).padStart(3, "0")}
              </div>

              <div className="overline mb-2">
                {p.project_type}
                {p.engagement_type && (
                  <span className={`ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 ${
                    p.engagement_type === "consultancy" ? "bg-[#F5F4F0] text-[#8B7F6A]" : "bg-[#FFF4E5] text-[#7A4E1A]"
                  }`}>{p.engagement_type}</span>
                )}
              </div>
              <div className="font-display font-bold tracking-tighter text-2xl mb-1 leading-tight group-hover:accent-blue transition-colors">
                {p.name}
              </div>
              <div className="text-sm text-[#5C5C5C] mb-5">{p.client_name || "Unassigned"}</div>

              <div className="flex items-center justify-between text-xs font-mono mb-2 tabular-nums">
                <span className="text-[#0A0A0A] font-semibold">{p.stage}</span>
                <span className="text-[#5C5C5C]">{pct}%</span>
              </div>
              <div className="h-1 bg-[#F0F0F0] relative overflow-hidden">
                <div
                  className="h-1 bg-[#8B7F6A] transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="mt-5 flex items-center justify-between">
                <div className="font-mono text-sm font-semibold tabular-nums">{formatINR(p.budget)}</div>
                <div className="overline flex items-center gap-1 group-hover:text-[#8B7F6A] transition-colors">
                  OPEN <CaretRight size={10} weight="bold" className="transition-transform group-hover:translate-x-0.5" />
                </div>
              </div>
            </button>
          );
        })}
        {projects.length === 0 && (
          <EmptyState />
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="border-r border-b border-[#E5E5E5] p-12 col-span-full text-center">
      <div className="inline-block mb-4 dotted-bg" style={{ width: 80, height: 80 }} />
      <div className="overline mb-2">NO PROJECTS YET</div>
      <p className="text-[#5C5C5C] text-sm max-w-sm mx-auto">
        Create a project from scratch or convert a lead from the CRM. You can also seed demo data from the dashboard.
      </p>
    </div>
  );
}
