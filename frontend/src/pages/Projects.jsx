import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import { Plus, ArrowRight, CaretRight, MagnifyingGlass, SquaresFour, ListBullets, PushPin, PencilSimple, Archive, X } from "@phosphor-icons/react";
import RowActions from "../components/RowActions";
import { confirmAction } from "../lib/confirm";
import { toast } from "sonner";
import PageHero from "../components/PageHero";
import { formatINR, empName } from "../lib/format";
import SearchSelect from "../components/SearchSelect";

const FALLBACK_STAGES = ["Requirement", "Concept", "Design Dev", "Tech Drawings", "Review", "Signoff", "Procurement", "Execution", "Handover"];
const FALLBACK_TYPES = ["Residential", "Commercial"];

export default function Projects() {
  const { currentOrg, hasPerm } = useAuth();
  const canCreate = hasPerm("projects.create");
  const canUpdate = hasPerm("projects.update");
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
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [view, setViewState] = useState(() => {
    try { return localStorage.getItem("ds_projects_view") || "grid"; } catch { return "grid"; }
  });
  const setView = (v) => {
    setViewState(v);
    try { localStorage.setItem("ds_projects_view", v); } catch { /* storage unavailable */ }
  };
  const navigate = useNavigate();
  const [pinned, setPinned] = useState(() => {
    try { return JSON.parse(localStorage.getItem("ds_projects_pinned") || "[]"); } catch { return []; }
  });
  const togglePin = (pid) => setPinned((cur) => {
    const next = cur.includes(pid) ? cur.filter((x) => x !== pid) : [pid, ...cur];
    try { localStorage.setItem("ds_projects_pinned", JSON.stringify(next)); } catch { /* storage unavailable */ }
    return next;
  });

  const load = async () => {
    const [p, c, e] = await Promise.all([
      api.get("/projects"),
      api.get("/clients"),
      api.get("/employees").catch(() => ({ data: [] })),
    ]);
    setProjects(p.data);
    setClients(c.data);
    setEmployees((Array.isArray(e.data) ? e.data : e.data?.employees || []).filter((x) => x.employment_status !== "terminated"));
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

  const term = query.trim().toLowerCase();
  const shown = projects
    .filter((p) => stageFilter === "all" || (p.stage || "Requirement") === stageFilter)
    .filter((p) => !term || `${p.name} ${p.client_name || ""} ${p.project_type || ""}`.toLowerCase().includes(term))
    .sort((a, b) => (sort === "name" ? (a.name || "").localeCompare(b.name || "")
      : sort === "stage" ? STAGES.indexOf(a.stage || "Requirement") - STAGES.indexOf(b.stage || "Requirement")
        : String(b.created_at || "").localeCompare(String(a.created_at || ""))))
    .sort((a, b) => Number(pinned.includes(b.id)) - Number(pinned.includes(a.id)));

  const archive = async (p) => {
    if (!await confirmAction(`Archive “${p.name}”? It will be hidden from active lists but all history is preserved.`)) return;
    try {
      await api.post(`/projects/${p.id}/archive`);
      toast.success("Project archived");
      load();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not archive");
    }
  };
  const menuFor = (p) => (
    <RowActions label={p.name} testid={`project-actions-${p.id}`} actions={[
      { label: "Open", icon: ArrowRight, onSelect: () => navigate(`/projects/${p.id}`) },
      { label: pinned.includes(p.id) ? "Unpin" : "Pin to top", icon: PushPin, onSelect: () => togglePin(p.id),
        testid: `project-pin-${p.id}` },
      { label: "Edit details", icon: PencilSimple, onSelect: () => navigate(`/projects/${p.id}?edit=1`), hidden: !canUpdate },
      { divider: true },
      { label: "Archive", icon: Archive, danger: true, onSelect: () => archive(p), hidden: !canUpdate,
        testid: `project-archive-${p.id}` },
    ]} />
  );

  return (
    <div className="space-y-8" data-testid="projects-page">
      <PageHero
        eyebrow="STUDIO / PROJECTS"
        title="Projects"
        kicker="Track every brief from concept to handover. Click any tile to dive in."
        count={projects.length}
      >
        {canCreate && <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-project-btn">
          {showForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> {"New project"}</>}
        </button>}
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-2 gap-4 scale-in" data-testid="project-form">
          <input className="input-flat" placeholder="Project name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="project-name" />
          <SearchSelect className="input-flat" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
            <option value="">Select client (optional)</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </SearchSelect>
          <select aria-label="Project type" className="input-flat" value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
            {TYPES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select aria-label="Stage" className="input-flat" value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>
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
                    className={`text-left p-3 border transition ${form.engagement_type === o.k ? "border-[var(--accent)] bg-[var(--hover)]" : "border-[var(--line)]"}`}
                    data-testid={`engagement-${o.k}`}>
                    <div className="font-display font-bold text-sm">{o.t}</div>
                    <div className="text-[10px] text-[var(--ink-2)]">{o.d}</div>
                  </button>
                ))}
              </div>
            </label>
          )}
          <input className="input-flat" type="number" min="0" placeholder="Enter Budget (₹)" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} data-testid="project-budget" />
          <input className="input-flat" placeholder="Short description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

          {/* Project Team — controls who can see this project's tasks */}
          <div className="md:col-span-2 border-t border-[var(--line-soft)] pt-3">
            <div className="overline text-[10px] mb-2">PROJECT TEAM</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Project Manager</span>
                <select aria-label="Project manager" className="input-flat w-full" value={form.project_manager_id}
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
                <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Team members (can see project tasks)</span>
                <div className="border border-[var(--line)] rounded-md max-h-32 overflow-y-auto p-2 flex flex-wrap gap-1.5" data-testid="project-team-picker">
                  {employees.length === 0 && <span className="text-xs text-[var(--ink-3)]">No employees yet.</span>}
                  {employees.map((emp) => {
                    const on = form.team_ids.includes(emp.id);
                    return (
                      <button type="button" key={emp.id} onClick={() => toggleTeam(emp.id)}
                        className={`px-2.5 py-1 text-xs rounded-full border transition ${on
                          ? "border-[var(--accent)] bg-[var(--hover)] text-[#5F5A4B] font-semibold"
                          : "border-[var(--line)] text-[var(--ink-2)] hover:border-[var(--accent)]"}`}
                        data-testid={`team-opt-${emp.id}`}>
                        {empName(emp)}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
          {err && <div className="md:col-span-2 border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
          <button className="btn-primary md:col-span-2" data-testid="project-submit" type="submit">Create project</button>
        </form>
      )}

      <div className="flex flex-col gap-3" data-testid="projects-toolbar">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[220px] max-w-md">
            <MagnifyingGlass size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
            <input className="input-flat w-full !pl-9" value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="Search projects, clients or type" aria-label="Search projects" data-testid="projects-search" />
          </div>
          <select aria-label="Sort projects" className="input-flat !w-auto" value={sort} onChange={(e) => setSort(e.target.value)}
                  data-testid="projects-sort">
            <option value="recent">Newest first</option>
            <option value="name">Name A–Z</option>
            <option value="stage">By stage</option>
          </select>
          <div className="ml-auto flex rounded-lg border border-[var(--line)] bg-white p-0.5" role="group" aria-label="Layout">
            {[["grid", SquaresFour, "Grid view"], ["list", ListBullets, "List view"]].map(([v, Icon, label]) => (
              <button key={v} type="button" onClick={() => setView(v)} aria-pressed={view === v} aria-label={label} title={label}
                      className={`p-1.5 rounded-md transition ${view === v ? "bg-[var(--hover)] text-[var(--ink)]" : "text-[var(--ink-3)] hover:text-[var(--ink)]"}`}
                      data-testid={`projects-view-${v}`}>
                <Icon size={16} />
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by stage">
          {[["all", "All", projects.length], ...STAGES.map((st) => [st, st, projects.filter((x) => (x.stage || "Requirement") === st).length])]
            .filter(([id, , n]) => id === "all" || n > 0)
            .map(([id, label, n]) => (
              <button key={id} type="button" role="tab" aria-selected={stageFilter === id} onClick={() => setStageFilter(id)}
                      className={`px-3 py-1.5 text-xs rounded-full border transition ${stageFilter === id
                        ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--line)] hover:border-[var(--accent-strong)]"}`}
                      data-testid={`projects-stage-${id}`}>
                {label} <span className={stageFilter === id ? "text-white/70" : "text-[var(--ink-3)]"}>{n}</span>
              </button>
            ))}
        </div>
      </div>

      {view === "list" && shown.length > 0 && (
        <div className="border border-[var(--line)] rounded-xl overflow-x-auto bg-white" data-testid="projects-list">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-2)] text-[10px] uppercase tracking-wider text-[var(--ink-2)]">
              <tr><th className="p-3 text-left">Project</th><th className="p-3 text-left">Client</th>
                <th className="p-3 text-left">Stage</th><th className="p-3 text-right">Budget</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.id} className="border-t border-[var(--line-soft)] hover:bg-[var(--surface-2)] cursor-pointer" onClick={() => navigate(`/projects/${p.id}`)}>
                  <td className="p-3"><div className="font-semibold">{p.name}</div><div className="text-xs text-[var(--ink-3)]">{p.project_type}{p.engagement_type ? ` · ${p.engagement_type}` : ""}</div></td>
                  <td className="p-3">{p.client_name || "—"}</td>
                  <td className="p-3"><span className="status-chip chip-medium">{p.stage || "Requirement"}</span></td>
                  <td className="p-3 text-right font-mono">{formatINR(p.budget)}</td>
                  <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>{menuFor(p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(view === "grid" || shown.length === 0) && (
      <div className="border-t border-l border-[var(--line)] grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 stagger">
        {shown.map((p, i) => {
          const idx = STAGES.indexOf(p.stage || "Requirement");
          const pct = Math.round(((idx + 1) / STAGES.length) * 100);
          return (
            <div key={p.id} className="fade-up relative border-r border-b border-[var(--line)] group hover:bg-[var(--surface-2)] transition">
            <div className="absolute top-3 right-3 z-10 flex items-center gap-1">
              {pinned.includes(p.id) && <PushPin size={13} weight="fill" className="text-[var(--accent-strong)]" aria-label="Pinned" />}
              {menuFor(p)}
            </div>
            <button
              onClick={() => navigate(`/projects/${p.id}`)}
              className="w-full text-left p-6 pr-12"
              data-testid={`project-card-${p.id}`}
            >

              <div className="overline mb-2">
                {p.project_type}
                {p.engagement_type && (
                  <span className={`ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
                    p.engagement_type === "consultancy" ? "bg-[var(--hover)] text-[#5F5A4B]" : "bg-[var(--warning-soft)] text-[var(--warning)]"
                  }`}>{p.engagement_type}</span>
                )}
              </div>
              <div className="font-display font-bold tracking-tighter text-2xl mb-1 leading-tight group-hover:accent-blue transition-colors">
                {p.name}
              </div>
              <div className="text-sm text-[var(--ink-2)] mb-5">{p.client_name || "No client"}</div>

              <div className="flex items-center justify-between text-xs font-mono mb-2 tabular-nums">
                <span className="text-[var(--ink)] font-semibold">{p.stage}</span>
                <span className="text-[var(--ink-2)]">{pct}%</span>
              </div>
              <div className="h-1 bg-[var(--line-soft)] relative overflow-hidden">
                <div
                  className="h-1 bg-[var(--accent)] transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="mt-5 flex items-center justify-between">
                <div className="font-mono text-sm font-semibold tabular-nums">{Number(p.budget) > 0 ? formatINR(p.budget) : <span className="font-sans font-normal text-xs text-[var(--ink-3)]">Fee not set</span>}</div>
                <div className="overline flex items-center gap-1 group-hover:text-[var(--accent-strong)] transition-colors">
                  OPEN <CaretRight size={10} weight="bold" className="transition-transform group-hover:translate-x-0.5" />
                </div>
              </div>
            </button>
            </div>
          );
        })}
        {projects.length === 0 && (
          <EmptyState />
        )}
        {projects.length > 0 && shown.length === 0 && (
          <div className="border-r border-b border-[var(--line)] p-10 col-span-full text-center text-sm text-[var(--ink-2)]">
            No projects match. <button type="button" className="underline" onClick={() => { setQuery(""); setStageFilter("all"); }}>Clear filters</button>
          </div>
        )}
      </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="border-r border-b border-[var(--line)] p-12 col-span-full text-center">
      <div className="inline-block mb-4 dotted-bg" style={{ width: 80, height: 80 }} />
      <div className="overline mb-2">NO PROJECTS YET</div>
      <p className="text-[var(--ink-2)] text-sm max-w-sm mx-auto">
        Create a project from scratch or convert a qualified lead from the CRM.
      </p>
    </div>
  );
}
