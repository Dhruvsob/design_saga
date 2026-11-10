import { useEffect, useState } from "react";
import { useParams, Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import CommentsPanel from "../components/CommentsPanel";
import ActivityTimeline from "../components/ActivityTimeline";
import ProjectPhases from "../components/ProjectPhases";
import ProjectSiteVisits from "../components/SiteVisits";
import ProjectDrawings from "../components/ProjectDrawings";
import ProjectSnags from "../components/ProjectSnags";
import ProjectAttention, { ProjectFacts } from "../components/ProjectHub";
import { empName, formatDate, formatINR, statusLabel } from "../lib/format";
import { feeCalc } from "../lib/fees";
import { safeFileUrl } from "../lib/url";
import {
  ArrowLeft, Copy, Plus, PencilSimple, Archive, ArrowCounterClockwise, ArrowsClockwise,
  X, Warning, Trash, UsersThree, CaretRight, Check,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";

const FALLBACK_STAGES = ["Requirement", "Concept", "Design Dev", "Tech Drawings", "Review", "Signoff", "Procurement", "Execution", "Handover"];
const TABS = ["Overview", "Phases", "Tasks", "Milestones", "Vendors", "Files", "Drawings", "Site visits", "Snags", "Invoices", "Activity"];
// One project workspace, grouped the way a studio works on a job.
export const PROJECT_TAB_GROUPS = [
  { id: "overview", label: "Overview", tabs: ["Overview", "Activity"] },
  { id: "work", label: "Work", tabs: ["Phases", "Tasks"] },
  { id: "design", label: "Design", tabs: ["Drawings", "Files"] },
  { id: "site", label: "Site", tabs: ["Site visits", "Snags"] },
  { id: "commercial", label: "Commercial", tabs: ["Milestones", "Invoices", "Vendors"] },
];
const SUBTAB_LABEL = { Milestones: "Fee milestones", Vendors: "Vendors & purchases", Activity: "Activity log" };
const inr = (n) => formatINR(n);

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { hasPerm, user } = useAuth();
  const { values } = useMasterData();
  const STAGES = values("project_stage", FALLBACK_STAGES);
  const TYPES = values("project_type", ["Residential", "Commercial"]);

  const [p, setP] = useState(null);
  const [tab, setTab] = useState(() => (TABS.includes(searchParams.get("tab")) ? searchParams.get("tab") : "Overview"));
  const [loading, setLoading] = useState(true);
  const [fileForm, setFileForm] = useState({ name: "", url: "", stage: "", client_visible: false, file: null });
  const [showFileForm, setShowFileForm] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [teamOpen, setTeamOpen] = useState(false);
  const [form, setForm] = useState({});
  const [employees, setEmployees] = useState([]);
  const [teamForm, setTeamForm] = useState({ project_manager_id: "", team_ids: [] });
  const [msForm, setMsForm] = useState({ name: "", amount: "", due_date: "", kind: "amount" });
  const [showMsForm, setShowMsForm] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/projects/${id}`);
      setP(data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (tab === "Snags" && !employees.length) loadEmployees(); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadEmployees = async () => {
    try {
      const { data } = await api.get("/employees");
      setEmployees((Array.isArray(data) ? data : data.employees || []).filter((x) => x.employment_status !== "terminated"));   // no former staff in pickers
    } catch { setEmployees([]); }
  };

  const setStage = async (stage) => {
    await api.patch(`/projects/${id}/stage`, { stage });
    load();
  };

  const copyShare = () => {
    const url = `${window.location.origin}/portal/${p.share_token}`;
    navigator.clipboard.writeText(url);
    toast.success("Client portal link copied to clipboard");
  };

  const rotateShare = async () => {
    if (!await confirmAction("Reset this client portal link? The previous link will stop working immediately.")) return;
    try {
      const { data } = await api.post(`/projects/${id}/share-token/rotate`);
      setP((current) => ({ ...current, share_token: data.share_token }));
      toast.success("Client portal link reset");
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not reset portal link");
    }
  };

  const addFile = async (e) => {
    e.preventDefault();
    try {
      if (fileForm.file) {
        const body = new FormData();
        body.append("project_id", id);
        body.append("name", fileForm.name || fileForm.file.name);
        body.append("stage", fileForm.stage);
        body.append("client_visible", String(fileForm.client_visible));
        body.append("upload", fileForm.file);
        await api.post("/files/upload", body);
      } else {
        await api.post("/files", { ...fileForm, file: undefined, project_id: id });
      }
      setFileForm({ name: "", url: "", stage: "", client_visible: false, file: null });
      setShowFileForm(false);
      toast.success("File added");
      load();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not add file");
    }
  };

  const deleteFile = async (fid) => {
    if (!await confirmAction("Remove this file link?")) return;
    try { await api.delete(`/files/${fid}`); load(); }
    catch (ex) { toast.error(ex?.response?.data?.detail || "Delete failed"); }
  };

  const setFileClientVisibility = async (fid, clientVisible) => {
    try {
      await api.patch(`/files/${fid}/client-visibility`, { client_visible: clientVisible });
      setP((current) => ({
        ...current,
        files: (current.files || []).map((file) => (
          file.id === fid ? { ...file, client_visible: clientVisible } : file
        )),
      }));
      toast.success(clientVisible ? "File shared in client portal" : "File hidden from client portal");
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Could not update client visibility");
    }
  };

  const openEdit = () => {
    setForm({
      name: p.name || "", project_type: p.project_type || "",
      budget: p.budget ?? "", description: p.description || "",
      start_date: p.start_date || "", end_date: p.end_date || "",
      site_address: p.site_address || "", site_area_sqft: p.site_area_sqft || "",
      fee_structure_type: p.fee_structure_type || "",
      fee_lump_sum_amount: p.fee_lump_sum_amount ?? "",
      fee_project_value: p.fee_project_value ?? "",
      fee_percentage: p.fee_percentage ?? "",
      fee_contract_value: p.fee_contract_value ?? "",
      fee_rate_per_sqft: p.fee_rate_per_sqft ?? "",
    });
    setErr("");
    setEditOpen(true);
  };

  // ⋮ "Edit details" on the Projects list lands here with ?edit=1
  useEffect(() => {
    if (p && searchParams.get("edit") === "1" && hasPerm("projects.update")) {
      openEdit();
      setSearchParams({}, { replace: true });
    }
  }, [p?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveEdit = async (e) => {
    e.preventDefault(); setErr("");
    const payload = {
      ...form,
      budget: Number(form.budget || 0),
      site_area_sqft: form.site_area_sqft ? Number(form.site_area_sqft) : undefined,
      // "" clears the fee structure on the server (undefined would just be dropped)
      fee_structure_type: form.fee_structure_type,
      fee_lump_sum_amount: form.fee_lump_sum_amount !== "" ? Number(form.fee_lump_sum_amount) : undefined,
      fee_project_value: form.fee_project_value !== "" ? Number(form.fee_project_value) : undefined,
      fee_percentage: form.fee_percentage !== "" ? Number(form.fee_percentage) : undefined,
      fee_contract_value: form.fee_contract_value !== "" ? Number(form.fee_contract_value) : undefined,
      fee_rate_per_sqft: form.fee_rate_per_sqft !== "" ? Number(form.fee_rate_per_sqft) : undefined,
    };
    try {
      await api.patch(`/projects/${id}`, payload);
      setEditOpen(false);
      load();
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(typeof d === "string" ? d : "Save failed");
    }
  };

  const openTeam = async () => {
    await loadEmployees();
    setTeamForm({
      project_manager_id: p.project_manager_id || "",
      team_ids: p.team_ids || [],
    });
    setTeamOpen(true);
  };

  const saveTeam = async (e) => {
    e.preventDefault();
    await api.patch(`/projects/${id}`, {
      project_manager_id: teamForm.project_manager_id || undefined,
      team_ids: teamForm.team_ids,
    });
    setTeamOpen(false);
    load();
  };

  const toggleArchive = async () => {
    if (p.archived) {
      await api.post(`/projects/${id}/restore`);
      load();
    } else {
      if (!await confirmAction(`Archive “${p.name}”? It will be hidden from active lists but all history is preserved.`)) return;
      await api.post(`/projects/${id}/archive`);
      navigate("/projects");
    }
  };

  const addMilestone = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/projects/${id}/milestones`, {
        project_id: id, name: msForm.name, due_date: msForm.due_date || undefined,
        ...(msForm.kind === "percent" ? { percent: Number(msForm.amount || 0) } : { amount: Number(msForm.amount || 0) }),
      });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not add milestone");
      return;
    }
    setMsForm({ name: "", amount: "", due_date: "", kind: "amount" });
    setShowMsForm(false);
    load();
  };

  if (loading || !p) return <div className="overline">LOADING…</div>;

  const currentIdx = STAGES.indexOf(p.stage || STAGES[0]);
  const fin = p.financials || {};
  // `money` keeps value, billing and cash received apart and counts receipts made
  // through Collections Due; the older `financials` block only sees invoice payments.
  const money = p.money || {};
  const stillToReceive = money.still_to_receive ?? Math.max(0, Number(money.invoiced || 0) - Number(money.received || 0));
  // Backend decides financial visibility (finance.read / invoices.read / Admin).
  // Fall back to client perms if the flag is absent.
  const canSeeFinancials = (p.can_view_financials !== undefined)
    ? !!p.can_view_financials
    : (hasPerm("*.*") || hasPerm("finance.read") || hasPerm("invoices.read"));
  const canSeeProcurement = (p.can_view_procurement !== undefined)
    ? !!p.can_view_procurement
    : hasPerm("purchase_orders.read");
  const canSeeVendorCosts = (p.can_view_vendor_costs !== undefined)
    ? !!p.can_view_vendor_costs
    : (hasPerm("*.*") || hasPerm("finance.read"));
  const visibleTabs = TABS.filter((t) => {
    if ((t === "Milestones" || t === "Invoices") && !canSeeFinancials) return false;
    if (t === "Vendors" && !canSeeProcurement && !canSeeVendorCosts) return false;
    if (t === "Site visits" && !(hasPerm("attendance.read") || hasPerm("attendance.create"))) return false;
    if (t === "Drawings" && !hasPerm("files.read")) return false;
    return true;
  });
  const tabGroups = PROJECT_TAB_GROUPS
    .map((g) => ({ ...g, tabs: g.tabs.filter((t) => visibleTabs.includes(t)) }))
    .filter((g) => g.tabs.length);
  const activeGroup = tabGroups.find((g) => g.tabs.includes(tab)) || tabGroups[0];
  const COUNTS = { Tasks: (p.tasks || []).length, Milestones: (p.milestones || []).length, Invoices: (p.invoices || []).length,
    Files: (p.files || []).length, Vendors: (p.purchase_orders || []).length + (p.vendor_bills || []).length };
  const groupCount = (g) => g.tabs.reduce((n, t) => n + (COUNTS[t] || 0), 0);

  return (
    <div className="space-y-8" data-testid="project-detail">
      <Link to="/projects" className="inline-flex items-center gap-1 text-sm text-[var(--ink-2)] hover:text-[var(--ink)]">
        <ArrowLeft size={14} /> Back to projects
      </Link>

      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="overline mb-2">
            {p.project_type} · {p.client_id ? (
              <Link to={`/clients/${p.client_id}`} className="hover:text-[var(--accent-strong)] underline-offset-2 hover:underline">{p.client_name || "—"}</Link>
            ) : (p.client_name || "—")}
            {p.engagement_type && (
              <span className={`ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
                p.engagement_type === "consultancy" ? "bg-[var(--hover)] text-[#5F5A4B]" : "bg-[var(--warning-soft)] text-[var(--warning)]"
              }`}>{p.engagement_type}</span>
            )}
            {p.archived && <span className="ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-[var(--hover)] text-[var(--ink-3)]">ARCHIVED</span>}
          </div>
          <h1 className="font-display font-bold tracking-tight text-4xl">{p.name}</h1>
          {p.description && <p className="mt-2 text-[var(--ink-2)] max-w-2xl">{p.description}</p>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {hasPerm("projects.update") && (
            <>
              <button onClick={openEdit} className="btn-ghost" data-testid="project-edit-btn">
                <PencilSimple size={14} /> Edit
              </button>
            </>
          )}
          {hasPerm("projects.update") && p.share_token && (
            <button onClick={copyShare} className="btn-ghost" data-testid="share-portal-btn">
              <Copy size={14} /> Client portal link
            </button>
          )}
          {hasPerm("projects.update") && (
            <RowActions label={p.name} testid="project-more-actions" actions={[
              { label: p.archived ? "Restore project" : "Archive project", icon: p.archived ? ArrowCounterClockwise : Archive,
                onSelect: toggleArchive, testid: "project-archive-btn" },
              { label: "New quotation for this project", icon: Plus, hidden: !hasPerm("quotations.create"),
                onSelect: () => navigate(`/quotations?project=${p.id}`) },
              { label: "Reset client portal link", icon: ArrowsClockwise, hidden: !p.share_token, divider: true,
                onSelect: rotateShare },
            ]} />
          )}
        </div>
      </div>

      {/* Stage tracker: one progress line; click a stage to move the project */}
      <div className="border border-[var(--line)] rounded-xl bg-white px-5 py-4" data-testid="stage-tracker">
        <div className="flex items-center justify-between mb-3">
          <div className="overline">LIFECYCLE</div>
          <div className="text-xs text-[var(--ink-2)]">Stage {currentIdx + 1} of {STAGES.length} · <span className="font-semibold text-[var(--ink)]">{STAGES[currentIdx] || p.stage}</span></div>
        </div>
        <ol className="flex flex-wrap lg:flex-nowrap items-start gap-y-3" aria-label="Project stages">
          {STAGES.map((s, i) => {
            const done = i < currentIdx;
            const current = i === currentIdx;
            return (
              <li key={s} className="flex-1 min-w-[96px] relative">
                {i > 0 && <span aria-hidden="true" className={`hidden lg:block absolute top-[11px] right-1/2 w-full h-[2px] ${i <= currentIdx ? "bg-[var(--accent)]" : "bg-[var(--line)]"}`} />}
                <button type="button" onClick={() => setStage(s)} data-testid={`stage-${s}`}
                  aria-current={current ? "step" : undefined}
                  title={current ? "Current stage" : `Move project to ${s}`}
                  className="relative z-[1] w-full flex flex-col items-center gap-1.5 group">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold border transition ${
                    current ? "bg-[var(--accent-strong)] border-[var(--accent-strong)] text-white ring-4 ring-[var(--accent-ring)]"
                    : done ? "bg-[var(--accent)] border-[var(--accent)] text-white"
                    : "bg-white border-[var(--line-strong)] text-[var(--ink-3)] group-hover:border-[var(--accent-strong)]"}`}>
                    {done ? <Check size={11} weight="bold" /> : i + 1}
                  </span>
                  <span className={`text-[11px] leading-tight text-center px-1 ${current ? "font-semibold text-[var(--ink)]" : done ? "text-[var(--ink-2)]" : "text-[var(--ink-3)] group-hover:text-[var(--ink)]"}`}>{s}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Tabs: five groups; the active group's sections underneath */}
      <div className="border-b border-[var(--line)]">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Project sections">
          {tabGroups.map((g) => (
            <button key={g.id} type="button" role="tab" aria-selected={activeGroup?.id === g.id}
              onClick={() => { if (!g.tabs.includes(tab)) setTab(g.tabs[0]); }}
              className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition whitespace-nowrap ${
                activeGroup?.id === g.id ? "border-[var(--accent)] text-[var(--accent-strong)]" : "border-transparent text-[var(--ink-2)] hover:text-[var(--ink)]"
              }`}
              data-testid={`tab-group-${g.id}`}>
              {g.label}
              {groupCount(g) > 0 && <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-3)]">{groupCount(g)}</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 -mt-4" role="tablist" aria-label={`${activeGroup?.label || ""} sections`}>
        {(activeGroup?.tabs || []).map((t) => (
          <button
            key={t}
            type="button" role="tab" aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs border rounded-full transition whitespace-nowrap ${
              tab === t ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--line)] hover:border-[var(--accent-strong)]"
            }`}
            data-testid={`tab-${t}`}
          >
            {SUBTAB_LABEL[t] || t}
            {t === "Tasks" && (p.tasks || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-3)]">{p.tasks.length}</span>}
            {t === "Milestones" && (p.milestones || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-3)]">{p.milestones.length}</span>}
            {t === "Vendors" && ((p.purchase_orders || []).length + (p.vendor_bills || []).length) > 0 && <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-3)]">{(p.purchase_orders || []).length + (p.vendor_bills || []).length}</span>}
            {t === "Files" && (p.files || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-3)]">{p.files.length}</span>}
            {t === "Invoices" && (p.invoices || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[var(--ink-3)]">{p.invoices.length}</span>}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-8">
          <ProjectFacts p={p} />
          <ProjectAttention p={p} visibleTabs={visibleTabs} canSeeFinancials={canSeeFinancials}
                            onOpen={(t) => setTab(t)} />
          {/* financials — only for Admin / Finance / Accounting */}
          {canSeeFinancials ? (
            <div className="grid grid-cols-2 md:grid-cols-5 border-t border-l border-[var(--line)] kpi-grid" data-testid="project-financials">
              <MiniStat label="Project value" value={inr(money.project_value ?? fin.budget)} />
              <MiniStat label="Invoiced" value={inr(money.invoiced ?? fin.invoiced)} />
              <MiniStat label="Received" value={inr(money.received ?? fin.collected)} accent="#1D633E" />
              <MiniStat label="Still to receive" value={inr(stillToReceive)} accent={stillToReceive > 0 ? "#B22B22" : undefined} />
              {canSeeVendorCosts && <MiniStat label="Vendor cost" value={inr(fin.vendor_cost)} />}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 border-t border-l border-[var(--line)] kpi-grid" data-testid="project-operational-stats">
              <MiniStat label="Tasks" value={`${(p.tasks || []).length}`} />
              <MiniStat label="Team" value={`${(p.team || []).length + (p.project_manager ? 1 : 0)}`} />
              <MiniStat label="Files" value={`${(p.files || []).length}`} />
              <MiniStat label="Stage" value={p.stage || "—"} />
            </div>
          )}

          <div className="grid grid-cols-1 gap-6">
            {/* team */}
            <div className="border border-[var(--line)] rounded-lg p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="overline"><UsersThree size={12} className="inline mr-1" /> TEAM</div>
                {hasPerm("projects.update") && (
                  <button onClick={openTeam} className="btn-ghost text-xs" data-testid="assign-team-btn">
                    <PencilSimple size={12} /> Assign
                  </button>
                )}
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-[var(--ink-2)]">Project Manager</span>
                  {p.project_manager ? (
                    <Link to={`/employees/${p.project_manager.id}`} className="font-semibold hover:text-[var(--accent-strong)]">
                      {p.project_manager.name}
                      <span className="text-xs text-[var(--ink-3)] ml-1.5">{p.project_manager.designation}</span>
                    </Link>
                  ) : <span className="text-[var(--ink-3)]">Unassigned</span>}
                </div>
                <div className="border-t border-[var(--line-soft)] pt-2">
                  <div className="text-xs text-[var(--ink-2)] mb-1.5">Members</div>
                  {(p.team || []).length === 0 && <div className="text-sm text-[var(--ink-3)]">No members assigned.</div>}
                  <div className="flex flex-wrap gap-1.5">
                    {(p.team || []).map((m) => (
                      <Link key={m.id} to={`/employees/${m.id}`}
                        className="text-xs border border-[var(--line)] px-2 py-1 rounded-md hover:border-[var(--ink)] transition">
                        {m.name} {m.designation && <span className="text-[var(--ink-3)]">· {m.designation}</span>}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      )}

      {tab === "Phases" && (
        <ProjectPhases projectId={id} project={p} canEdit={hasPerm("projects.update")}
          canSeeFinancials={canSeeFinancials} onChanged={load} />
      )}

      {tab === "Tasks" && (
        <div className="space-y-2">
          {(p.tasks || []).length === 0 && <Empty text="No tasks yet. Add them from the Tasks page." />}
          {(p.tasks || []).map((t) => (
            <button key={t.id} onClick={() => navigate(`/tasks/${t.id}`)}
              className="w-full text-left border border-[var(--line)] rounded-lg p-3 flex items-center justify-between hover:border-[var(--ink)] transition"
              data-testid={`project-task-${t.id}`}>
              <div>
                <div className="font-semibold text-sm">{t.title}</div>
                <div className="text-xs text-[var(--ink-2)]">
                  {[t.area, t.category].filter(Boolean).join(" · ") || null}
                  {(t.area || t.category) && " · "}
                  Due {formatDate(t.due_date)} · {t.assignee_name || "Unassigned"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-[var(--hover)] text-[var(--ink-2)]">{t.status_detail || t.status}</span>
                <span className={`status-chip chip-${t.priority}`}>{statusLabel(t.priority)}</span>
                <CaretRight size={12} className="text-[var(--ink-3)]" />
              </div>
            </button>
          ))}
        </div>
      )}

      {tab === "Milestones" && canSeeFinancials && (
        <div className="space-y-3">
          {hasPerm("finance.read") && (
            <div className="flex justify-end">
              <button onClick={() => setShowMsForm(!showMsForm)} className="btn-primary" data-testid="add-milestone-btn">
                {showMsForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> {"Add milestone"}</>}
              </button>
            </div>
          )}
          {showMsForm && (
            <form onSubmit={addMilestone} className="card-flat grid grid-cols-1 md:grid-cols-4 gap-3">
              <input className="input-flat" placeholder="Milestone name" required value={msForm.name} onChange={(e) => setMsForm({ ...msForm, name: e.target.value })} data-testid="ms-name" />
              <div className="flex gap-2">
                <select aria-label="Fee type" className="input-flat w-28" value={msForm.kind} onChange={(e) => setMsForm({ ...msForm, kind: e.target.value })} data-testid="ms-kind">
                  <option value="amount">₹ fixed</option>
                  <option value="percent">% of value</option>
                </select>
                <input className="input-flat flex-1" type="number" step="0.01" min="0.01" max={msForm.kind === "percent" ? 100 : undefined}
                  placeholder={msForm.kind === "percent" ? "e.g. 10 (%)" : "Amount (₹)"} required value={msForm.amount}
                  onChange={(e) => setMsForm({ ...msForm, amount: e.target.value })} data-testid="ms-amount" />
              </div>
              <input className="input-flat" type="date" value={msForm.due_date} onChange={(e) => setMsForm({ ...msForm, due_date: e.target.value })} />
              <button className="btn-primary" data-testid="ms-submit">Save</button>
            </form>
          )}
          {p.money && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2" data-testid="project-money">
              {[["Project value", p.money.project_value, "Agreed fee / contract value"],
                ["Scheduled", p.money.scheduled, "Total of milestones"],
                ["Invoiced", p.money.invoiced, "Invoices sent (documents)"],
                ["Received", p.money.received, "Money actually in Cash/Bank"],
                ["Still to receive", p.money.still_to_receive ?? p.money.billed_unpaid, p.money.project_value ? "Project value − received" : "Invoiced − received"],
              ].map(([label, value, hint]) => (
                <div key={label} className="border border-[var(--line)] rounded-lg p-3">
                  <div className="overline">{label}</div>
                  <div className={`font-display font-bold text-lg tabular-nums ${label === "Received" ? "text-[var(--success)]" : ""}`}>{inr(value)}</div>
                  <div className="text-[10px] text-[var(--ink-3)]">{hint}</div>
                </div>
              ))}
            </div>
          )}
          {(p.milestones || []).length === 0 && <Empty text="No payment milestones yet." />}
          {(p.milestones || []).map((m) => (
            <div key={m.id} className="border border-[var(--line)] rounded-md p-3 flex items-center justify-between" data-testid={`milestone-${m.id}`}>
              <div>
                <div className="font-semibold text-sm">{m.name}</div>
                <div className="text-xs text-[var(--ink-2)]">Due {formatDate(m.due_date)}{m.percent ? ` · ${m.percent}% of project value` : ""}{Number(m.paid_amount || 0) > 0 && m.status !== "paid" ? ` · ${inr(m.paid_amount)} received` : ""}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono font-semibold">{inr(m.amount)}</span>
                <span className={`status-chip chip-${m.status || "pending"}`}>{m.status === "paid" ? "received" : Number(m.paid_amount || 0) > 0 ? "part received" : m.invoice_id ? "invoiced" : "due"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Vendors" && (
        <div className="space-y-6">
          {canSeeProcurement && <div>
            <div className="overline mb-3">PURCHASE ORDERS</div>
            {(p.purchase_orders || []).length === 0 && <Empty text="No purchase orders linked to this project." />}
            <div className="space-y-2">
              {(p.purchase_orders || []).map((po) => (
                <button key={po.id} onClick={() => navigate("/purchase-orders")}
                  className="w-full text-left border border-[var(--line)] rounded-lg p-3 flex items-center justify-between hover:border-[var(--ink)] transition">
                  <div>
                    <div className="font-mono font-semibold text-sm">{po.po_number}</div>
                    <div className="text-xs text-[var(--ink-2)]">{po.vendor_name || "—"}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-semibold">{inr(po.total)}</span>
                    <span className={`status-chip chip-${po.status}`}>{statusLabel(po.status)}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>}
          {canSeeVendorCosts && <div>
            <div className="overline mb-3">VENDOR BILLS</div>
            {(p.vendor_bills || []).length === 0 && <Empty text="No vendor bills linked to this project." />}
            <div className="space-y-2">
              {(p.vendor_bills || []).map((b) => (
                <button key={b.id} onClick={() => b.vendor_id && navigate(`/vendors/${b.vendor_id}`)}
                  className="w-full text-left border border-[var(--line)] rounded-lg p-3 flex items-center justify-between hover:border-[var(--ink)] transition">
                  <div>
                    <div className="font-mono font-semibold text-sm">{b.bill_number || b.id}</div>
                    <div className="text-xs text-[var(--ink-2)]">{b.vendor_name || "—"} · {formatDate(b.bill_date)}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-semibold">{inr(b.total)}</span>
                    <span className={`status-chip chip-${b.status}`}>{statusLabel(b.status)}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>}
        </div>
      )}

      {tab === "Files" && (
        <div className="space-y-3">
          <div className="flex justify-end">
            {hasPerm("files.create") && <button onClick={() => setShowFileForm(!showFileForm)} className="btn-primary" data-testid="add-file-btn">
              <Plus size={14} /> Add file
            </button>}
          </div>
          {showFileForm && (
            <form onSubmit={addFile} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3">
              <input className="input-flat" placeholder="Display name" value={fileForm.name} onChange={(e) => setFileForm({ ...fileForm, name: e.target.value })} />
              <input className="input-flat" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.docx,.xlsx,.csv,.txt" onChange={(e) => setFileForm({ ...fileForm, file: e.target.files?.[0] || null })} />
              <input className="input-flat" placeholder="Or paste an external URL" required={!fileForm.file} value={fileForm.url} onChange={(e) => setFileForm({ ...fileForm, url: e.target.value })} />
              <input className="input-flat" placeholder="Stage (e.g. Concept)" value={fileForm.stage} onChange={(e) => setFileForm({ ...fileForm, stage: e.target.value })} />
              <label className="md:col-span-3 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={fileForm.client_visible} onChange={(e) => setFileForm({ ...fileForm, client_visible: e.target.checked })} />
                Share this file in the client portal
              </label>
              <button className="btn-primary md:col-span-3">Save</button>
            </form>
          )}
          {(p.files || []).length === 0 && <Empty text="No files yet." />}
          {(p.files || []).map((f) => (
            <div key={f.id} className="border border-[var(--line)] rounded-md p-3 flex items-center justify-between hover:border-[var(--ink)] transition group">
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm">{f.name}</div>
                <div className="text-xs text-[var(--ink-2)]">{f.stage || "—"} · v{f.version || 1} · {f.uploader_name}</div>
              </div>
              <div className="flex items-center gap-2">
                {(f.created_by === user?.user_id || hasPerm("files.update")) && (
                  <label className="flex items-center gap-2 text-xs text-[var(--ink-2)]" title="Control whether this file appears in the public client portal">
                    <input type="checkbox" checked={Boolean(f.client_visible)} onChange={(e) => setFileClientVisibility(f.id, e.target.checked)} />
                    Client portal
                  </label>
                )}
                {safeFileUrl(f.url) ? <a href={safeFileUrl(f.url)} target="_blank" rel="noreferrer" className="overline">OPEN →</a> : <span className="overline text-[var(--ink-3)]">UNAVAILABLE</span>}
                <RowActions label={f.name || "file"} testid={`file-actions-${f.id}`} actions={[
                  { label: "Remove file", icon: Trash, danger: true, onSelect: () => deleteFile(f.id), testid: `file-delete-${f.id}` },
                ]} />
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Drawings" && <ProjectDrawings projectId={id} projectName={p.name} files={p.files || []} onFilesChanged={load} />}
      {tab === "Snags" && <ProjectSnags projectId={id} employees={employees} />}
      {tab === "Site visits" && <ProjectSiteVisits projectId={id} projectName={p.name} />}

      {tab === "Invoices" && canSeeFinancials && (
        <div className="space-y-2">
          {(p.invoices || []).length === 0 && <Empty text="No invoices yet." />}
          {(p.invoices || []).map((i) => (
            <div key={i.id} className="border border-[var(--line)] rounded-md p-3 flex items-center justify-between">
              <div>
                <div className="font-mono font-semibold text-sm">{i.number}</div>
                <div className="text-xs text-[var(--ink-2)]">{i.doc_type} · Due {formatDate(i.due_date)}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="font-mono font-semibold">{inr(i.total)}</div>
                <span className={`status-chip chip-${i.status}`}>{statusLabel(i.status)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Activity" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <CommentsPanel entityType="project" entityId={id} />
          <ActivityTimeline entityType="project" entityId={id} />
        </div>
      )}

      {/* Edit modal */}
      {editOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setEditOpen(false); }}>
          <form onSubmit={saveEdit} className="bg-white border border-[var(--ink)] w-full max-w-lg p-6 space-y-3 max-h-[85vh] overflow-y-auto" data-testid="project-edit-modal">
            <div className="flex items-center justify-between">
              <div className="overline">EDIT PROJECT</div>
              <button type="button" onClick={() => setEditOpen(false)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <input required className="input-flat w-full" placeholder="Project name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="edit-project-name" />
            <div className="grid grid-cols-2 gap-3">
              <select aria-label="Project type" className="input-flat" value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
                {TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <input className="input-flat" type="number" min="0" placeholder="Enter Budget (₹)" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} data-testid="edit-project-budget" />
              <label className="text-xs text-[var(--ink-2)]">Start date
                <input className="input-flat w-full mt-1" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              </label>
              <label className="text-xs text-[var(--ink-2)]">End date
                <input className="input-flat w-full mt-1" type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              </label>
            </div>
            <input className="input-flat w-full" placeholder="Site address" value={form.site_address} onChange={(e) => setForm({ ...form, site_address: e.target.value })} />
            <input className="input-flat w-full" type="number" min="0" placeholder="Enter site area (sq ft)" value={form.site_area_sqft} onChange={(e) => setForm({ ...form, site_area_sqft: e.target.value })} />

            {/* Fee structure */}
            <div className="border-t border-[var(--line-soft)] pt-3 space-y-2">
              <div className="overline text-[10px]">FEE STRUCTURE</div>
              <select aria-label="Fee structure type" className="input-flat w-full"
                value={form.fee_structure_type}
                onChange={(e) => setForm({ ...form, fee_structure_type: e.target.value })}>
                <option value="">— Select fee type —</option>
                <option value="lump_sum">Lump Sum (fixed fee)</option>
                <option value="percentage_consultancy">Consultancy % (% of project value)</option>
                <option value="turnkey">Turnkey (materials + execution)</option>
                <option value="per_sqft">Per Sq Ft (rate × area)</option>
              </select>
              {form.fee_structure_type === "lump_sum" && (
                <input className="input-flat w-full" type="number" min="0" placeholder="Fixed fee amount (₹)"
                  value={form.fee_lump_sum_amount}
                  onChange={(e) => setForm({ ...form, fee_lump_sum_amount: e.target.value })} />
              )}
              {form.fee_structure_type === "percentage_consultancy" && (
                <div className="grid grid-cols-2 gap-2">
                  <input className="input-flat" type="number" min="0" placeholder="Total project value (₹)"
                    value={form.fee_project_value}
                    onChange={(e) => setForm({ ...form, fee_project_value: e.target.value })} />
                  <input className="input-flat" type="number" min="0" max="100" step="0.01" placeholder="Fee % (e.g. 8.5)"
                    value={form.fee_percentage}
                    onChange={(e) => setForm({ ...form, fee_percentage: e.target.value })} />
                </div>
              )}
              {form.fee_structure_type === "turnkey" && (
                <input className="input-flat w-full" type="number" min="0" placeholder="Turnkey contract value (₹)"
                  value={form.fee_contract_value}
                  onChange={(e) => setForm({ ...form, fee_contract_value: e.target.value })} />
              )}
              {form.fee_structure_type === "per_sqft" && (
                <input className="input-flat w-full" type="number" min="0" placeholder="Rate per sq ft (₹/sq ft)"
                  value={form.fee_rate_per_sqft}
                  onChange={(e) => setForm({ ...form, fee_rate_per_sqft: e.target.value })} />
              )}
              {feeCalc(form) !== null && (
                <div className="text-xs text-[var(--ink-2)] font-mono bg-[var(--surface-2)] px-3 py-1.5 rounded">
                  Calculated fee: <span className="text-[var(--ink)] font-semibold">{inr(feeCalc(form))}</span>
                  {form.fee_structure_type === "per_sqft" && form.site_area_sqft && ` (${Number(form.site_area_sqft).toLocaleString()} sq ft × ₹${Number(form.fee_rate_per_sqft).toLocaleString()}/sq ft)`}
                  {form.fee_structure_type === "percentage_consultancy" && form.fee_percentage && ` (${form.fee_percentage}% of ${inr(Number(form.fee_project_value))})`}
                </div>
              )}
            </div>

            <textarea className="input-flat w-full" rows="2" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 flex items-center gap-2"><Warning size={12} /> {err}</div>}
            <button className="btn-primary w-full" data-testid="edit-project-save">Save changes</button>
          </form>
        </div>
      )}

      {/* Team modal */}
      {teamOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setTeamOpen(false); }}>
          <form onSubmit={saveTeam} className="bg-white border border-[var(--ink)] w-full max-w-lg p-6 space-y-4 max-h-[85vh] overflow-y-auto" data-testid="team-modal">
            <div className="flex items-center justify-between">
              <div className="overline">ASSIGN TEAM</div>
              <button type="button" onClick={() => setTeamOpen(false)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <label className="block">
              <div className="overline text-[10px] mb-1">PROJECT MANAGER</div>
              <select aria-label="Project manager" className="input-flat w-full" value={teamForm.project_manager_id}
                onChange={(e) => setTeamForm({ ...teamForm, project_manager_id: e.target.value })}
                data-testid="team-pm-select">
                <option value="">Unassigned</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{empName(emp)} {emp.designation ? `· ${emp.designation}` : ""}</option>
                ))}
              </select>
            </label>
            <div>
              <div className="overline text-[10px] mb-2">TEAM MEMBERS</div>
              {employees.length === 0 && <div className="text-sm text-[var(--ink-3)]">No employees found. Add them in the Employees module.</div>}
              <div className="max-h-56 overflow-y-auto border border-[var(--line)] divide-y divide-[var(--line-soft)]">
                {employees.map((emp) => (
                  <label key={emp.id} className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-[var(--surface-2)]">
                    <input type="checkbox"
                      checked={teamForm.team_ids.includes(emp.id)}
                      onChange={(e) => setTeamForm((f) => ({
                        ...f,
                        team_ids: e.target.checked
                          ? [...f.team_ids, emp.id]
                          : f.team_ids.filter((x) => x !== emp.id),
                      }))} />
                    <span className="font-semibold">{empName(emp)}</span>
                    <span className="text-xs text-[var(--ink-3)]">{emp.designation || emp.department || ""}</span>
                  </label>
                ))}
              </div>
            </div>
            <button className="btn-primary w-full" data-testid="team-save">Save team</button>
          </form>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, accent }) {
  return (
    <div className="border-r border-b border-[var(--line)] p-5">
      <div className="overline mb-2">{label}</div>
      <div className="font-display font-bold tracking-tight text-2xl tabular-nums" style={accent ? { color: accent } : undefined}>{value}</div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-[var(--ink-2)]">{k}</dt>
      <dd className="font-semibold">{v}</dd>
    </div>
  );
}

function Empty({ text }) {
  return <p className="text-[var(--ink-2)] text-sm border border-dashed border-[var(--line)] rounded-md p-6 text-center">{text}</p>;
}
