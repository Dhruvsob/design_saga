import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import { Plus, ArrowRight, Sparkle, MagnifyingGlass, Trash } from "@phosphor-icons/react";

const STATUS_CHIP = {
  active: "chip-paid",
  probation: "chip-medium",
  notice: "chip-overdue",
  terminated: "chip-draft",
};

export default function Employees() {
  const navigate = useNavigate();
  const { hasPerm, user } = useAuth();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ departments: [], employment_types: [], employment_statuses: [] });
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState({ q: "", department: "", status: "" });
  const [form, setForm] = useState({
    first_name: "", last_name: "", email: "", phone: "",
    department: "Design", designation: "",
    employment_type: "full_time", employment_status: "active",
    joining_date: new Date().toISOString().slice(0, 10),
  });

  const load = async () => {
    setLoading(true);
    try {
      const [r, m] = await Promise.all([api.get("/employees"), api.get("/employees/meta")]);
      setRows(r.data);
      setMeta(m.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.post("/employees", form);
      setShowForm(false);
      setForm({
        first_name: "", last_name: "", email: "", phone: "",
        department: "Design", designation: "",
        employment_type: "full_time", employment_status: "active",
        joining_date: new Date().toISOString().slice(0, 10),
      });
      await load();
      navigate(`/employees/${data.id}`);
    } finally {
      setSaving(false);
    }
  };

  const seed = async () => {
    setSeeding(true);
    try { await api.post("/employees/seed"); await load(); } finally { setSeeding(false); }
  };

  const remove = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this employee record permanently?")) return;
    await api.delete(`/employees/${id}`);
    load();
  };

  const filtered = useMemo(() => {
    const q = filter.q.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter.department && r.department !== filter.department) return false;
      if (filter.status && r.employment_status !== filter.status) return false;
      if (q) {
        const hay = `${r.first_name} ${r.last_name} ${r.email} ${r.employee_id} ${r.designation}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rows, filter]);

  const canCreate = hasPerm("employees.create");
  const canDelete = hasPerm("employees.delete") || user?.role === "Admin";

  return (
    <div className="space-y-8" data-testid="employees-page">
      <PageHero
        eyebrow="HR / EMPLOYEES"
        title="Your people."
        kicker="Complete HR record — payroll structure, documents, warnings, rewards, KPIs. All in one place."
        count={rows.length}
      >
        {canCreate && rows.length === 0 && (
          <button onClick={seed} disabled={seeding} className="btn-ghost" data-testid="seed-employees-btn">
            <Sparkle size={14} /> {seeding ? "Seeding…" : "Seed sample team"}
          </button>
        )}
        {canCreate && (
          <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-employee-btn">
            <Plus size={14} /> {showForm ? "Cancel" : "New employee"}
          </button>
        )}
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3 scale-in" data-testid="new-employee-form">
          <input required className="input-flat" placeholder="First name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} data-testid="emp-first-name" />
          <input className="input-flat" placeholder="Last name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          <input className="input-flat" placeholder="Designation" value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
          <input className="input-flat" type="email" placeholder="Work email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input-flat" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <select className="input-flat" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}>
            {meta.departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <select className="input-flat" value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}>
            {meta.employment_types.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
          </select>
          <select className="input-flat" value={form.employment_status} onChange={(e) => setForm({ ...form, employment_status: e.target.value })}>
            {meta.employment_statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input required className="input-flat" type="date" value={form.joining_date} onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
          <button disabled={saving} className="btn-primary md:col-span-3" type="submit" data-testid="emp-submit">
            {saving ? "Creating…" : "Create employee"}
          </button>
        </form>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2 flex-1 min-w-[240px] max-w-md px-3 py-2 border border-[#E5E5E5] focus-within:border-[#002FA7] transition">
          <MagnifyingGlass size={15} className="text-[#5C5C5C]" />
          <input
            data-testid="emp-search"
            value={filter.q}
            onChange={(e) => setFilter({ ...filter, q: e.target.value })}
            placeholder="Search name, email, EMP-ID, designation…"
            className="bg-transparent flex-1 outline-none text-sm placeholder-[#9A9A9A]"
          />
        </div>
        <select className="input-flat max-w-[200px]" value={filter.department} onChange={(e) => setFilter({ ...filter, department: e.target.value })}>
          <option value="">All departments</option>
          {meta.departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select className="input-flat max-w-[200px]" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">All statuses</option>
          {meta.employment_statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-14 w-full" />)}
        </div>
      ) : (
        <div className="border border-[#E5E5E5]">
          <table className="w-full">
            <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
              <tr className="text-left">
                <Th>Employee</Th>
                <Th>EMP-ID</Th>
                <Th>Department</Th>
                <Th>Designation</Th>
                <Th className="text-right">Net / month</Th>
                <Th>Status</Th>
                <Th>Joined</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  className="row-hover border-b border-[#F0F0F0] cursor-pointer"
                  onClick={() => navigate(`/employees/${r.id}`)}
                  data-testid={`emp-row-${r.id}`}
                >
                  <Td>
                    <div className="flex items-center gap-3">
                      {r.photo ? (
                        <img src={r.photo} alt="" className="w-8 h-8 object-cover ring-1 ring-[#E5E5E5]" />
                      ) : (
                        <div className="w-8 h-8 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-xs">
                          {(r.first_name || "?").slice(0, 1).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="font-semibold text-sm">{r.first_name} {r.last_name}</div>
                        <div className="text-xs text-[#5C5C5C]">{r.email || "—"}</div>
                      </div>
                    </div>
                  </Td>
                  <Td className="font-mono text-xs">{r.employee_id}</Td>
                  <Td className="text-sm">{r.department}</Td>
                  <Td className="text-sm">{r.designation || "—"}</Td>
                  <Td className="font-mono text-right font-semibold">₹{(r.salary?.net_monthly || 0).toLocaleString("en-IN")}</Td>
                  <Td><span className={`status-chip ${STATUS_CHIP[r.employment_status] || "chip-draft"}`}>{r.employment_status}</span></Td>
                  <Td className="font-mono text-xs">{r.joining_date || "—"}</Td>
                  <Td>
                    <div className="flex items-center gap-2 justify-end">
                      <ArrowRight size={14} className="text-[#5C5C5C]" />
                      {canDelete && (
                        <button onClick={(e) => remove(r.id, e)} className="text-[#FF2A00] hover:scale-110 transition" title="Delete">
                          <Trash size={14} />
                        </button>
                      )}
                    </div>
                  </Td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="p-10 text-center text-[#5C5C5C]">
                  {rows.length === 0 ? "No employees yet. Create one or seed the sample team." : "No matches for these filters."}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
