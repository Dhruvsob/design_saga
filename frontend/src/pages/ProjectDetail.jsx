import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import CommentsPanel from "../components/CommentsPanel";
import ActivityTimeline from "../components/ActivityTimeline";
import {
  ArrowLeft, Copy, Plus, PencilSimple, Archive, ArrowCounterClockwise,
  X, Warning, Trash, UsersThree, CaretRight,
} from "@phosphor-icons/react";

const FALLBACK_STAGES = ["Requirement", "Concept", "Design Dev", "Tech Drawings", "Review", "Signoff", "Procurement", "Execution", "Handover"];
const TABS = ["Overview", "Tasks", "Milestones", "Vendors", "Files", "Invoices", "Activity"];
const inr = (n) => `₹${(n || 0).toLocaleString("en-IN")}`;

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const { values } = useMasterData();
  const STAGES = values("project_stage", FALLBACK_STAGES);
  const TYPES = values("project_type", ["Residential", "Commercial"]);

  const [p, setP] = useState(null);
  const [tab, setTab] = useState("Overview");
  const [loading, setLoading] = useState(true);
  const [fileForm, setFileForm] = useState({ name: "", url: "", stage: "" });
  const [showFileForm, setShowFileForm] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [teamOpen, setTeamOpen] = useState(false);
  const [form, setForm] = useState({});
  const [employees, setEmployees] = useState([]);
  const [teamForm, setTeamForm] = useState({ project_manager_id: "", team_ids: [] });
  const [msForm, setMsForm] = useState({ name: "", amount: "", due_date: "" });
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

  const loadEmployees = async () => {
    try {
      const { data } = await api.get("/employees");
      setEmployees(Array.isArray(data) ? data : data.employees || []);
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

  const addFile = async (e) => {
    e.preventDefault();
    await api.post("/files", { ...fileForm, project_id: id });
    setFileForm({ name: "", url: "", stage: "" });
    setShowFileForm(false);
    load();
  };

  const deleteFile = async (fid) => {
    if (!window.confirm("Remove this file link?")) return;
    try { await api.delete(`/files/${fid}`); load(); }
    catch (ex) { alert(ex?.response?.data?.detail || "Delete failed"); }
  };

  const openEdit = () => {
    setForm({
      name: p.name || "", project_type: p.project_type || "",
      budget: p.budget || 0, description: p.description || "",
      start_date: p.start_date || "", end_date: p.end_date || "",
      site_address: p.site_address || "", site_area_sqft: p.site_area_sqft || "",
    });
    setErr("");
    setEditOpen(true);
  };

  const saveEdit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      await api.patch(`/projects/${id}`, {
        ...form,
        budget: Number(form.budget || 0),
        site_area_sqft: form.site_area_sqft ? Number(form.site_area_sqft) : undefined,
      });
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
      if (!window.confirm(`Archive “${p.name}”? It will be hidden from active lists but all history is preserved.`)) return;
      await api.post(`/projects/${id}/archive`);
      navigate("/projects");
    }
  };

  const addMilestone = async (e) => {
    e.preventDefault();
    await api.post(`/projects/${id}/milestones`, {
      project_id: id, name: msForm.name,
      amount: Number(msForm.amount || 0), due_date: msForm.due_date || undefined,
    });
    setMsForm({ name: "", amount: "", due_date: "" });
    setShowMsForm(false);
    load();
  };

  if (loading || !p) return <div className="overline">LOADING…</div>;

  const currentIdx = STAGES.indexOf(p.stage || STAGES[0]);
  const fin = p.financials || {};
  const canFinance = hasPerm("finance.read");

  return (
    <div className="space-y-8" data-testid="project-detail">
      <Link to="/projects" className="inline-flex items-center gap-1 text-sm text-[#5C5C5C] hover:text-[#0A0A0A]">
        <ArrowLeft size={14} /> Back to projects
      </Link>

      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="overline mb-2">
            {p.project_type} · {p.client_id ? (
              <Link to={`/clients/${p.client_id}`} className="hover:text-[#8B7F6A] underline-offset-2 hover:underline">{p.client_name || "—"}</Link>
            ) : (p.client_name || "—")}
            {p.engagement_type && (
              <span className={`ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 ${
                p.engagement_type === "consultancy" ? "bg-[#F5F4F0] text-[#8B7F6A]" : "bg-[#FFF4E5] text-[#7A4E1A]"
              }`}>{p.engagement_type}</span>
            )}
            {p.archived && <span className="ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 bg-[#F5F5F5] text-[#9A9A9A]">ARCHIVED</span>}
          </div>
          <h1 className="font-display font-bold tracking-tight text-4xl">{p.name}</h1>
          {p.description && <p className="mt-2 text-[#5C5C5C] max-w-2xl">{p.description}</p>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {hasPerm("projects.update") && (
            <>
              <button onClick={openEdit} className="btn-ghost" data-testid="project-edit-btn">
                <PencilSimple size={14} /> Edit
              </button>
              <button onClick={toggleArchive} className="btn-ghost" data-testid="project-archive-btn">
                {p.archived ? <><ArrowCounterClockwise size={14} /> Restore</> : <><Archive size={14} /> Archive</>}
              </button>
            </>
          )}
          <button onClick={copyShare} className="btn-ghost" data-testid="share-portal-btn">
            <Copy size={14} /> Client portal link
          </button>
        </div>
      </div>

      {/* Stage tracker */}
      <div className="border border-[#E5E5E5] p-6 bg-white" data-testid="stage-tracker">
        <div className="overline mb-4">LIFECYCLE STAGE</div>
        <div className="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-1">
          {STAGES.map((s, i) => {
            const done = i < currentIdx;
            const current = i === currentIdx;
            return (
              <button
                key={s}
                onClick={() => setStage(s)}
                className={`p-2 text-[10px] font-mono uppercase tracking-wider border text-left transition ${
                  current ? "bg-[#8B7F6A] text-white border-[#8B7F6A]"
                  : done ? "bg-[#0A0A0A] text-white border-[#0A0A0A]"
                  : "bg-white text-[#5C5C5C] border-[#E5E5E5] hover:border-[#0A0A0A]"
                }`}
                data-testid={`stage-${s}`}
              >
                <div className="opacity-60">STEP {i + 1}</div>
                <div className="font-semibold">{s}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-[#E5E5E5] overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition whitespace-nowrap ${
              tab === t ? "border-[#8B7F6A] text-[#8B7F6A]" : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"
            }`}
            data-testid={`tab-${t}`}
          >
            {t}
            {t === "Tasks" && (p.tasks || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[#9A9A9A]">{p.tasks.length}</span>}
            {t === "Milestones" && (p.milestones || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[#9A9A9A]">{p.milestones.length}</span>}
            {t === "Vendors" && ((p.purchase_orders || []).length + (p.vendor_bills || []).length) > 0 && <span className="ml-1.5 font-mono text-[10px] text-[#9A9A9A]">{(p.purchase_orders || []).length + (p.vendor_bills || []).length}</span>}
            {t === "Files" && (p.files || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[#9A9A9A]">{p.files.length}</span>}
            {t === "Invoices" && (p.invoices || []).length > 0 && <span className="ml-1.5 font-mono text-[10px] text-[#9A9A9A]">{p.invoices.length}</span>}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-6">
          {/* financials */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-0 border-t border-l border-[#E5E5E5]">
            <MiniStat label="Budget" value={inr(fin.budget)} />
            <MiniStat label="Invoiced" value={inr(fin.invoiced)} />
            <MiniStat label="Collected" value={inr(fin.collected)} accent="#1D633E" />
            <MiniStat label="Outstanding" value={inr(fin.outstanding)} accent={fin.outstanding > 0 ? "#B22B22" : undefined} />
            {canFinance
              ? <MiniStat label="Vendor cost" value={inr(fin.vendor_cost)} />
              : <MiniStat label="Tasks" value={`${(p.tasks || []).length}`} />}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* team */}
            <div className="border border-[#E5E5E5] p-5">
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
                  <span className="text-[#5C5C5C]">Project Manager</span>
                  {p.project_manager ? (
                    <Link to={`/employees/${p.project_manager.id}`} className="font-semibold hover:text-[#8B7F6A]">
                      {p.project_manager.name}
                      <span className="text-xs text-[#9A9A9A] ml-1.5">{p.project_manager.designation}</span>
                    </Link>
                  ) : <span className="text-[#9A9A9A]">Unassigned</span>}
                </div>
                <div className="border-t border-[#F0F0F0] pt-2">
                  <div className="text-xs text-[#5C5C5C] mb-1.5">Members</div>
                  {(p.team || []).length === 0 && <div className="text-sm text-[#9A9A9A]">No members assigned.</div>}
                  <div className="flex flex-wrap gap-1.5">
                    {(p.team || []).map((m) => (
                      <Link key={m.id} to={`/employees/${m.id}`}
                        className="text-xs border border-[#E5E5E5] px-2 py-1 hover:border-[#0A0A0A] transition">
                        {m.name} {m.designation && <span className="text-[#9A9A9A]">· {m.designation}</span>}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* site info */}
            <div className="border border-[#E5E5E5] p-5">
              <div className="overline mb-4">SITE / SCHEDULE</div>
              <dl className="space-y-2 text-sm">
                <Row k="Site address" v={p.site_address || "—"} />
                <Row k="Site area" v={p.site_area_sqft ? `${p.site_area_sqft} sq.ft` : "—"} />
                <Row k="Start date" v={p.start_date || "—"} />
                <Row k="End date" v={p.end_date || "—"} />
                <Row k="Created" v={(p.created_at || "").slice(0, 10)} />
              </dl>
            </div>
          </div>
        </div>
      )}

      {tab === "Tasks" && (
        <div className="space-y-2">
          {(p.tasks || []).length === 0 && <Empty text="No tasks yet. Add them from the Tasks page." />}
          {(p.tasks || []).map((t) => (
            <button key={t.id} onClick={() => navigate(`/tasks/${t.id}`)}
              className="w-full text-left border border-[#E5E5E5] p-3 flex items-center justify-between hover:border-[#0A0A0A] transition"
              data-testid={`project-task-${t.id}`}>
              <div>
                <div className="font-semibold text-sm">{t.title}</div>
                <div className="text-xs text-[#5C5C5C]">
                  {[t.area, t.category].filter(Boolean).join(" · ") || null}
                  {(t.area || t.category) && " · "}
                  Due {t.due_date || "—"} · {t.assignee_name || "Unassigned"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 bg-[#F5F5F5] text-[#5C5C5C]">{t.status_detail || t.status}</span>
                <span className={`status-chip chip-${t.priority}`}>{t.priority}</span>
                <CaretRight size={12} className="text-[#9A9A9A]" />
              </div>
            </button>
          ))}
        </div>
      )}

      {tab === "Milestones" && (
        <div className="space-y-3">
          {canFinance && (
            <div className="flex justify-end">
              <button onClick={() => setShowMsForm(!showMsForm)} className="btn-primary" data-testid="add-milestone-btn">
                <Plus size={14} /> {showMsForm ? "Cancel" : "Add milestone"}
              </button>
            </div>
          )}
          {showMsForm && (
            <form onSubmit={addMilestone} className="card-flat grid grid-cols-1 md:grid-cols-4 gap-3">
              <input className="input-flat" placeholder="Milestone name" required value={msForm.name} onChange={(e) => setMsForm({ ...msForm, name: e.target.value })} data-testid="ms-name" />
              <input className="input-flat" type="number" placeholder="Amount (₹)" required value={msForm.amount} onChange={(e) => setMsForm({ ...msForm, amount: e.target.value })} data-testid="ms-amount" />
              <input className="input-flat" type="date" value={msForm.due_date} onChange={(e) => setMsForm({ ...msForm, due_date: e.target.value })} />
              <button className="btn-primary" data-testid="ms-submit">Save</button>
            </form>
          )}
          {(p.milestones || []).length === 0 && <Empty text="No payment milestones yet." />}
          {(p.milestones || []).map((m) => (
            <div key={m.id} className="border border-[#E5E5E5] p-3 flex items-center justify-between" data-testid={`milestone-${m.id}`}>
              <div>
                <div className="font-semibold text-sm">{m.name}</div>
                <div className="text-xs text-[#5C5C5C]">Due {m.due_date || "—"}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono font-semibold">{inr(m.amount)}</span>
                <span className={`status-chip chip-${m.status || "pending"}`}>{m.status || "pending"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Vendors" && (
        <div className="space-y-6">
          <div>
            <div className="overline mb-3">PURCHASE ORDERS</div>
            {(p.purchase_orders || []).length === 0 && <Empty text="No purchase orders linked to this project." />}
            <div className="space-y-2">
              {(p.purchase_orders || []).map((po) => (
                <button key={po.id} onClick={() => navigate("/purchase-orders")}
                  className="w-full text-left border border-[#E5E5E5] p-3 flex items-center justify-between hover:border-[#0A0A0A] transition">
                  <div>
                    <div className="font-mono font-semibold text-sm">{po.po_number}</div>
                    <div className="text-xs text-[#5C5C5C]">{po.vendor_name || "—"}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-semibold">{inr(po.total)}</span>
                    <span className={`status-chip chip-${po.status}`}>{po.status}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="overline mb-3">VENDOR BILLS</div>
            {(p.vendor_bills || []).length === 0 && <Empty text="No vendor bills linked to this project." />}
            <div className="space-y-2">
              {(p.vendor_bills || []).map((b) => (
                <button key={b.id} onClick={() => b.vendor_id && navigate(`/vendors/${b.vendor_id}`)}
                  className="w-full text-left border border-[#E5E5E5] p-3 flex items-center justify-between hover:border-[#0A0A0A] transition">
                  <div>
                    <div className="font-mono font-semibold text-sm">{b.bill_number || b.id}</div>
                    <div className="text-xs text-[#5C5C5C]">{b.vendor_name || "—"} · {b.bill_date || "—"}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-semibold">{inr(b.total)}</span>
                    <span className={`status-chip chip-${b.status}`}>{b.status}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "Files" && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => setShowFileForm(!showFileForm)} className="btn-primary" data-testid="add-file-btn">
              <Plus size={14} /> Add file link
            </button>
          </div>
          {showFileForm && (
            <form onSubmit={addFile} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3">
              <input className="input-flat" placeholder="File name" required value={fileForm.name} onChange={(e) => setFileForm({ ...fileForm, name: e.target.value })} />
              <input className="input-flat" placeholder="URL" required value={fileForm.url} onChange={(e) => setFileForm({ ...fileForm, url: e.target.value })} />
              <input className="input-flat" placeholder="Stage (e.g. Concept)" value={fileForm.stage} onChange={(e) => setFileForm({ ...fileForm, stage: e.target.value })} />
              <button className="btn-primary md:col-span-3">Save</button>
            </form>
          )}
          {(p.files || []).length === 0 && <Empty text="No files yet." />}
          {(p.files || []).map((f) => (
            <div key={f.id} className="border border-[#E5E5E5] p-3 flex items-center justify-between hover:border-[#0A0A0A] transition group">
              <a href={f.url} target="_blank" rel="noreferrer" className="flex-1 min-w-0">
                <div className="font-semibold text-sm">{f.name}</div>
                <div className="text-xs text-[#5C5C5C]">{f.stage || "—"} · v{f.version || 1} · {f.uploader_name}</div>
              </a>
              <div className="flex items-center gap-2">
                <a href={f.url} target="_blank" rel="noreferrer" className="overline">OPEN →</a>
                <button onClick={() => deleteFile(f.id)} className="btn-ghost p-1 text-[#B22B22] opacity-0 group-hover:opacity-100 transition" title="Remove" data-testid={`file-delete-${f.id}`}>
                  <Trash size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Invoices" && (
        <div className="space-y-2">
          {(p.invoices || []).length === 0 && <Empty text="No invoices yet." />}
          {(p.invoices || []).map((i) => (
            <div key={i.id} className="border border-[#E5E5E5] p-3 flex items-center justify-between">
              <div>
                <div className="font-mono font-semibold text-sm">{i.number}</div>
                <div className="text-xs text-[#5C5C5C]">{i.doc_type} · Due {i.due_date || "—"}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="font-mono font-semibold">{inr(i.total)}</div>
                <span className={`status-chip chip-${i.status}`}>{i.status}</span>
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
          <form onSubmit={saveEdit} className="bg-white border border-[#0A0A0A] w-full max-w-lg p-6 space-y-3 max-h-[85vh] overflow-y-auto" data-testid="project-edit-modal">
            <div className="flex items-center justify-between">
              <div className="overline">EDIT PROJECT</div>
              <button type="button" onClick={() => setEditOpen(false)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <input required className="input-flat w-full" placeholder="Project name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="edit-project-name" />
            <div className="grid grid-cols-2 gap-3">
              <select className="input-flat" value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
                {TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <input className="input-flat" type="number" placeholder="Budget (₹)" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} data-testid="edit-project-budget" />
              <label className="text-xs text-[#5C5C5C]">Start date
                <input className="input-flat w-full mt-1" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
              </label>
              <label className="text-xs text-[#5C5C5C]">End date
                <input className="input-flat w-full mt-1" type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              </label>
            </div>
            <input className="input-flat w-full" placeholder="Site address" value={form.site_address} onChange={(e) => setForm({ ...form, site_address: e.target.value })} />
            <input className="input-flat w-full" type="number" placeholder="Site area (sq.ft)" value={form.site_area_sqft} onChange={(e) => setForm({ ...form, site_area_sqft: e.target.value })} />
            <textarea className="input-flat w-full" rows="2" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 flex items-center gap-2"><Warning size={12} /> {err}</div>}
            <button className="btn-primary w-full" data-testid="edit-project-save">Save changes</button>
          </form>
        </div>
      )}

      {/* Team modal */}
      {teamOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setTeamOpen(false); }}>
          <form onSubmit={saveTeam} className="bg-white border border-[#0A0A0A] w-full max-w-lg p-6 space-y-4 max-h-[85vh] overflow-y-auto" data-testid="team-modal">
            <div className="flex items-center justify-between">
              <div className="overline">ASSIGN TEAM</div>
              <button type="button" onClick={() => setTeamOpen(false)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <label className="block">
              <div className="overline text-[10px] mb-1">PROJECT MANAGER</div>
              <select className="input-flat w-full" value={teamForm.project_manager_id}
                onChange={(e) => setTeamForm({ ...teamForm, project_manager_id: e.target.value })}
                data-testid="team-pm-select">
                <option value="">Unassigned</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.name} {emp.designation ? `· ${emp.designation}` : ""}</option>
                ))}
              </select>
            </label>
            <div>
              <div className="overline text-[10px] mb-2">TEAM MEMBERS</div>
              {employees.length === 0 && <div className="text-sm text-[#9A9A9A]">No employees found. Add them in the Employees module.</div>}
              <div className="max-h-56 overflow-y-auto border border-[#E5E5E5] divide-y divide-[#F0F0F0]">
                {employees.map((emp) => (
                  <label key={emp.id} className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-[#FAFAFA]">
                    <input type="checkbox"
                      checked={teamForm.team_ids.includes(emp.id)}
                      onChange={(e) => setTeamForm((f) => ({
                        ...f,
                        team_ids: e.target.checked
                          ? [...f.team_ids, emp.id]
                          : f.team_ids.filter((x) => x !== emp.id),
                      }))} />
                    <span className="font-semibold">{emp.name}</span>
                    <span className="text-xs text-[#9A9A9A]">{emp.designation || emp.department || ""}</span>
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
    <div className="border-r border-b border-[#E5E5E5] p-5">
      <div className="overline mb-2">{label}</div>
      <div className="font-display font-bold tracking-tight text-2xl tabular-nums" style={accent ? { color: accent } : undefined}>{value}</div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-[#5C5C5C]">{k}</dt>
      <dd className="font-semibold">{v}</dd>
    </div>
  );
}

function Empty({ text }) {
  return <p className="text-[#5C5C5C] text-sm border border-dashed border-[#E5E5E5] p-6 text-center">{text}</p>;
}
