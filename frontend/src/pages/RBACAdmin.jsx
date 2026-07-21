import { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import { ShieldCheck, CaretDown, Info } from "@phosphor-icons/react";

const ROLE_DESCRIPTIONS = {
  Admin:          "Full system access. Can manage users and settings.",
  Director:       "All operational access. Cannot manage RBAC.",
  ProjectManager: "Owns projects, tasks, leads. Reads finance.",
  Designer:       "Reads projects, owns tasks + files + quotation drafts.",
  Accountant:     "Owns invoices & quotations. Read-only projects/leads.",
  HR:             "Reads users, updates non-role fields, dashboard.",
  Employee:       "Reads projects/tasks/clients. Updates own tasks.",
  Client:         "No studio panel access (portal-only via share link).",
};

export default function RBACAdmin() {
  const { user: me, refresh } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState("");
  const [expandedRole, setExpandedRole] = useState(null);

  const load = async () => {
    try {
      const [u, r] = await Promise.all([
        api.get("/rbac/users"),
        api.get("/rbac/roles"),
      ]);
      setUsers(u.data);
      setRoles(r.data.roles);
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load");
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
      // If it's my own role that changed, refresh session perms
      if (userId === me?.user_id) await refresh();
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to change role");
    } finally {
      setSavingId(null);
    }
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
        kicker="Role-based access control. Admin-only zone. Changes apply on the user's next request."
        count={users.length}
      >
        <div className="btn-ghost pointer-events-none">
          <ShieldCheck size={14} /> {roles.length} roles configured
        </div>
      </PageHero>

      {error && (
        <div className="border border-[#FF2A00] bg-[#FFF5F3] p-4 text-sm text-[#FF2A00] flex items-center gap-2">
          <Info size={16} /> {error}
        </div>
      )}

      {/* Users table */}
      <div className="card-flat p-0 overflow-hidden">
        <div className="p-6 pb-4">
          <div className="overline">TEAM MEMBERS</div>
        </div>
        <table className="w-full" data-testid="rbac-users-table">
          <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Name</Th>
              <Th>Email</Th>
              <Th>Role</Th>
              <Th>Joined</Th>
              <Th>Last login</Th>
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
                  <Td className="font-mono text-xs">{u.email}</Td>
                  <Td>
                    <select
                      className="input-flat"
                      style={{ padding: "6px 8px", width: 200 }}
                      value={u.role}
                      disabled={isSaving}
                      onChange={(e) => changeRole(u.user_id, e.target.value)}
                      data-testid={`role-select-${u.user_id}`}
                    >
                      {roles.map((r) => (
                        <option key={r.name} value={r.name}>{r.name}</option>
                      ))}
                    </select>
                    {isSaving && <span className="ml-2 overline text-[10px]">SAVING…</span>}
                  </Td>
                  <Td className="font-mono text-xs">{(u.created_at || "").slice(0, 10) || "—"}</Td>
                  <Td className="font-mono text-xs">{(u.last_login || "").slice(0, 10) || "—"}</Td>
                </tr>
              );
            })}
            {users.length === 0 && (
              <tr><td colSpan={5} className="p-8 text-center text-[#5C5C5C]">No users yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

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
                    <div className="font-display font-bold tracking-tight text-lg w-40 flex-shrink-0">
                      {r.name}
                    </div>
                    <div className="text-sm text-[#5C5C5C] truncate">
                      {ROLE_DESCRIPTIONS[r.name] || "—"}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="font-mono text-xs tabular-nums text-[#5C5C5C]">
                      {r.permissions.length} {r.permissions.length === 1 ? "grant" : "grants"}
                    </span>
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
                          <span key={p} className="font-mono text-[11px] px-2 py-1 bg-[#F0F3FB] text-[#002FA7] border border-[#DDE3F4]">
                            {p}
                          </span>
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

const Th = ({ children }) => <th className="px-4 py-3 overline">{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
