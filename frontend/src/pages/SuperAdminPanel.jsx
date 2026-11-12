import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { API } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import { dateForInput, formatDate, statusLabel } from "../lib/format";
import {
  Crown, Plus, Buildings, Users, Briefcase, CalendarCheck,
  Trash, ShieldCheck, PauseCircle, PlayCircle, Warning, Check,
  Sparkle, ArrowRight, Key, PencilSimpleLine, ChartLineUp, UserCirclePlus,
  Faders, Copy, LinkSimple,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";

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
  const [contactRequests, setContactRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editOrg, setEditOrg] = useState(null);
  const [resetForOrg, setResetForOrg] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [reassignUser, setReassignUser] = useState(null);
  const [healthOrg, setHealthOrg] = useState(null);
  const [modulesOrg, setModulesOrg] = useState(null);
  const [supportOrg, setSupportOrg] = useState(null);
  const [isoResult, setIsoResult] = useState(null);
  const [isoBusy, setIsoBusy] = useState(false);

  const runIsolationCheck = async () => {
    setIsoBusy(true);
    try {
      const r = await api.get("/platform/isolation-check");
      setIsoResult(r.data);
    } catch (e) {
      toast.error(fmtErr(e?.response?.data?.detail, "Isolation check failed"));
    } finally {
      setIsoBusy(false);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const [o, a, p, c] = await Promise.all([
        api.get("/platform/orgs"),
        api.get("/platform/analytics"),
        api.get("/platform/pending-signups").catch(() => ({ data: [] })),
        api.get("/platform/contact-requests?limit=20").catch(() => ({ data: [] })),
      ]);
      setOrgs(o.data);
      setAnalytics(a.data);
      setPending(p.data);
      setContactRequests(c.data);
      setErr("");
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Failed to load"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const changeStatus = async (org, action) => {
    if (!await confirmAction(`${action.toUpperCase()} "${org.name}"? Users will be logged out immediately.`)) return;
    try {
      await api.post(`/platform/orgs/${org.org_id}/status`, { action });
      await load();
    } catch (e) {
      toast.error(fmtErr(e?.response?.data?.detail, "Status change failed"));
    }
  };

  const deleteOrg = async (org, purge, confirm) => {
    try {
      await api.delete(`/platform/orgs/${org.org_id}`, { params: purge ? { purge: true, confirm } : {} });
      toast.success(purge ? `${org.name} deleted permanently` : `${org.name} deactivated`);
      setConfirmDelete(purge ? null : { ...org, is_active: false });
      await load();
    } catch (e) {
      toast.error(fmtErr(e?.response?.data?.detail, "Delete failed"));
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
        title="Platform admin"
        kicker="Create, monitor and control every company workspace on the platform."
        count={orgs.length}
      >
        <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="create-org-btn">
          <Plus size={14} /> Create workspace
        </button>
      </PageHero>

      {err && (
        <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-4 text-sm text-[var(--danger)] flex items-center gap-2">
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
          <KPI icon={CalendarCheck} label="RENEWALS TO REVIEW"
               value={(analytics.renewals?.due_30_days || 0) + (analytics.renewals?.overdue || 0)}
               tone={analytics.renewals?.overdue ? "#A2352A" : "#7A4E1A"}
               testid="kpi-renewals" />
        </div>
      )}

      {analytics && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="platform-commercial">
          <div className="card-flat">
            <div className="overline mb-3"><ChartLineUp size={11} className="inline mr-1"/> WORKSPACES BY PLAN</div>
            <MixList rows={Object.fromEntries(Object.entries(analytics.plans || {}).filter(([, n]) => n))}
                     empty="No workspaces yet" />
            <div className="overline mt-5 mb-3">SUBSCRIPTION STATUS</div>
            <MixList rows={analytics.subscriptions} empty="No subscriptions set" />
          </div>
          <DueList title="RENEWALS DUE · NEXT 30 DAYS" rows={analytics.renewals_due} dateKey="renewal_date"
                   empty="No renewals in the next 30 days" testid="renewals-due" />
          <DueList title="TRIALS ENDING · NEXT 14 DAYS" rows={analytics.trials_ending} dateKey="trial_ends_on"
                   empty="No trials ending soon" testid="trials-ending" />
        </div>
      )}

      {/* Pending Google signups needing org assignment */}
      {pending.length > 0 && (
        <div className="card-flat border-l-4 border-l-[var(--warning)]" data-testid="pending-signups-card">
          <div className="flex items-center justify-between mb-3">
            <div className="overline text-[var(--warning)]">
              <Warning size={11} className="inline mr-1"/> PENDING GOOGLE SIGNUPS · {pending.length}
            </div>
          </div>
          <div className="text-xs text-[var(--ink-2)] mb-3">
            These users signed in with Google but their email domain didn't match any workspace. Assign each to a company below.
          </div>
          <div className="space-y-2">
            {pending.map((u) => (
              <div key={u.user_id} className="flex flex-wrap items-center gap-3 p-2 border border-[var(--line-soft)] hover:bg-[var(--surface-2)]"
                   data-testid={`pending-row-${u.user_id}`}>
                <div className="w-8 h-8 bg-[var(--line-soft)] flex items-center justify-center font-mono text-xs">
                  {(u.name || u.email || "?").slice(0,2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm truncate">{u.name || u.email}</div>
                  <div className="text-xs text-[var(--ink-2)]">{u.email}</div>
                </div>
                <div className="text-xs font-mono text-[var(--ink-2)]">
                  Signed up {formatDate(u.created_at)}
                </div>
                <button onClick={() => setReassignUser(u)} className="btn-primary text-xs" data-testid={`assign-${u.user_id}`}>
                  <UserCirclePlus size={12}/> Assign to workspace
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {contactRequests.length > 0 && (
        <div className="card-flat" data-testid="contact-requests-card">
          <div className="flex items-center justify-between mb-3">
            <div className="overline">DEMO REQUESTS · {contactRequests.length}</div>
            <span className="text-xs text-[var(--ink-3)]">Latest public enquiries</span>
          </div>
          <div className="divide-y divide-[var(--line-soft)]">
            {contactRequests.map((request) => (
              <div key={request.request_id} className="py-3 first:pt-0 last:pb-0 grid gap-1 md:grid-cols-[1fr_auto]">
                <div className="min-w-0">
                  <div className="font-semibold text-sm truncate">{request.name} · {request.company}</div>
                  <div className="text-xs text-[var(--ink-2)] break-words">
                    {request.message || "Demo enquiry"}
                  </div>
                  <div className="text-[10px] font-mono uppercase text-[var(--ink-3)] mt-1">
                    {request.type || "studio"} · {formatDate(request.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2 md:justify-end">
                  {request.phone && <span className="text-xs font-mono">{request.phone}</span>}
                  <a className="btn-ghost text-xs" href={`mailto:${request.email}`}>Email</a>
                </div>
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
            <div className="text-xs text-[var(--ink-2)] mt-1">
              Verify every business record is attributed to a valid workspace — no cross-tenant leakage.
            </div>
          </div>
          <button onClick={runIsolationCheck} disabled={isoBusy} className="btn-primary text-xs"
                  data-testid="run-isolation-check">
            {isoBusy ? "Checking…" : "Run isolation check"}
          </button>
        </div>
        {isoResult && (
          <div className="mt-4 border-t border-[var(--line-soft)] pt-4" data-testid="isolation-result">
            <div className="flex items-center gap-3">
              <span className={`text-[11px] font-mono uppercase px-2.5 py-1 ${isoResult.status === "PASS"
                ? "bg-[var(--success-soft)] text-[var(--success)]" : "bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
                {isoResult.status}
              </span>
              <span className="text-xs text-[var(--ink-2)]">
                {isoResult.collections_checked} collections · {isoResult.organisations} workspaces · {(isoResult.checked_at || "").slice(0, 19).replace("T", " ")}
              </span>
            </div>
            {(isoResult.problems || []).length > 0 && (
              <div className="mt-3 space-y-1">
                {isoResult.problems.map((p) => (
                  <div key={p.collection} className="text-xs font-mono text-[var(--danger)]">
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
        <table className="w-full min-w-[900px]" data-testid="orgs-table">
          <thead className="bg-[var(--surface-2)] border-y border-[var(--line)]">
            <tr className="text-left">
              <Th>Workspace</Th>
              <Th>Owner</Th>
              <Th>Mode</Th>
              <Th>Plan</Th>
              <Th>Amount</Th>
              <Th>Renewal</Th>
              <Th>Users</Th>
              <Th>Projects</Th>
              <Th>Status</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {orgs.map((o) => (
              <tr key={o.org_id} className="row-hover border-b border-[var(--line-soft)]" data-testid={`org-row-${o.org_id}`}>
                <Td>
                  <div className="flex items-center gap-3">
                    {o.branding?.logo_url ? (
                      <img src={o.branding.logo_url} alt="" className="w-8 h-8 object-contain ring-1 ring-[var(--line)] bg-white rounded-full" />
                    ) : (
                      <div className="w-8 h-8 flex items-center justify-center text-white font-display font-bold text-xs rounded-full"
                           style={{ backgroundColor: (!o.branding?.primary_color || o.branding.primary_color.toUpperCase() === "#002FA7") ? "#76705E" : o.branding.primary_color }}>
                        {(o.name || "?").slice(0, 2).toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0">
                      <div className="font-semibold text-sm truncate flex items-center gap-2">
                        {o.name} {o.is_default && <span className="overline text-[9px] accent-blue">DEFAULT</span>}
                      </div>
                      <div className="text-xs text-[var(--ink-2)]">{o.industry || "—"}</div>
                    </div>
                  </div>
                </Td>
                <Td>
                  <div className="text-sm truncate max-w-[160px]">{o.owner || "—"}</div>
                  {o.owner_email && <div className="text-[10px] text-[var(--ink-3)] truncate max-w-[160px]">{o.owner_email}</div>}
                </Td>
                <Td>
                  {(() => {
                    const tone = { consultancy: "bg-[var(--hover)] text-[#5F5A4B]",
                                   turnkey: "bg-[var(--warning-soft)] text-[var(--warning)]",
                                   hybrid: "bg-[var(--success-soft)] text-[var(--success)]" }[o.business_mode || "hybrid"];
                    return <span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${tone}`}>{o.business_mode || "hybrid"}</span>;
                  })()}
                </Td>
                <Td>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[var(--hover)] text-[#5F5A4B]">{o.plan || "starter"}</span>
                </Td>
                <Td className="font-mono text-xs tabular-nums">
                  {o.billing?.amount_charged != null ? fmtMoney(o.billing.amount_charged) : "—"}
                  {o.billing?.maintenance_charge != null && (
                    <div className="text-[10px] text-[var(--ink-3)]">+{fmtMoney(o.billing.maintenance_charge)} AMC</div>
                  )}
                </Td>
                <Td className="font-mono text-xs">{o.billing?.renewal_date ? formatDate(o.billing.renewal_date) : "—"}</Td>
                <Td className="font-mono text-xs tabular-nums">{o.stats?.users ?? 0}</Td>
                <Td className="font-mono text-xs tabular-nums">{o.stats?.projects ?? 0}</Td>
                <Td>
                  {o.is_suspended ? (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[var(--warning-soft)] text-[var(--warning)]">suspended</span>
                  ) : o.is_active === false ? (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[var(--danger-soft)] text-[var(--danger)]">deactivated</span>
                  ) : (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[var(--success-soft)] text-[var(--success)]">active</span>
                  )}
                  {!o.is_default && <SubscriptionControl org={o} onSaved={load} />}
                </Td>
                <Td className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button title="Health & limits" onClick={() => setHealthOrg(o)} className="btn-ghost text-xs" data-testid={`health-org-${o.org_id}`}>
                      <ChartLineUp size={12} />
                    </button>
                    <button title="Module access" onClick={() => setModulesOrg(o)} className="btn-ghost text-xs" data-testid={`modules-${o.org_id}`}>
                      <Faders size={12} />
                    </button>
                    <button title="Edit" onClick={() => setEditOrg(o)} className="btn-ghost text-xs" data-testid={`edit-org-${o.org_id}`}>
                      <PencilSimpleLine size={12} />
                    </button>
                    {!o.is_default && (o.is_suspended ? (
                      <button title="Activate" onClick={() => changeStatus(o, "activate")}
                              className="btn-ghost text-xs text-[var(--success)]" data-testid={`activate-${o.org_id}`}>
                        <PlayCircle size={13} />
                      </button>
                    ) : (
                      <button title="Suspend" onClick={() => changeStatus(o, "suspend")}
                              className="btn-ghost text-xs text-[var(--warning)]" data-testid={`suspend-${o.org_id}`}>
                        <PauseCircle size={13} />
                      </button>
                    ))}
                    <button title="Manage admins" onClick={() => setResetForOrg(o)}
                            className="btn-ghost text-xs" data-testid={`admins-${o.org_id}`}>
                      <ShieldCheck size={12} />
                    </button>
                    {o.is_active !== false && (
                      <button title="Support access" onClick={() => setSupportOrg(o)}
                              className="btn-ghost text-xs" data-testid={`support-${o.org_id}`}>
                        <Key size={12} />
                      </button>
                    )}
                    {!o.is_default && (
                      <button title="Delete" onClick={() => setConfirmDelete(o)}
                              className="btn-ghost text-xs text-[var(--danger)]" data-testid={`delete-${o.org_id}`}>
                        <Trash size={12} />
                      </button>
                    )}
                  </div>
                </Td>
              </tr>
            ))}
            {orgs.length === 0 && (
              <tr><td colSpan={10} className="p-12 text-center text-[var(--ink-2)]">
                No workspaces yet. Click <em>Create workspace</em> to spin up the first tenant.
              </td></tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {showCreate && <CreateOrgModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {editOrg && <EditOrgModal org={editOrg} onClose={() => setEditOrg(null)} onSaved={() => { setEditOrg(null); load(); }} />}
      {resetForOrg && <OrgAdminsModal org={resetForOrg} onClose={() => setResetForOrg(null)} />}
      {confirmDelete && <ConfirmDeleteModal org={confirmDelete} onClose={() => setConfirmDelete(null)} onConfirm={deleteOrg} />}
      {reassignUser && <ReassignModal user={reassignUser} orgs={orgs} onClose={() => setReassignUser(null)} onDone={() => { setReassignUser(null); load(); }} />}
      {healthOrg && <OrgHealthModal org={healthOrg} onClose={() => setHealthOrg(null)} onSaved={() => { load(); }} />}
      {modulesOrg && <ModulesModal org={modulesOrg} onClose={() => setModulesOrg(null)} onSaved={() => { setModulesOrg(null); load(); }} />}
      {supportOrg && <SupportAccessModal org={supportOrg} onClose={() => setSupportOrg(null)} />}
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
      <div className="text-sm text-[var(--ink-2)] mb-3">
        Move <b>{user.email}</b> into an existing workspace and set their role. They'll be able to log in immediately.
      </div>
      <div className="space-y-3">
        <label className="block">
          <div className="text-xs text-[var(--ink-2)] mb-1">Target workspace</div>
          <select aria-label="Organisation" className="input-flat w-full" value={orgId} onChange={(e) => setOrgId(e.target.value)}
                  data-testid="reassign-org-select">
            {orgs.map((o) => <option key={o.org_id} value={o.org_id}>{o.name}</option>)}
          </select>
        </label>
        <label className="block">
          <div className="text-xs text-[var(--ink-2)] mb-1">Role in workspace</div>
          <select aria-label="Role" className="input-flat w-full" value={role} onChange={(e) => setRole(e.target.value)}
                  data-testid="reassign-role-select">
            {["Employee","Designer","ProjectManager","Accountant","HR","Director","Admin"].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
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
/** Count per category (plans, subscription states) as label + bar. */
function MixList({ rows, empty }) {
  const entries = Object.entries(rows || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  if (!entries.length) return <p className="text-sm text-[var(--ink-3)]">{empty}</p>;
  return (
    <ul className="space-y-2">
      {entries.map(([k, n]) => (
        <li key={k} className="flex items-center gap-3 text-sm">
          <span className="w-24 shrink-0">{statusLabel(k)}</span>
          <span className="flex-1 h-2 rounded-full bg-[var(--line-soft)] overflow-hidden">
            <span className="block h-full bg-[var(--accent)] rounded-full" style={{ width: `${(n / max) * 100}%` }} />
          </span>
          <span className="font-mono tabular-nums w-8 text-right">{n}</span>
        </li>
      ))}
    </ul>
  );
}

/** Workspaces with an upcoming date (renewal or trial end), soonest first. */
function DueList({ title, rows, dateKey, empty, testid }) {
  return (
    <div className="card-flat" data-testid={testid}>
      <div className="overline mb-3">{title}</div>
      {!rows?.length ? <p className="text-sm text-[var(--ink-3)]">{empty}</p> : (
        <ul className="divide-y divide-[var(--line-soft)]">
          {rows.map((r) => (
            <li key={r.org_id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="font-semibold truncate">{r.name}</span>
              <span className={`text-xs shrink-0 ${r.days_left < 0 ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-2)]"}`}>
                {formatDate(r[dateKey])} · {r.days_left < 0 ? `${-r.days_left} d overdue` : r.days_left === 0 ? "today" : `in ${r.days_left} d`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function KPI({ icon: Icon, label, value, total, display, tone, testid }) {
  return (
    <div className="card-flat p-5 relative overflow-hidden group hover:-translate-y-0.5 transition" data-testid={testid}>
      <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: tone }} />
      <div className="flex items-start justify-between mb-3">
        <Icon size={22} style={{ color: tone }} weight="duotone" />
      </div>
      <div className="overline text-[10px] text-[var(--ink-2)] mb-1">{label}</div>
      <div className="font-display font-bold tracking-tighter text-3xl tabular-nums">
        {display ?? value}
        {typeof total === "number" && (
          <span className="text-sm text-[var(--ink-3)] font-normal ml-1">/{total}</span>
        )}
      </div>
    </div>
  );
}

/* ------- Create org modal ------- */
function CreateOrgModal({ onClose, onCreated }) {
  const [f, setF] = useState({
    name: "", admin_name: "", admin_email: "", employee_id_prefix: "",
    plan: "starter", gstin: "", industry: "Architecture & Interior Design",
    business_mode: "hybrid",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/platform/orgs", {
        ...f, employee_id_prefix: f.employee_id_prefix || undefined,
      });
      setCreated({ path: data.invite_path, email: f.admin_email, name: data.org?.name || f.name });
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };
  if (created) {
    return (
      <Modal onClose={onCreated} title="Workspace ready" eyebrow="NEW TENANT">
        <p className="text-sm text-[var(--ink-2)] mb-4">
          <b>{created.name}</b> is set up. Send this link to <b>{created.email}</b> so they can
          choose their own password and sign in.
        </p>
        <InviteLinkPanel path={created.path} />
        <div className="flex justify-end mt-5">
          <button type="button" onClick={onCreated} className="btn-primary" data-testid="co-done">Done</button>
        </div>
      </Modal>
    );
  }
  return (
    <Modal onClose={onClose} title="Create Workspace" eyebrow="NEW TENANT">
      <form onSubmit={submit} className="space-y-4" data-testid="create-org-form">
        <div className="overline text-[var(--accent-strong)]">01 · BUSINESS MODE</div>
        <div className="grid grid-cols-3 gap-3">
          {[
            {k:"consultancy", t:"Consultancy", d:"Design-only studio. CRM, projects, quotations, HR, accounting — without procurement."},
            {k:"turnkey",     t:"Turnkey",     d:"End-to-end delivery. Adds POs, GRN, inventory, material tracking, project costing."},
            {k:"hybrid",      t:"Hybrid",      d:"Both modes in one workspace. Each project picks its own engagement type."},
          ].map(o => (
            <button key={o.k} type="button"
              onClick={() => setF({...f, business_mode: o.k})}
              className={`text-left p-3 border transition ${f.business_mode === o.k ? "border-[var(--accent)] bg-[var(--hover)]" : "border-[var(--line)] hover:border-[var(--ink)]"}`}
              data-testid={`mode-${o.k}`}>
              <div className="font-display font-bold tracking-tighter text-base mb-1">{o.t}</div>
              <div className="text-[10px] text-[var(--ink-2)] leading-relaxed">{o.d}</div>
            </button>
          ))}
        </div>

        <div className="overline text-[var(--accent-strong)]">02 · WORKSPACE</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input required data-testid="co-name" className="input-flat" placeholder="Company / Studio name *"
                 value={f.name} onChange={(e) => setF({...f, name: e.target.value})} />
          <input className="input-flat" placeholder="Industry"
                 value={f.industry} onChange={(e) => setF({...f, industry: e.target.value})} />
          <select aria-label="Plan" className="input-flat" value={f.plan}
                  onChange={(e) => setF({...f, plan: e.target.value})}>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
          <input className="input-flat" placeholder="GSTIN (optional)"
                 value={f.gstin} onChange={(e) => setF({...f, gstin: e.target.value})} />
          <PrefixField value={f.employee_id_prefix}
                       onChange={(v) => setF({...f, employee_id_prefix: v})}
                       hint="Optional. Defaults to the studio's initials." />
        </div>
        <div className="overline text-[var(--accent-strong)]">03 · FIRST ADMIN</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input required data-testid="co-admin-name" className="input-flat" placeholder="Admin name *"
                 value={f.admin_name} onChange={(e) => setF({...f, admin_name: e.target.value})} />
          <input required type="email" data-testid="co-admin-email" className="input-flat" placeholder="Admin email *"
                 value={f.admin_email} onChange={(e) => setF({...f, admin_email: e.target.value})} />
        </div>
        <p className="text-[11px] text-[var(--ink-3)] -mt-1">
          You will get a one-time link (valid 72 hours) for the admin to choose their own password.
          Nobody at the platform sees or sets it.
        </p>
        {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
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
  const b = org.billing || {};
  const [f, setF] = useState({
    display_name: org.display_name || org.name, phone: org.phone || "",
    website: org.website || "", gstin: org.gstin || "", pan: org.pan || "",
    plan: org.plan || "starter", industry: org.industry || "",
    business_mode: org.business_mode || "hybrid",
    employee_id_prefix: org.employee_id_prefix || "DS",
  });
  const [billing, setBilling] = useState({
    owner_override: b.owner_override || "",
    amount_charged: b.amount_charged ?? "",
    maintenance_charge: b.maintenance_charge ?? "",
    billing_cycle: b.billing_cycle || "yearly",
    start_date: b.start_date || "",
    renewal_date: b.renewal_date || "",
    notes: b.notes || "",
  });
  const setB = (k, v) => setBilling((s) => ({ ...s, [k]: v }));
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const billingPayload = {
        ...billing,
        amount_charged: billing.amount_charged === "" ? null : Number(billing.amount_charged),
        maintenance_charge: billing.maintenance_charge === "" ? null : Number(billing.maintenance_charge),
      };
      await api.patch(`/platform/orgs/${org.org_id}`, {
        ...f, employee_id_prefix: f.employee_id_prefix || undefined, billing: billingPayload,
      });
      onSaved();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Update failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title={`Edit · ${org.name}`} eyebrow="WORKSPACE INFO">
      <form onSubmit={submit} className="space-y-3" data-testid="edit-org-form">
        <label className="block">
          <div className="text-xs text-[var(--ink-2)] mb-1">Business mode</div>
          <select aria-label="Business mode" className="input-flat w-full" value={f.business_mode}
                  onChange={(e) => setF({...f, business_mode: e.target.value})}
                  data-testid="edit-mode">
            <option value="consultancy">Consultancy</option>
            <option value="turnkey">Turnkey</option>
            <option value="hybrid">Hybrid</option>
          </select>
          {f.business_mode !== org.business_mode && (
            <div className="text-[11px] text-[var(--warning)] mt-1">
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
          <select aria-label="Plan" className="input-flat" value={f.plan}
                  onChange={(e) => setF({...f, plan: e.target.value})}>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
          <PrefixField value={f.employee_id_prefix}
                       onChange={(v) => setF({...f, employee_id_prefix: v})}
                       hint="Applies to new users only. Existing IDs keep working." />
        </div>

        {/* Subscription / billing (manual bookkeeping — no payment gateway) */}
        <div className="border-t border-[var(--line-soft)] pt-3">
          <div className="overline mb-2">SUBSCRIPTION & BILLING</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Owner name (override)</span>
              <input className="input-flat w-full" placeholder={org.owner || "Primary Admin"}
                     value={billing.owner_override} onChange={(e) => setB("owner_override", e.target.value)}
                     data-testid="billing-owner" />
            </label>
            <label className="block">
              <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Billing cycle</span>
              <select aria-label="Billing cycle" className="input-flat w-full" value={billing.billing_cycle}
                      onChange={(e) => setB("billing_cycle", e.target.value)} data-testid="billing-cycle">
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="yearly">Yearly</option>
                <option value="lifetime">Lifetime</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Amount charged (₹)</span>
              <input className="input-flat w-full" type="number" min="0" placeholder="Enter amount"
                     value={billing.amount_charged} onChange={(e) => setB("amount_charged", e.target.value)}
                     data-testid="billing-amount" />
            </label>
            <label className="block">
              <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Maintenance / AMC (₹)</span>
              <input className="input-flat w-full" type="number" min="0" placeholder="Enter charge"
                     value={billing.maintenance_charge} onChange={(e) => setB("maintenance_charge", e.target.value)}
                     data-testid="billing-maintenance" />
            </label>
            <label className="block">
              <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Start date</span>
              <input className="input-flat w-full" type="date"
                     value={billing.start_date} onChange={(e) => setB("start_date", e.target.value)}
                     data-testid="billing-start" />
            </label>
            <label className="block">
              <span className="text-[11px] text-[var(--ink-2)] mb-1 block">Renewal date</span>
              <input className="input-flat w-full" type="date"
                     value={billing.renewal_date} onChange={(e) => setB("renewal_date", e.target.value)}
                     data-testid="billing-renewal" />
            </label>
          </div>
        </div>
        {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
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
  const [link, setLink] = useState(null);
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

  const [newAdmin, setNewAdmin] = useState({ name: "", email: "" });
  const [busy, setBusy] = useState(false);
  const createAdmin = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/platform/orgs/${org.org_id}/admins`, newAdmin);
      setLink({ path: data.invite_path, email: newAdmin.email, purpose: "invite" });
      setNewAdmin({ name: "", email: "" });
      setShowCreate(false);
      await load();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };
  const issueLink = async (u) => {
    if (!await confirmAction(`Create a set-password link for ${u.email}? When they use it, their current password, sessions and App PIN stop working. Any earlier unused link stops working now.`)) return;
    setErr("");
    try {
      const { data } = await api.post(`/platform/orgs/${org.org_id}/users/${u.user_id}/reset-link`);
      setLink({ path: data.invite_path, email: u.email, purpose: "reset" });
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Could not create the link"));
    }
  };

  return (
    <Modal onClose={onClose} title={org.name} eyebrow="ADMINS & USERS" wide>
      {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 mb-3">{err}</div>}
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-[var(--ink-2)]">{users.length} users in this workspace</div>
        <button onClick={() => setShowCreate(!showCreate)} className="btn-ghost text-xs">
          <Plus size={11} /> Add admin
        </button>
      </div>
      {link && (
        <div className="border border-[var(--accent)] bg-[var(--hover)] p-3 mb-4" data-testid="admin-link-panel">
          <div className="text-xs text-[var(--ink-2)] mb-2">
            {link.purpose === "invite" ? "Admin added." : "Set-password link created."} Send this one-time link to <b>{link.email}</b>:
          </div>
          <InviteLinkPanel path={link.path} />
          <div className="text-right mt-2">
            <button type="button" onClick={() => setLink(null)} className="btn-ghost text-xs">Dismiss</button>
          </div>
        </div>
      )}
      {showCreate && (
        <form onSubmit={createAdmin} className="border border-[var(--line)] p-3 mb-4 grid grid-cols-1 md:grid-cols-3 gap-2">
          <input required className="input-flat" placeholder="Name" value={newAdmin.name}
                 onChange={(e) => setNewAdmin({...newAdmin, name: e.target.value})} />
          <input required type="email" className="input-flat" placeholder="Email" value={newAdmin.email}
                 onChange={(e) => setNewAdmin({...newAdmin, email: e.target.value})} />
          <button disabled={busy} className="btn-primary text-xs">{busy ? "…" : "Add admin & get link"}</button>
        </form>
      )}
      <div className="overflow-x-auto"><table className="w-full">
        <thead className="bg-[var(--surface-2)] border-y border-[var(--line)]">
          <tr className="text-left"><Th>Name</Th><Th>Email</Th><Th>Role</Th><Th className="text-right">Actions</Th></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.user_id} className="border-b border-[var(--line-soft)]">
              <Td className="font-semibold text-sm">{u.name}</Td>
              <Td className="font-mono text-xs">{u.email}</Td>
              <Td><span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[var(--hover)] text-[#5F5A4B]">{statusLabel(u.role)}</span></Td>
              <Td className="text-right">
                <button onClick={() => issueLink(u)} className="btn-ghost text-xs"
                        data-testid={`reset-link-${u.user_id}`}>
                  <LinkSimple size={11} /> Set-password link
                </button>
              </Td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </Modal>
  );
}

/** Two to four letters that start every new login ID in a workspace (DS0001 …). */
function PrefixField({ value, onChange, hint }) {
  return (
    <label className="block">
      <span className="sr-only">Login ID prefix</span>
      <input className="input-flat w-full font-mono uppercase" placeholder="Login ID prefix (e.g. DS)"
             value={value} maxLength={4} pattern="[A-Za-z]{2,4}" title="Two to four letters"
             onChange={(e) => onChange(e.target.value.replace(/[^A-Za-z]/g, "").toUpperCase())}
             data-testid="org-id-prefix" />
      <span className="block text-[10px] text-[var(--ink-3)] mt-1">
        {value ? `New login IDs look like ${value}0001. ` : ""}{hint}
      </span>
    </label>
  );
}

/** A one-time set-password link, shown once, built from this site's own address. */
function InviteLinkPanel({ path }) {
  const url = `${window.location.origin}${path}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      toast.error("Copy failed. Select the link and copy it manually.");
    }
  };
  return (
    <div>
      <div className="flex items-stretch gap-2">
        <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label="One-time link"
               className="input-flat flex-1 min-w-0 font-mono text-xs" data-testid="invite-link" />
        <button type="button" onClick={copy} className="btn-primary text-xs" data-testid="invite-copy">
          <Copy size={12} /> Copy
        </button>
      </div>
      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)] mt-1.5">
        Works once · expires in 72 hours · shown only now
      </div>
    </div>
  );
}

/* ------- Confirm delete modal ------- */
/** Offboarding in three steps: deactivate (reversible) → download the full export →
 *  delete permanently with the workspace's short name typed. The server enforces
 *  the same order. */
function ConfirmDeleteModal({ org, onClose, onConfirm }) {
  const [confirmText, setConfirmText] = useState("");
  const active = org.is_active !== false;
  const exported = Boolean(org.exported_at);
  const slug = org.slug || "";
  const canPurge = !active && exported && confirmText.trim().toLowerCase() === slug.toLowerCase();
  const Step = ({ n, done, title, children }) => (
    <li className={`border rounded-lg p-4 ${done ? "border-[var(--line)] bg-[var(--surface-2)]" : "border-[var(--line)]"}`}>
      <div className="flex items-center gap-2 font-semibold text-sm mb-2">
        <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs ${done ? "bg-[var(--success)] text-white" : "bg-[var(--line-soft)]"}`}>
          {done ? <Check size={12} weight="bold" /> : n}
        </span>
        {title}
      </div>
      {children}
    </li>
  );
  return (
    <Modal onClose={onClose} title="Remove workspace" eyebrow="DANGER ZONE">
      <p className="text-sm text-[var(--ink-2)] mb-4">
        Removing <strong className="text-[var(--ink)]">{org.name}</strong> happens in three steps so a customer&apos;s data is never lost by mistake.
      </p>
      <ol className="space-y-3">
        <Step n={1} done={!active} title="Deactivate (reversible)">
          <p className="text-xs text-[var(--ink-2)] mb-3">Signs everyone out and blocks access. All data stays and the workspace can be reactivated.</p>
          {active && (
            <button onClick={() => onConfirm(org, false)} className="btn-primary" data-testid="deactivate-btn">
              <PauseCircle size={14} /> Deactivate workspace
            </button>
          )}
        </Step>
        <Step n={2} done={exported} title="Download the complete export">
          <p className="text-xs text-[var(--ink-2)] mb-3">
            Every record (passwords and Google tokens removed) and every uploaded file, as one zip for the customer and your records.
            {exported && <> Last exported {formatDate(org.exported_at)}.</>}
          </p>
          <a href={`${API}/platform/orgs/${org.org_id}/export`} className={`btn-ghost ${active ? "pointer-events-none opacity-50" : ""}`}
             aria-disabled={active} data-testid="export-btn" onClick={() => toast.success("Export started — reopen this dialog when the download finishes")}>
            <ArrowRight size={14} /> Download export
          </a>
        </Step>
        <Step n={3} done={false} title="Delete permanently">
          <p className="text-xs text-[var(--danger)] mb-2">
            Deletes every project, invoice, employee, file and record of this workspace. This cannot be undone.
          </p>
          <label className="block text-xs text-[var(--ink-2)] mb-1" htmlFor="purge-confirm">
            Type the workspace&apos;s short name <code className="font-mono bg-[var(--line-soft)] px-1">{slug}</code> to confirm
          </label>
          <input id="purge-confirm" className="input-flat w-full mb-3" value={confirmText} disabled={active || !exported}
                 onChange={(e) => setConfirmText(e.target.value)} data-testid="delete-confirm-input" />
          <button disabled={!canPurge} onClick={() => onConfirm(org, true, confirmText.trim())}
                  className="btn-primary bg-[var(--danger)]" data-testid="delete-confirm-btn">
            <Trash size={12} /> Delete permanently
          </button>
        </Step>
      </ol>
      <div className="flex justify-end mt-4">
        <button onClick={onClose} className="btn-ghost">Close</button>
      </div>
    </Modal>
  );
}

/* ------- Support access (time-limited, read-only by default) ------- */
function SupportAccessModal({ org, onClose }) {
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState("read");
  const [minutes, setMinutes] = useState(60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const start = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await api.post(`/platform/impersonate/${org.org_id}`, { reason: reason.trim(), mode, minutes: Number(minutes) });
      window.location.assign("/dashboard");
    } catch (err) {
      setError(fmtErr(err?.response?.data?.detail, "Could not start support access"));
      setBusy(false);
    }
  };
  return (
    <Modal onClose={onClose} title="Support access" eyebrow={org.name}>
      <form onSubmit={start} className="space-y-4">
        <p className="text-sm text-[var(--ink-2)]">
          You will see this workspace exactly as its admin does. The customer sees this access, the reason and
          the time in their own audit log. It ends automatically.
        </p>
        <label className="block">
          <span className="text-xs text-[var(--ink-2)]">Reason (shown to the customer)</span>
          <textarea className="input-flat w-full mt-1" rows={2} required minLength={10} maxLength={300}
                    value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="For example: Ticket 42 — invoice PDF shows the wrong address" data-testid="support-reason" />
        </label>
        <fieldset className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <legend className="text-xs text-[var(--ink-2)] mb-1">Access</legend>
          {[["read", "View only", "Recommended. Nothing can be changed."],
            ["write", "View and change", "Only when the customer asked you to fix something."]].map(([k, t, d]) => (
            <label key={k} className={`border rounded-lg p-3 cursor-pointer ${mode === k ? "border-[var(--accent)] bg-[var(--hover)]" : "border-[var(--line)]"}`}>
              <input type="radio" name="support-mode" className="sr-only" checked={mode === k} onChange={() => setMode(k)} />
              <div className="font-semibold text-sm">{t}</div>
              <div className="text-[11px] text-[var(--ink-2)]">{d}</div>
            </label>
          ))}
        </fieldset>
        <label className="block">
          <span className="text-xs text-[var(--ink-2)]">Ends after</span>
          <select className="input-flat w-full mt-1" value={minutes} onChange={(e) => setMinutes(e.target.value)}>
            {[15, 30, 60, 120, 240].map((m) => <option key={m} value={m}>{m < 60 ? `${m} minutes` : `${m / 60} hour${m > 60 ? "s" : ""}`}</option>)}
          </select>
        </label>
        {error && <div className="text-xs text-[var(--danger)]" role="alert">{error}</div>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button className="btn-primary" disabled={busy || reason.trim().length < 10} data-testid="support-start">
            <Key size={14} /> {busy ? "Opening…" : "Open workspace"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/* ------- Modal shell ------- */
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className={`bg-white p-6 w-full border border-[var(--line)] rounded-xl max-h-[92vh] overflow-y-auto ${wide ? "max-w-4xl" : "max-w-2xl"}`}>
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

/* ------- Module access modal ------- */
const ALL_MODULES = [
  { key: "crm",               label: "CRM / Leads" },
  { key: "clients",           label: "Clients" },
  { key: "projects",          label: "Projects" },
  { key: "quotations",        label: "Quotations" },
  { key: "tasks",             label: "Tasks" },
  { key: "employees",         label: "Employees & HR" },
  { key: "attendance",        label: "Attendance" },
  { key: "payroll",           label: "Payroll" },
  { key: "accounting",        label: "Accounting" },
  { key: "invoices",          label: "Invoices" },
  { key: "expenses",          label: "Expenses" },
  { key: "loans",             label: "Loans" },
  { key: "vendors",           label: "Vendors & Bills" },
  { key: "vendor_commissions",label: "Vendor Commissions" },
  { key: "documents",         label: "Documents" },
  { key: "reports",           label: "Reports" },
  { key: "purchase_orders",   label: "Purchase Orders" },
  { key: "vendor_billing",    label: "Vendor Billing" },
  // Inventory, material tracking, site material, labour billing and project
  // costing have no screens yet; their toggles return once they are built.
];

function ModulesModal({ org, onClose, onSaved }) {
  const initModules = org.features?.modules || {};
  const [mods, setMods] = useState(() => {
    const m = {};
    ALL_MODULES.forEach(({ key }) => { m[key] = initModules[key] !== false; });
    return m;
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const toggle = (key) => setMods((s) => ({ ...s, [key]: !s[key] }));

  const save = async () => {
    setBusy(true); setErr("");
    try {
      await api.patch(`/platform/orgs/${org.org_id}/modules`, { modules: mods });
      toast.success("Module access updated");
      onSaved?.();
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Could not save modules"));
    } finally { setBusy(false); }
  };

  const enabledCount = Object.values(mods).filter(Boolean).length;

  return (
    <Modal onClose={onClose} title={org.name} eyebrow="MODULE ACCESS" wide>
      <p className="text-sm text-[var(--ink-2)] mb-4">
        Toggle which ERP modules this workspace can access. Disabled modules are hidden from their navigation menu immediately and their API endpoints return 403.
      </p>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-[var(--ink-3)]">{enabledCount} of {ALL_MODULES.length} modules enabled</span>
        <button type="button" onClick={() => setMods(Object.fromEntries(ALL_MODULES.map(m => [m.key, true])))}
                className="btn-ghost text-xs">Enable all</button>
        <button type="button" onClick={() => setMods(Object.fromEntries(ALL_MODULES.map(m => [m.key, false])))}
                className="btn-ghost text-xs">Disable all</button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2" data-testid={`modules-grid-${org.org_id}`}>
        {ALL_MODULES.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => toggle(key)}
            className={`flex items-center justify-between p-3 border text-left transition rounded-md ${
              mods[key]
                ? "border-[var(--accent)] bg-[var(--hover)]"
                : "border-[var(--line)] bg-[var(--surface-2)] opacity-70"
            }`}
            data-testid={`module-toggle-${key}`}
          >
            <span className="text-sm font-medium">{label}</span>
            <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
              mods[key]
                ? "bg-[var(--success-soft)] text-[var(--success)]"
                : "bg-[var(--danger-soft)] text-[var(--danger)]"
            }`}>
              {mods[key] ? "ON" : "OFF"}
            </span>
          </button>
        ))}
      </div>
      {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 mt-3 rounded-md">{err}</div>}
      <div className="flex gap-2 justify-end mt-4">
        <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
        <button disabled={busy} onClick={save} className="btn-primary" data-testid="save-modules-btn">
          {busy ? "Saving…" : <><Faders size={12} /> Save modules</>}
        </button>
      </div>
    </Modal>
  );
}

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
    <div className="border border-[var(--line-soft)] p-2">
      <div className="text-[10px] font-mono uppercase text-[var(--ink-3)]">{label}</div>
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
        {err && <div className="text-xs text-[var(--danger)] border border-[var(--danger)] bg-[var(--danger-soft)] p-2">{err}</div>}
        {!health && !err && <div className="skeleton h-40 w-full" />}
        {health && (
          <>
            {(health.warnings || []).length > 0 && (
              <div className="border-l-4 border-l-[var(--warning)] bg-[var(--warning-soft)] p-3 space-y-1">
                {health.warnings.map((w, i) => (
                  <div key={i} className="text-xs text-[var(--warning)]">{w}</div>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="border border-[var(--line)] rounded-md p-3">
                <div className="text-[10px] font-mono uppercase text-[var(--ink-3)]">USERS</div>
                <div className="font-mono text-lg">{health.usage.users.used}<span className="text-xs text-[var(--ink-3)]"> / {health.usage.users.limit ?? "∞"}</span></div>
              </div>
              <div className="border border-[var(--line)] rounded-md p-3">
                <div className="text-[10px] font-mono uppercase text-[var(--ink-3)]">PROJECTS</div>
                <div className="font-mono text-lg">{health.usage.projects.used}<span className="text-xs text-[var(--ink-3)]"> / {health.usage.projects.limit ?? "∞"}</span></div>
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
            <div className="text-xs text-[var(--ink-2)]">
              Last login: <span className="font-mono">{(health.last_login || "never").slice(0, 19).replace("T", " ")}</span>
              {" · "}Active admins: <span className="font-mono">{health.admins}</span>
            </div>
            <div className="border-t border-[var(--line-soft)] pt-4">
              <div className="overline mb-3">PLAN &amp; LIMITS</div>
              <div className="grid grid-cols-3 gap-3">
                <label className="text-xs space-y-1">
                  <span className="font-mono uppercase text-[var(--ink-3)]">Plan</span>
                  <select aria-label="Plan" value={limits.plan} onChange={(e) => setLimits({ ...limits, plan: e.target.value })}
                          className="input w-full" data-testid="limits-plan">
                    <option value="starter">starter</option>
                    <option value="pro">pro</option>
                    <option value="enterprise">enterprise</option>
                  </select>
                </label>
                <label className="text-xs space-y-1">
                  <span className="font-mono uppercase text-[var(--ink-3)]">Max users</span>
                  <input type="number" min="1" value={limits.max_users}
                         onChange={(e) => setLimits({ ...limits, max_users: e.target.value })}
                         className="input w-full" data-testid="limits-max-users" />
                </label>
                <label className="text-xs space-y-1">
                  <span className="font-mono uppercase text-[var(--ink-3)]">Max projects</span>
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

/** Trial / active / expired. Expired (or a past trial end) = read-only workspace. */
function SubscriptionControl({ org, onSaved }) {
  const sub = org.subscription || {};
  const [status, setStatus] = useState(sub.status || "");
  const [trialEnd, setTrialEnd] = useState(sub.trial_ends_on || "");
  const [busy, setBusy] = useState(false);
  const today = dateForInput(new Date());
  const readOnly = sub.status === "expired" || (sub.status === "trial" && sub.trial_ends_on && sub.trial_ends_on < today);
  const save = async (nextStatus, nextEnd) => {
    if (nextStatus === "trial" && !nextEnd) return;
    if (nextStatus === "expired" && !await confirmAction({
      title: `Make "${org.name}" read-only?`,
      body: "Users can still sign in, view and download everything, but cannot create, edit or delete until the plan is active again.",
      confirmLabel: "Make read-only", danger: true,
    })) { setStatus(sub.status || ""); return; }
    setBusy(true);
    try {
      await api.patch(`/platform/orgs/${org.org_id}/subscription`, {
        status: nextStatus || null, trial_ends_on: nextStatus === "trial" ? nextEnd : null,
      });
      toast.success("Subscription updated");
      onSaved?.();
    } catch (e) {
      toast.error(fmtErr(e?.response?.data?.detail, "Could not update the subscription"));
    } finally { setBusy(false); }
  };
  return (
    <div className="mt-1.5 flex flex-col gap-1" data-testid={`sub-${org.org_id}`}>
      <select aria-label={`Subscription for ${org.name}`} className="input-flat !py-1 !text-xs !w-auto" value={status} disabled={busy}
              onChange={(e) => { setStatus(e.target.value); if (e.target.value !== "trial") save(e.target.value, null); }}>
        <option value="">Plan: not set</option>
        <option value="trial">Trial</option>
        <option value="active">Active (paid)</option>
        <option value="expired">Ended (read-only)</option>
      </select>
      {status === "trial" && (
        <input type="date" aria-label="Trial ends on" className="input-flat !py-1 !text-xs !w-auto" value={trialEnd} disabled={busy}
               onChange={(e) => { setTrialEnd(e.target.value); save("trial", e.target.value); }} />
      )}
      {readOnly && <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[var(--danger-soft)] text-[var(--danger)] w-fit">read-only</span>}
    </div>
  );
}
