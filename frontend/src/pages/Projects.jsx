import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import { Plus, ArrowRight, CaretRight } from "@phosphor-icons/react";
import PageHero from "../components/PageHero";

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
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "", client_id: "", project_type: "Residential",
    engagement_type: defaultEng, budget: 0, stage: "Requirement", description: "",
  });
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  const load = async () => {
    const [p, c] = await Promise.all([api.get("/projects"), api.get("/clients")]);
    setProjects(p.data);
    setClients(c.data);
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { setForm((f) => ({ ...f, engagement_type: defaultEng })); }, [defaultEng]);

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      await api.post("/projects", { ...form, budget: Number(form.budget || 0) });
      setShowForm(false);
      setForm({ name: "", client_id: "", project_type: "Residential",
                engagement_type: defaultEng, budget: 0, stage: "Requirement", description: "" });
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
          <input className="input-flat" type="number" placeholder="Budget" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
          <input className="input-flat" placeholder="Short description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
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
                <div className="font-mono text-sm font-semibold tabular-nums">₹{(p.budget || 0).toLocaleString("en-IN")}</div>
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
