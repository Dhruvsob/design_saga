import { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import {
  ShieldCheck, CaretDown, Info, UserPlus, Key, Check, X, Warning,
} from "@phosphor-icons/react";

const ROLE_DESCRIPTIONS = {
  Admin:          "Full system access. Can manage users and settings.",
  Director:       "All operational access + finance. Cannot manage RBAC.",
  ProjectManager: "Owns projects, tasks, leads. Reads finance.",
  Designer:       "Reads projects, owns tasks + files + quotation drafts.",
  Accountant:     "Owns invoices & finance. Read-only projects/leads.",
  HR:             "Reads users, updates non-role fields, dashboard.",
  Employee:       "Reads projects/tasks/clients. Updates own tasks.",
  Client:         "No studio panel access (portal-only via share link).",
};

function fmtErr(detail, fb = "Failed") {
  if (!detail) return fb;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || String(e)).join(" · ");
  return typeof detail === "object" ? (detail.msg || fb) : String(detail);
}

export default function RBACAdmin() {
  const { user: me, refresh } = useAuth();
  const [users, setUsers] = useState([]);
  const [pending, setPending] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState("");
  const [expandedRole, setExpandedRole] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showReset, setShowReset] = useState(null);   // user_id being reset

  const load = async () => {
    try {
      const [u, r, p] = await Promise.all([
        api.get("/rbac/users"),
        api.get("/rbac/roles"),
        api.get("/rbac/pending").catch(() => ({ data: [] })),
      ]);
      setUsers(u.data);
      setRoles(r.data.roles);
      setPending(p.data);
      setError("");
    } catch (e) {
      setError(fmtErr(e?.response?.data?.detail, "Failed to load"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const changeRole = async (userId, newRole) => {
    setSavingId(userId);
    setError("");
    try {
      await api.patch(`/rbac/users/${userId}/role`, { role: newRole });
      await load();
      if (userId === me?.user_id) await refresh();
    } catch (e) {
      setError(fmtErr(e?.response?.data?.detail, "Failed to change role"));
    } finally { setSavingId(null); }
  };

  const decidePending = async (userId, decision, role) => {
    setSavingId(userId);
    try {
      await api.post(`/rbac/users/${userId}/${decision === "approve" ? "approve" : "approve"}`,
                     { decision, role });
      await load();
    } catch (e) {
      setError(fmtErr(e?.response?.data?.detail, "Failed"));
    } finally { setSavingId(null); }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-16 w-72"></div>
        <div className="skeleton h-64 w-full"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8" data-testid="rbac-page">
      <PageHero
        eyebrow="ADMIN / TEAM & ROLES"
        title="Who sees what."
        kicker="Role-based access control. Admin-only zone."
        count={users.length}
      >
        <button onClick={() => setShowCreate(!showCreate)} className="btn-primary" data-testid="create-user-btn">
          <UserPlus size={14} /> {showCreate ? "Cancel" : "Create user"}
        </button>
      </PageHero>

      {error && (
        <div className="border border-[#B22B22] bg-[#FCEEEC] p-4 text-sm text-[#B22B22] flex items-center gap-2" data-testid="rbac-error">
          <Warning size={16} /> {error}
        </div>
      )}

      {showCreate && <CreateUserForm roles={roles} onDone={() => { setShowCreate(false); load(); }} />}

      {/* Pending approvals */}
      {pending.length > 0 && (
        <div className="card-flat p-0 overflow-hidden border-l-4 border-l-[#F0A93A]" data-testid="pending-section">
          <div className="p-6 pb-4 flex items-center justify-between">
            <div>
              <div className="overline text-[#B87500]">PENDING APPROVALS · {pending.length}</div>
              <div className="text-xs text-[#5C5C5C] mt-1">
                New Google sign-ins waiting for you to grant access.
              </div>
            </div>
          </div>
          <table className="w-full">
            <thead className="bg-[#FFF8EC] border-y border-[#F0DDB8] text-left">
              <tr><Th>Name</Th><Th>Email</Th><Th>Assign role</Th><Th className="text-right">Action</Th></tr>
            </thead>
            <tbody>
              {pending.map((u) => (
                <PendingRow key={u.user_id} u={u} roles={roles} onDecide={decidePending} savingId={savingId} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Users table */}
      <div className="card-flat p-0 overflow-hidden">
        <div className="p-6 pb-4">
          <div className="overline">TEAM MEMBERS · {users.length}</div>
        </div>
        <table className="w-full" data-testid="rbac-users-table">
          <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Name</Th><Th>Employee ID</Th><Th>Email</Th><Th>Role</Th>
              <Th>Status</Th><Th>Joined</Th><Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isMe = u.user_id === me?.user_id;
              const isSaving = savingId === u.user_id;
              return (
                <tr key={u.user_id} className="row-hover border-b border-[#F0F0F0]">
                  <Td>
                    <div className="flex items-center gap-3">
                      {u.picture ? (
                        <img src={u.picture} alt="" className="w-8 h-8 object-cover ring-1 ring-[#E5E5E5]" />
                      ) : (
                        <div className="w-8 h-8 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-xs">
                          {(u.name || "?").slice(0, 1).toUpperCase()}
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="font-semibold text-sm truncate flex items-center gap-2">
                          {u.name || "—"}
                          {isMe && <span className="overline text-[10px] accent-blue">YOU</span>}
                        </div>
                      </div>
                    </div>
                  </Td>
                  <Td className="font-mono text-xs">{u.employee_id || "—"}</Td>
                  <Td className="font-mono text-xs">{u.email}</Td>
                  <Td>
                    <select
                      className="input-flat" style={{ padding: "6px 8px", width: 180 }}
                      value={u.role} disabled={isSaving}
                      onChange={(e) => changeRole(u.user_id, e.target.value)}
                      data-testid={`role-select-${u.user_id}`}
                    >
                      {roles.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
                    </select>
                  </Td>
                  <Td>
                    <StatusPill status={u.approval_status || "approved"} active={u.is_active !== false} />
                  </Td>
                  <Td className="font-mono text-xs">{(u.created_at || "").slice(0, 10) || "—"}</Td>
                  <Td className="text-right">
                    <button
                      onClick={() => setShowReset(u.user_id)}
                      className="btn-ghost text-xs" data-testid={`reset-pwd-${u.user_id}`}
                    ><Key size={12} /> Reset password</button>
                  </Td>
                </tr>
              );
            })}
            {users.length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-[#5C5C5C]">No users yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showReset && (
        <ResetPasswordModal
          userId={showReset}
          user={users.find((u) => u.user_id === showReset)}
          onClose={() => setShowReset(null)}
        />
      )}

      {/* Roles reference */}
      <div className="card-flat">
        <div className="flex items-center justify-between mb-4">
          <div className="overline">PERMISSION MATRIX</div>
          <span className="overline">{roles.length} ROLES</span>
        </div>
        <div className="border border-[#E5E5E5] divide-y divide-[#F0F0F0]">
          {roles.map((r) => {
            const isOpen = expandedRole === r.name;
            return (
              <div key={r.name}>
                <button
                  onClick={() => setExpandedRole(isOpen ? null : r.name)}
                  className="w-full text-left p-4 hover:bg-[#FAFAFA] transition flex items-center justify-between"
                  data-testid={`role-row-${r.name}`}
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="font-display font-bold tracking-tight text-lg w-40 flex-shrink-0">{r.name}</div>
                    <div className="text-sm text-[#5C5C5C] truncate">{ROLE_DESCRIPTIONS[r.name] || "—"}</div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="font-mono text-xs tabular-nums text-[#5C5C5C]">{r.permissions.length} grants</span>
                    <CaretDown size={14} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-1 fade-up">
                    {r.permissions.length === 0 ? (
                      <p className="text-sm text-[#5C5C5C]">No grants. Portal-only role.</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {r.permissions.map((p) => (
                          <span key={p} className="font-mono text-[11px] px-2 py-1 bg-[#F0F3FB] text-[#002FA7] border border-[#DDE3F4]">{p}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ---------- Pending row (row-local role picker) ---------- */
function PendingRow({ u, roles, onDecide, savingId }) {
  const [role, setRole] = useState("Employee");
  const isSaving = savingId === u.user_id;
  return (
    <tr className="border-b border-[#F0DDB8]" data-testid={`pending-row-${u.user_id}`}>
      <Td>
        <div className="flex items-center gap-3">
          {u.picture ? (
            <img src={u.picture} alt="" className="w-8 h-8 object-cover ring-1 ring-[#E5E5E5]" />
          ) : (
            <div className="w-8 h-8 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-xs">
              {(u.name || "?").slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="font-semibold text-sm">{u.name || "—"}</div>
        </div>
      </Td>
      <Td className="font-mono text-xs">{u.email}</Td>
      <Td>
        <select className="input-flat" style={{ padding: "6px 8px", width: 180 }}
          value={role} onChange={(e) => setRole(e.target.value)}>
          {roles.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
        </select>
      </Td>
      <Td className="text-right">
        <div className="flex items-center justify-end gap-2">
          <button
            disabled={isSaving} onClick={() => onDecide(u.user_id, "reject")}
            className="btn-ghost text-xs" data-testid={`reject-${u.user_id}`}
          ><X size={11} /> Reject</button>
          <button
            disabled={isSaving} onClick={() => onDecide(u.user_id, "approve", role)}
            className="btn-primary bg-[#1D633E] text-xs" data-testid={`approve-${u.user_id}`}
          ><Check size={11} /> Approve</button>
        </div>
      </Td>
    </tr>
  );
}

/* ---------- Status pill ---------- */
function StatusPill({ status, active }) {
  if (!active || status === "rejected") return (
    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#FCEEEC] text-[#B22B22]">deactivated</span>
  );
  if (status === "pending") return (
    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#FFF4E5] text-[#7A4E1A]">pending</span>
  );
  return (
    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#EFF7EF] text-[#1D633E]">approved</span>
  );
}

/* ---------- Create-user form ---------- */
function CreateUserForm({ roles, onDone }) {
  const [f, setF] = useState({
    email: "", password: "", name: "", role: "Employee", phone: "", approve_immediately: true,
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      await api.post("/auth/register", f);
      onDone();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="card-flat space-y-3" data-testid="create-user-form">
      <div className="overline">CREATE NEW USER</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input required data-testid="cu-name" className="input-flat" placeholder="Full name *"
          value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input required type="email" data-testid="cu-email" className="input-flat" placeholder="Email *"
          value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <input required data-testid="cu-password" type="text" className="input-flat" placeholder="Initial password *"
          value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        <input className="input-flat" placeholder="Phone"
          value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        <select data-testid="cu-role" className="input-flat" value={f.role}
          onChange={(e) => setF({ ...f, role: e.target.value })}>
          {roles.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.approve_immediately}
            onChange={(e) => setF({ ...f, approve_immediately: e.target.checked })} />
          Approve immediately
        </label>
      </div>
      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
      <button disabled={busy} className="btn-primary" data-testid="cu-submit">
        {busy ? "Creating…" : "Create user"}
      </button>
    </form>
  );
}

/* ---------- Reset-password modal ---------- */
function ResetPasswordModal({ userId, user, onClose }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      await api.post(`/auth/reset-password/${userId}`, { new_password: pw });
      onClose();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Reset failed"));
    } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <form onClick={(e) => e.stopPropagation()} onSubmit={submit}
        className="bg-white p-6 max-w-md w-full border border-[#E5E5E5] space-y-3" data-testid="reset-pwd-modal">
        <div className="overline">RESET PASSWORD</div>
        <div className="font-display font-bold tracking-tight text-2xl">{user?.name || "User"}</div>
        <div className="text-xs text-[#5C5C5C]">{user?.email} · {user?.employee_id}</div>
        <input required minLength={6} type="text" data-testid="reset-pwd-input"
          className="input-flat w-full" placeholder="New password (min 6 chars)"
          value={pw} onChange={(e) => setPw(e.target.value)} />
        <p className="text-xs text-[#9A9A9A]">
          All active sessions for this user will be logged out. They'll need to sign in again with the new password.
        </p>
        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} className="btn-primary" data-testid="reset-pwd-submit">
            <Key size={12} /> {busy ? "Resetting…" : "Reset password"}
          </button>
        </div>
      </form>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
