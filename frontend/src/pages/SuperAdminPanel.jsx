import { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import {
  Crown, Plus, Buildings, Users, Briefcase, CurrencyInr,
  Trash, ShieldCheck, PauseCircle, PlayCircle, Warning, Check,
  Sparkle, ArrowRight, Key, PencilSimpleLine, ChartLineUp, UserCirclePlus,
} from "@phosphor-icons/react";

function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}

function fmtMoney(n) {
  return "₹" + (n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export default function SuperAdminPanel() {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editOrg, setEditOrg] = useState(null);
  const [resetForOrg, setResetForOrg] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [reassignUser, setReassignUser] = useState(null);
  const [healthOrg, setHealthOrg] = useState(null);
  const [isoResult, setIsoResult] = useState(null);
  const [isoBusy, setIsoBusy] = useState(false);

  const runIsolationCheck = async () => {
    setIsoBusy(true);
    try {
      const r = await api.get("/platform/isolation-check");
      setIsoResult(r.data);
    } catch (e) {
      alert(fmtErr(e?.response?.data?.detail, "Isolation check failed"));
    } finally {
      setIsoBusy(false);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const [o, a, p] = await Promise.all([
        api.get("/platform/orgs"),
        api.get("/platform/analytics"),
        api.get("/platform/pending-signups").catch(() => ({ data: [] })),
      ]);
      setOrgs(o.data);
      setAnalytics(a.data);
      setPending(p.data);
      setErr("");
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Failed to load"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const changeStatus = async (org, action) => {
    if (!window.confirm(`${action.toUpperCase()} "${org.name}"? Users will be logged out immediately.`)) return;
    try {
      await api.post(`/platform/orgs/${org.org_id}/status`, { action });
      await load();
    } catch (e) {
      alert(fmtErr(e?.response?.data?.detail, "Status change failed"));
    }
  };

  const deleteOrg = async (org, purge) => {
    try {
      await api.delete(`/platform/orgs/${org.org_id}${purge ? "?purge=true" : ""}`);
      setConfirmDelete(null);
      await load();
    } catch (e) {
      alert(fmtErr(e?.response?.data?.detail, "Delete failed"));
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-16 w-96"></div>
        <div className="grid grid-cols-4 gap-4">{[1,2,3,4].map(i => <div key={i} className="skeleton h-24"></div>)}</div>
        <div className="skeleton h-96 w-full"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8" data-testid="super-admin-page">
      <PageHero
        eyebrow="PLATFORM · SUPER ADMIN"
        title="One studio to rule them all."
        kicker="Create, monitor and control every company workspace on the platform."
        count={orgs.length}
      >
        <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="create-org-btn">
          <Plus size={14} /> Create workspace
        </button>
      </PageHero>

      {err && (
        <div className="border border-[#B22B22] bg-[#FCEEEC] p-4 text-sm text-[#B22B22] flex items-center gap-2">
          <Warning size={16} /> {err}
        </div>
      )}

      {/* Platform KPIs */}
      {analytics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI icon={Buildings} label="ACTIVE WORKSPACES"
               value={analytics.orgs.active} total={analytics.orgs.total}
               tone="#8B7F6A" testid="kpi-active-orgs" />
          <KPI icon={Users} label="TOTAL USERS"
               value={analytics.users.active} total={analytics.users.total}
               tone="#1D633E" testid="kpi-users" />
          <KPI icon={Briefcase} label="TOTAL PROJECTS"
               value={analytics.projects} tone="#7A1FA2" testid="kpi-projects" />
          <KPI icon={CurrencyInr} label="PLATFORM REVENUE"
               display={fmtMoney(analytics.revenue_total)} tone="#B87500" testid="kpi-revenue" />
        </div>
      )}

      {analytics?.leaderboard?.length > 0 && (
        <div className="card-flat">
          <div className="flex items-center justify-between mb-4">
            <div className="overline"><ChartLineUp size={11} className="inline mr-1"/> REVENUE LEADERBOARD · TOP 5</div>
          </div>
          <div className="space-y-2">
            {analytics.leaderboard.map((row, i) => (
              <div key={row.org_id} className="flex items-center gap-3 p-2 border border-[#F0F0F0] hover:bg-[#FAFAFA]">
                <div className="font-mono text-xs w-8 text-[#9A9A9A]">#{i + 1}</div>
                <div className="flex-1 font-semibold text-sm">{row.name}</div>
                <div className="font-mono text-sm accent-blue">{fmtMoney(row.revenue)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending Google signups needing org assignment */}
      {pending.length > 0 && (
        <div className="card-flat border-l-4 border-l-[#B87500]" data-testid="pending-signups-card">
          <div className="flex items-center justify-between mb-3">
            <div className="overline text-[#B87500]">
              <Warning size={11} className="inline mr-1"/> PENDING GOOGLE SIGNUPS · {pending.length}
            </div>
          </div>
          <div className="text-xs text-[#5C5C5C] mb-3">
            These users signed in with Google but their email domain didn't match any workspace. Assign each to a company below.
          </div>
          <div className="space-y-2">
            {pending.map((u) => (
              <div key={u.user_id} className="flex flex-wrap items-center gap-3 p-2 border border-[#F0F0F0] hover:bg-[#FAFAFA]"
                   data-testid={`pending-row-${u.user_id}`}>
                <div className="w-8 h-8 bg-[#F0F0F0] flex items-center justify-center font-mono text-xs">
                  {(u.name || u.email || "?").slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm truncate">{u.name || u.email}</div>
                  <div className="text-xs text-[#5C5C5C]">{u.email}</div>
                </div>
                <div className="text-xs font-mono text-[#5C5C5C]">
                  Signed up {(u.created_at || "").slice(0,10)}
                </div>
                <button onClick={() => setReassignUser(u)} className="btn-primary text-xs" data-testid={`assign-${u.user_id}`}>
                  <UserCirclePlus size={12}/> Assign to workspace
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tenant isolation verification */}
      <div className="card-flat" data-testid="isolation-check-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="overline"><ShieldCheck size={11} className="inline mr-1"/> TENANT ISOLATION</div>
            <div className="text-xs text-[#5C5C5C] mt-1">
              Verify every business record is attributed to a valid workspace — no cross-tenant leakage.
            </div>
          </div>
          <button onClick={runIsolationCheck} disabled={isoBusy} className="btn-primary text-xs"
                  data-testid="run-isolation-check">
            {isoBusy ? "Checking…" : "Run isolation check"}
          </button>
        </div>
        {isoResult && (
          <div className="mt-4 border-t border-[#F0F0F0] pt-4" data-testid="isolation-result">
            <div className="flex items-center gap-3">
              <span className={`text-[11px] font-mono uppercase px-2.5 py-1 ${isoResult.status === "PASS"
                ? "bg-[#EFF7EF] text-[#1D633E]" : "bg-[#FCEEEC] text-[#B22B22]"}`}>
                {isoResult.status}
              </span>
              <span className="text-xs text-[#5C5C5C]">
                {isoResult.collections_checked} collections · {isoResult.organisations} workspaces · {(isoResult.checked_at || "").slice(0, 19).replace("T", " ")}
              </span>
            </div>
            {(isoResult.problems || []).length > 0 && (
              <div className="mt-3 space-y-1">
                {isoResult.problems.map((p) => (
                  <div key={p.collection} className="text-xs font-mono text-[#B22B22]">
                    {p.collection}: {p.missing_org_id} missing org · {p.unknown_org_id} unknown org
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Orgs table */}
      <div className="card-flat p-0 overflow-hidden">
        <div className="p-6 pb-4">
          <div className="overline">WORKSPACES · {orgs.length}</div>
        </div>
        <div className="overflow-x-auto">
        <div className="overflow-x-auto"><table className="w-full min-w-[900px]" data-testid="orgs-table">
          <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Workspace</Th>
              <Th>Mode</Th>
              <Th>Slug</Th>
              <Th>Plan</Th>
              <Th>Users</Th>
              <Th>Projects</Th>
              <Th>Status</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {orgs.map((o) => (
              <tr key={o.org_id} className="row-hover border-b border-[#F0F0F0]" data-testid={`org-row-${o.org_id}`}>
                <Td>
                  <div className="flex items-center gap-3">
                    {o.branding?.logo_url ? (
                      <img src={o.branding.logo_url} alt="" className="w-8 h-8 object-contain ring-1 ring-[#E5E5E5] bg-white" />
                    ) : (
                      <div className="w-8 h-8 flex items-center justify-center text-white font-display font-bold text-xs"
                           style={{ backgroundColor: o.branding?.primary_color || "#8B7F6A" }}>
                        {(o.name || "?").slice(0, 2).toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0">
                      <div className="font-semibold text-sm truncate flex items-center gap-2">
                        {o.name} {o.is_default && <span className="overline text-[9px] accent-blue">DEFAULT</span>}
                      </div>
                      <div className="text-xs text-[#5C5C5C]">{o.industry || "—"}</div>
                    </div>
                  </div>
                </Td>
                <Td className="font-mono text-xs">{o.slug}</Td>
                <Td>
                  {(() => {
                    const tone = { consultancy: "bg-[#F5F4F0] text-[#8B7F6A]",
                                   turnkey: "bg-[#FFF4E5] text-[#7A4E1A]",
                                   hybrid: "bg-[#EFF7EF] text-[#1D633E]" }[o.business_mode || "hybrid"];
                    return <span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${tone}`}>{o.business_mode || "hybrid"}</span>;
                  })()}
                </Td>
                <Td>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#F5F4F0] text-[#8B7F6A]">{o.plan || "starter"}</span>
                </Td>
                <Td className="font-mono text-xs tabular-nums">{o.stats?.users ?? 0}</Td>
                <Td className="font-mono text-xs tabular-nums">{o.stats?.projects ?? 0}</Td>
                <Td>
                  {o.is_suspended ? (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#FFF4E5] text-[#7A4E1A]">suspended</span>
                  ) : o.is_active === false ? (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#FCEEEC] text-[#B22B22]">deactivated</span>
                  ) : (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#EFF7EF] text-[#1D633E]">active</span>
                  )}
                </Td>
                <Td className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button title="Health & limits" onClick={() => setHealthOrg(o)} className="btn-ghost text-xs" data-testid={`health-org-${o.org_id}`}>
                      <ChartLineUp size={12} />
                    </button>
                    <button title="Edit" onClick={() => setEditOrg(o)} className="btn-ghost text-xs" data-testid={`edit-org-${o.org_id}`}>
                      <PencilSimpleLine size={12} />
                    </button>
                    {!o.is_default && (o.is_suspended ? (
                      <button title="Activate" onClick={() => changeStatus(o, "activate")}
                              className="btn-ghost text-xs text-[#1D633E]" data-testid={`activate-${o.org_id}`}>
                        <PlayCircle size={13} />
                      </button>
                    ) : (
                      <button title="Suspend" onClick={() => changeStatus(o, "suspend")}
                              className="btn-ghost text-xs text-[#B87500]" data-testid={`suspend-${o.org_id}`}>
                        <PauseCircle size={13} />
                      </button>
                    ))}
                    <button title="Manage admins" onClick={() => setResetForOrg(o)}
                            className="btn-ghost text-xs" data-testid={`admins-${o.org_id}`}>
                      <ShieldCheck size={12} />
                    </button>
                    {!o.is_default && (
                      <button title="Delete" onClick={() => setConfirmDelete(o)}
                              className="btn-ghost text-xs text-[#B22B22]" data-testid={`delete-${o.org_id}`}>
                        <Trash size={12} />
                      </button>
                    )}
                  </div>
                </Td>
              </tr>
            ))}
            {orgs.length === 0 && (
              <tr><td colSpan={8} className="p-12 text-center text-[#5C5C5C]">
                No workspaces yet. Click <em>Create workspace</em> to spin up the first tenant.
              </td></tr>
            )}
          </tbody>
        </table></div>
        </div>
      </div>

      {showCreate && <CreateOrgModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {editOrg && <EditOrgModal org={editOrg} onClose={() => setEditOrg(null)} onSaved={() => { setEditOrg(null); load(); }} />}
      {resetForOrg && <OrgAdminsModal org={resetForOrg} onClose={() => setResetForOrg(null)} />}
      {confirmDelete && <ConfirmDeleteModal org={confirmDelete} onClose={() => setConfirmDelete(null)} onConfirm={deleteOrg} />}
      {reassignUser && <ReassignModal user={reassignUser} orgs={orgs} onClose={() => setReassignUser(null)} onDone={() => { setReassignUser(null); load(); }} />}
      {healthOrg && <OrgHealthModal org={healthOrg} onClose={() => setHealthOrg(null)} onSaved={() => { load(); }} />}
    </div>
  );
}

function ReassignModal({ user, orgs, onClose, onDone }) {
  const [orgId, setOrgId] = useState(orgs[0]?.org_id || "");
  const [role, setRole] = useState("Employee");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    if (!orgId) return;
    setBusy(true); setErr("");
    try {
      await api.post(`/platform/users/${user.user_id}/reassign-org`, {
        org_id: orgId, role, approve: true,
      });
      onDone();
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Reassign failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title={user.name || user.email} eyebrow="ASSIGN TO WORKSPACE">
      <div className="text-sm text-[#5C5C5C] mb-3">
        Move <b>{user.email}</b> into an existing workspace and set their role. They'll be able to log in immediately.
      </div>
      <div className="space-y-3">
        <label className="block">
          <div className="text-xs text-[#5C5C5C] mb-1">Target workspace</div>
          <select className="input-flat w-full" value={orgId} onChange={(e) => setOrgId(e.target.value)}
                  data-testid="reassign-org-select">
            {orgs.map((o) => <option key={o.org_id} value={o.org_id}>{o.name}</option>)}
          </select>
        </label>
        <label className="block">
          <div className="text-xs text-[#5C5C5C] mb-1">Role in workspace</div>
          <select className="input-flat w-full" value={role} onChange={(e) => setRole(e.target.value)}
                  data-testid="reassign-role-select">
            {["Employee","Designer","ProjectManager","Accountant","HR","Director","Admin"].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} onClick={submit} className="btn-primary" data-testid="reassign-submit">
            {busy ? "Assigning…" : "Assign & Approve"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ------- KPI card ------- */
function KPI({ icon: Icon, label, value, total, display, tone, testid }) {
  return (
    <div className="card-flat p-5 relative overflow-hidden group hover:-translate-y-0.5 transition" data-testid={testid}>
      <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: tone }} />
      <div className="flex items-start justify-between mb-3">
        <Icon size={22} style={{ color: tone }} weight="duotone" />
      </div>
      <div className="overline text-[10px] text-[#5C5C5C] mb-1">{label}</div>
      <div className="font-display font-bold tracking-tighter text-3xl tabular-nums">
        {display ?? value}
        {typeof total === "number" && (
          <span className="text-sm text-[#9A9A9A] font-normal ml-1">/{total}</span>
        )}
      </div>
    </div>
  );
}

/* ------- Create org modal ------- */
function CreateOrgModal({ onClose, onCreated }) {
  const [f, setF] = useState({
    name: "", admin_name: "", admin_email: "", admin_password: "",
    plan: "starter", gstin: "", industry: "Architecture & Interior Design",
    business_mode: "hybrid",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      await api.post("/platform/orgs", f);
      onCreated();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title="Create Workspace" eyebrow="NEW TENANT">
      <form onSubmit={submit} className="space-y-4" data-testid="create-org-form">
        <div className="overline text-[#8B7F6A]">01 · BUSINESS MODE</div>
        <div className="grid grid-cols-3 gap-3">
          {[
            {k:"consultancy", t:"Consultancy", d:"Design-only studio. CRM, projects, quotations, HR, accounting — without procurement."},
            {k:"turnkey",     t:"Turnkey",     d:"End-to-end delivery. Adds POs, GRN, inventory, material tracking, project costing."},
            {k:"hybrid",      t:"Hybrid",      d:"Both modes in one workspace. Each project picks its own engagement type."},
          ].map(o => (
            <button key={o.k} type="button"
              onClick={() => setF({...f, business_mode: o.k})}
              className={`text-left p-3 border transition ${f.business_mode === o.k ? "border-[#8B7F6A] bg-[#F5F4F0]" : "border-[#E5E5E5] hover:border-[#0A0A0A]"}`}
              data-testid={`mode-${o.k}`}>
              <div className="font-display font-bold tracking-tighter text-base mb-1">{o.t}</div>
              <div className="text-[10px] text-[#5C5C5C] leading-relaxed">{o.d}</div>
            </button>
          ))}
        </div>

        <div className="overline text-[#8B7F6A]">02 · WORKSPACE</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input required data-testid="co-name" className="input-flat" placeholder="Company / Studio name *"
                 value={f.name} onChange={(e) => setF({...f, name: e.target.value})} />
          <input className="input-flat" placeholder="Industry"
                 value={f.industry} onChange={(e) => setF({...f, industry: e.target.value})} />
          <select className="input-flat" value={f.plan}
                  onChange={(e) => setF({...f, plan: e.target.value})}>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
          <input className="input-flat" placeholder="GSTIN (optional)"
                 value={f.gstin} onChange={(e) => setF({...f, gstin: e.target.value})} />
        </div>
        <div className="overline text-[#8B7F6A]">03 · FIRST ADMIN</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input required data-testid="co-admin-name" className="input-flat" placeholder="Admin name *"
                 value={f.admin_name} onChange={(e) => setF({...f, admin_name: e.target.value})} />
          <input required type="email" data-testid="co-admin-email" className="input-flat" placeholder="Admin email *"
                 value={f.admin_email} onChange={(e) => setF({...f, admin_email: e.target.value})} />
          <input required minLength={8} data-testid="co-admin-password" className="input-flat" placeholder="Password (letters + digits, min 8) *"
                 value={f.admin_password} onChange={(e) => setF({...f, admin_password: e.target.value})} />
        </div>
        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} className="btn-primary" data-testid="co-submit">
            {busy ? "Creating…" : (<><Sparkle size={12} /> Create workspace</>)}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/* ------- Edit org modal ------- */
function EditOrgModal({ org, onClose, onSaved }) {
  const [f, setF] = useState({
    display_name: org.display_name || org.name, phone: org.phone || "",
    website: org.website || "", gstin: org.gstin || "", pan: org.pan || "",
    plan: org.plan || "starter", industry: org.industry || "",
    business_mode: org.business_mode || "hybrid",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      await api.patch(`/platform/orgs/${org.org_id}`, f);
      onSaved();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Update failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title={`Edit · ${org.name}`} eyebrow="WORKSPACE INFO">
      <form onSubmit={submit} className="space-y-3" data-testid="edit-org-form">
        <label className="block">
          <div className="text-xs text-[#5C5C5C] mb-1">Business mode</div>
          <select className="input-flat w-full" value={f.business_mode}
                  onChange={(e) => setF({...f, business_mode: e.target.value})}
                  data-testid="edit-mode">
            <option value="consultancy">Consultancy</option>
            <option value="turnkey">Turnkey</option>
            <option value="hybrid">Hybrid</option>
          </select>
          {f.business_mode !== org.business_mode && (
            <div className="text-[11px] text-[#B87500] mt-1">
              ⚠ Changing mode will enable/disable modules for this workspace.
            </div>
          )}
        </label>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input className="input-flat" placeholder="Display name"
                 value={f.display_name} onChange={(e) => setF({...f, display_name: e.target.value})} />
          <input className="input-flat" placeholder="Industry"
                 value={f.industry} onChange={(e) => setF({...f, industry: e.target.value})} />
          <input className="input-flat" placeholder="Phone"
                 value={f.phone} onChange={(e) => setF({...f, phone: e.target.value})} />
          <input className="input-flat" placeholder="Website"
                 value={f.website} onChange={(e) => setF({...f, website: e.target.value})} />
          <input className="input-flat" placeholder="GSTIN"
                 value={f.gstin} onChange={(e) => setF({...f, gstin: e.target.value})} />
          <input className="input-flat" placeholder="PAN"
                 value={f.pan} onChange={(e) => setF({...f, pan: e.target.value})} />
          <select className="input-flat" value={f.plan}
                  onChange={(e) => setF({...f, plan: e.target.value})}>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>
        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} className="btn-primary">{busy ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

/* ------- Manage Admins modal (list + create + reset) ------- */
function OrgAdminsModal({ org, onClose }) {
  const [users, setUsers] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [resetting, setResetting] = useState(null);
  const [err, setErr] = useState("");
  const load = async () => {
    try {
      const { data } = await api.get(`/platform/orgs/${org.org_id}/users`);
      setUsers(data);
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail));
    }
  };
  useEffect(() => { load(); }, [org.org_id]);

  const [newAdmin, setNewAdmin] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const createAdmin = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api.post(`/platform/orgs/${org.org_id}/admins`, newAdmin);
      setNewAdmin({ name: "", email: "", password: "" });
      setShowCreate(false);
      await load();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };
  const doReset = async (uid, pw) => {
    try {
      await api.post(`/platform/orgs/${org.org_id}/users/${uid}/reset-password`, { new_password: pw });
      setResetting(null);
      await load();
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Reset failed"));
    }
  };

  return (
    <Modal onClose={onClose} title={org.name} eyebrow="ADMINS & USERS" wide>
      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 mb-3">{err}</div>}
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-[#5C5C5C]">{users.length} users in this workspace</div>
        <button onClick={() => setShowCreate(!showCreate)} className="btn-ghost text-xs">
          <Plus size={11} /> Add admin
        </button>
      </div>
      {showCreate && (
        <form onSubmit={createAdmin} className="border border-[#E5E5E5] p-3 mb-4 grid grid-cols-1 md:grid-cols-4 gap-2">
          <input required className="input-flat" placeholder="Name" value={newAdmin.name}
                 onChange={(e) => setNewAdmin({...newAdmin, name: e.target.value})} />
          <input required type="email" className="input-flat" placeholder="Email" value={newAdmin.email}
                 onChange={(e) => setNewAdmin({...newAdmin, email: e.target.value})} />
          <input required minLength={6} className="input-flat" placeholder="Password" value={newAdmin.password}
                 onChange={(e) => setNewAdmin({...newAdmin, password: e.target.value})} />
          <button disabled={busy} className="btn-primary text-xs">{busy ? "…" : "Create Admin"}</button>
        </form>
      )}
      <div className="overflow-x-auto"><table className="w-full">
        <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]">
          <tr className="text-left"><Th>Name</Th><Th>Email</Th><Th>Role</Th><Th className="text-right">Actions</Th></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.user_id} className="border-b border-[#F0F0F0]">
              <Td className="font-semibold text-sm">{u.name}</Td>
              <Td className="font-mono text-xs">{u.email}</Td>
              <Td><span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#F5F4F0] text-[#8B7F6A]">{u.role}</span></Td>
              <Td className="text-right">
                <button onClick={() => setResetting(u.user_id)} className="btn-ghost text-xs">
                  <Key size={11} /> Reset password
                </button>
                {resetting === u.user_id && (
                  <ResetInline onCancel={() => setResetting(null)}
                               onConfirm={(pw) => doReset(u.user_id, pw)} />
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </Modal>
  );
}

function ResetInline({ onCancel, onConfirm }) {
  const [pw, setPw] = useState("");
  return (
    <div className="mt-2 flex items-center gap-2 justify-end">
      <input type="text" className="input-flat text-xs" placeholder="New password"
             value={pw} onChange={(e) => setPw(e.target.value)} style={{ width: 160 }} />
      <button onClick={() => onConfirm(pw)} className="btn-primary text-xs" disabled={pw.length < 6}>Set</button>
      <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
    </div>
  );
}

/* ------- Confirm delete modal ------- */
function ConfirmDeleteModal({ org, onClose, onConfirm }) {
  const [purge, setPurge] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const canDelete = confirmText === org.name;
  return (
    <Modal onClose={onClose} title="Delete Workspace" eyebrow="DANGER ZONE">
      <div className="space-y-3">
        <div className="border border-[#B22B22] bg-[#FCEEEC] p-3 text-sm text-[#B22B22]">
          <div className="flex items-center gap-2 font-semibold mb-1">
            <Warning size={14} /> This action affects <em>{org.name}</em>.
          </div>
          Deactivating removes access but preserves data. Purging <strong>permanently deletes</strong> every project, invoice, user and record in this workspace.
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={purge} onChange={(e) => setPurge(e.target.checked)} />
          <span>Also permanently delete all workspace data (irreversible)</span>
        </label>
        <div className="text-xs text-[#5C5C5C]">Type <code className="font-mono bg-[#F0F0F0] px-1">{org.name}</code> to confirm.</div>
        <input className="input-flat w-full" value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
               data-testid="delete-confirm-input" />
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={!canDelete} onClick={() => onConfirm(org, purge)}
                  className="btn-primary bg-[#B22B22]" data-testid="delete-confirm-btn">
            <Trash size={12} /> {purge ? "Purge forever" : "Deactivate"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ------- Modal shell ------- */
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className={`bg-white p-6 w-full border border-[#E5E5E5] max-h-[92vh] overflow-y-auto ${wide ? "max-w-4xl" : "max-w-2xl"}`}>
        <div className="flex items-start justify-between mb-4">
          <div>
            {eyebrow && <div className="overline mb-1">{eyebrow}</div>}
            <div className="font-display font-bold tracking-tighter text-3xl">{title}</div>
          </div>
          <button onClick={onClose} className="btn-ghost">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm align-middle ${className}`}>{children}</td>;

function OrgHealthModal({ org, onClose, onSaved }) {
  const [health, setHealth] = useState(null);
  const [err, setErr] = useState("");
  const [limits, setLimits] = useState({ max_users: "", max_projects: "", plan: org.plan || "starter" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/platform/orgs/${org.org_id}/health`)
      .then((r) => {
        setHealth(r.data);
        setLimits({
          max_users: r.data?.usage?.users?.limit ?? "",
          max_projects: r.data?.usage?.projects?.limit ?? "",
          plan: r.data?.plan || "starter",
        });
      })
      .catch((e) => setErr(fmtErr(e?.response?.data?.detail, "Failed to load health")));
  }, [org.org_id]);

  const saveLimits = async () => {
    setBusy(true);
    try {
      const payload = { plan: limits.plan };
      if (limits.max_users) payload.max_users = Number(limits.max_users);
      if (limits.max_projects) payload.max_projects = Number(limits.max_projects);
      await api.patch(`/platform/orgs/${org.org_id}/limits`, payload);
      onSaved?.();
      onClose();
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Failed to save limits"));
    } finally {
      setBusy(false);
    }
  };

  const CountCell = ({ label, value }) => (
    <div className="border border-[#F0F0F0] p-2">
      <div className="text-[10px] font-mono uppercase text-[#9A9A9A]">{label}</div>
      <div className="font-mono text-sm tabular-nums">{value ?? "—"}</div>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6 space-y-5"
           onClick={(e) => e.stopPropagation()} data-testid="org-health-modal">
        <div className="flex items-start justify-between">
          <div>
            <div className="overline">TENANT HEALTH</div>
            <h3 className="font-display text-xl font-bold">{org.name}</h3>
          </div>
          <button onClick={onClose} className="btn-ghost text-xs">Close</button>
        </div>
        {err && <div className="text-xs text-[#B22B22] border border-[#B22B22] bg-[#FCEEEC] p-2">{err}</div>}
        {!health && !err && <div className="skeleton h-40 w-full" />}
        {health && (
          <>
            {(health.warnings || []).length > 0 && (
              <div className="border-l-4 border-l-[#B87500] bg-[#FFF9F0] p-3 space-y-1">
                {health.warnings.map((w, i) => (
                  <div key={i} className="text-xs text-[#7A4E1A]">{w}</div>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="border border-[#E5E5E5] p-3">
                <div className="text-[10px] font-mono uppercase text-[#9A9A9A]">USERS</div>
                <div className="font-mono text-lg">{health.usage.users.used}<span className="text-xs text-[#9A9A9A]"> / {health.usage.users.limit ?? "∞"}</span></div>
              </div>
              <div className="border border-[#E5E5E5] p-3">
                <div className="text-[10px] font-mono uppercase text-[#9A9A9A]">PROJECTS</div>
                <div className="font-mono text-lg">{health.usage.projects.used}<span className="text-xs text-[#9A9A9A]"> / {health.usage.projects.limit ?? "∞"}</span></div>
              </div>
            </div>
            <div>
              <div className="overline mb-2">RECORDS</div>
              <div className="grid grid-cols-4 gap-2">
                {Object.entries(health.counts || {}).filter(([, v]) => v !== null).map(([k, v]) => (
                  <CountCell key={k} label={k.replace(/_/g, " ")} value={v} />
                ))}
              </div>
            </div>
            <div className="text-xs text-[#5C5C5C]">
              Last login: <span className="font-mono">{(health.last_login || "never").slice(0, 19).replace("T", " ")}</span>
              {" · "}Active admins: <span className="font-mono">{health.admins}</span>
            </div>
            <div className="border-t border-[#F0F0F0] pt-4">
              <div className="overline mb-3">PLAN &amp; LIMITS</div>
              <div className="grid grid-cols-3 gap-3">
                <label className="text-xs space-y-1">
                  <span className="font-mono uppercase text-[#9A9A9A]">Plan</span>
                  <select value={limits.plan} onChange={(e) => setLimits({ ...limits, plan: e.target.value })}
                          className="input w-full" data-testid="limits-plan">
                    <option value="starter">starter</option>
                    <option value="pro">pro</option>
                    <option value="enterprise">enterprise</option>
                  </select>
                </label>
                <label className="text-xs space-y-1">
                  <span className="font-mono uppercase text-[#9A9A9A]">Max users</span>
                  <input type="number" min="1" value={limits.max_users}
                         onChange={(e) => setLimits({ ...limits, max_users: e.target.value })}
                         className="input w-full" data-testid="limits-max-users" />
                </label>
                <label className="text-xs space-y-1">
                  <span className="font-mono uppercase text-[#9A9A9A]">Max projects</span>
                  <input type="number" min="1" value={limits.max_projects}
                         onChange={(e) => setLimits({ ...limits, max_projects: e.target.value })}
                         className="input w-full" data-testid="limits-max-projects" />
                </label>
              </div>
              <div className="flex justify-end mt-4">
                <button onClick={saveLimits} disabled={busy} className="btn-primary text-xs" data-testid="save-limits-btn">
                  {busy ? "Saving…" : "Save limits"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
