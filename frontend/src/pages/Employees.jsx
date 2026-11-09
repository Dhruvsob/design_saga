import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import { dateForInput, formatDate, statusLabel } from "../lib/format";
import { Plus, ArrowRight, MagnifyingGlass, UserMinus, X } from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";
import { usePaged } from "../components/Pager";
import { IdentificationCard } from "@phosphor-icons/react";
import { SkeletonRows, EmptyRow } from "../components/TableState";

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
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState({ q: "", department: "", status: "" });
  const [form, setForm] = useState({
    first_name: "", last_name: "", email: "", phone: "",
    department: "Design", designation: "",
    employment_type: "full_time", employment_status: "active",
    joining_date: dateForInput(new Date()),
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
        joining_date: dateForInput(new Date()),
      });
      await load();
      navigate(`/employees/${data.id}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id, e) => {
    e.stopPropagation();
    if (!await confirmAction("Terminate this employee? Their login will be disabled, while attendance, payroll, and accounting history will be retained.")) return;
    await api.delete(`/employees/${id}`);
    load();
  };

  const filtered = useMemo(() => {
    const q = filter.q.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter.department && r.department !== filter.department) return false;
      // Default view is current staff; former staff appear under "Former staff" or by status.
      if (!filter.status && r.employment_status === "terminated") return false;
      if (filter.status && filter.status !== "all" && r.employment_status !== filter.status) return false;
      if (q) {
        const hay = `${r.first_name} ${r.last_name} ${r.email} ${r.employee_id} ${r.designation}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rows, filter]);
  const { pageRows: filteredPage, pager: filteredPager } = usePaged(filtered, { key: "employees" });

  const canCreate = hasPerm("employees.create");
  const canDelete = hasPerm("employees.delete") || user?.role === "Admin";
  const canPayrollRead = hasPerm("payroll.read");

  return (
    <div className="space-y-8" data-testid="employees-page">
      <PageHero
        eyebrow="HR / EMPLOYEES"
        title="Employees"
        kicker="Complete HR record — payroll structure, documents, warnings, rewards, KPIs. All in one place."
        count={rows.length}
      >
        {canCreate && (
          <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-employee-btn">
            {showForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> {"New employee"}</>}
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
          <select aria-label="Department" className="input-flat" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}>
            {meta.departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <select aria-label="Employment type" className="input-flat" value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}>
            {meta.employment_types.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
          </select>
          <select aria-label="Employment status" className="input-flat" value={form.employment_status} onChange={(e) => setForm({ ...form, employment_status: e.target.value })}>
            {meta.employment_statuses.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
          <input required className="input-flat" type="date" value={form.joining_date} onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
          <button disabled={saving} className="btn-primary md:col-span-3" type="submit" data-testid="emp-submit">
            {saving ? "Creating…" : "Create employee"}
          </button>
        </form>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2 flex-1 min-w-[240px] max-w-md px-3 py-2 border border-[var(--line)] focus-within:border-[var(--accent)] transition">
          <MagnifyingGlass size={15} className="text-[var(--ink-2)]" />
          <input
            data-testid="emp-search"
            value={filter.q}
            onChange={(e) => setFilter({ ...filter, q: e.target.value })}
            placeholder="Search name, email, EMP-ID, designation…"
            className="bg-transparent flex-1 outline-none text-sm placeholder-[var(--ink-3)]"
          />
        </div>
        <select aria-label="Department" className="input-flat max-w-[200px]" value={filter.department} onChange={(e) => setFilter({ ...filter, department: e.target.value })}>
          <option value="">All departments</option>
          {meta.departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select aria-label="Status" className="input-flat max-w-[200px]" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">Current staff</option>
          <option value="all">Everyone (incl. former)</option>
          {meta.employment_statuses.map((s) => <option key={s} value={s}>{s === "terminated" ? "Former staff" : statusLabel(s)}</option>)}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-14 w-full" />)}
        </div>
      ) : (
        <div className="border border-[var(--line)]">
          <div className="overflow-x-auto"><table className="w-full">
            <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
              <tr className="text-left">
                <Th>Employee</Th>
                <Th>EMP-ID</Th>
                <Th>Department</Th>
                <Th>Designation</Th>
                {canPayrollRead && <Th className="text-right">Net / month</Th>}
                <Th>Status</Th>
                <Th>Joined</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {filteredPage.map((r) => (
                <tr
                  key={r.id}
                  className="row-hover border-b border-[var(--line-soft)] cursor-pointer"
                  onClick={() => navigate(`/employees/${r.id}`)}
                  data-testid={`emp-row-${r.id}`}
                >
                  <Td>
                    <div className="flex items-center gap-3">
                      {r.photo ? (
                        <img src={r.photo} alt="" className="w-8 h-8 object-cover ring-1 ring-[var(--line)]" />
                      ) : (
                        <div className="w-8 h-8 bg-[var(--ink)] text-white flex items-center justify-center font-display font-bold text-xs">
                          {(r.first_name || "?").slice(0, 1).toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="font-semibold text-sm">{r.first_name} {r.last_name}</div>
                        {r.email && <div className="text-xs text-[var(--ink-2)]">{r.email}</div>}
                      </div>
                    </div>
                  </Td>
                  <Td className="font-mono text-xs">{r.employee_id}</Td>
                  <Td className="text-sm">{r.department}</Td>
                  <Td className="text-sm">{r.designation || "—"}</Td>
                  {canPayrollRead && <Td className="font-mono text-right font-semibold">₹{(r.salary?.net_monthly || 0).toLocaleString("en-IN")}</Td>}
                  <Td><span className={`status-chip ${STATUS_CHIP[r.employment_status] || "chip-draft"}`}>{statusLabel(r.employment_status)}</span></Td>
                  <Td className="font-mono text-xs">{formatDate(r.joining_date)}</Td>
                  <Td>
                    <div className="flex items-center gap-2 justify-end">
                      <RowActions label={[r.first_name, r.last_name].filter(Boolean).join(" ") || "employee"} testid={`employee-actions-${r.id}`} actions={[
                        { label: "Open profile", icon: ArrowRight, onSelect: () => navigate(`/employees/${r.id}`) },
                        { divider: true },
                        { label: "Terminate employee", icon: UserMinus, danger: true, hidden: !canDelete,
                          onSelect: () => remove(r.id, { stopPropagation() {} }) },
                      ]} />
                    </div>
                  </Td>
                </tr>
              ))}
              {loading && rows.length === 0 && <SkeletonRows cols={canPayrollRead ? 8 : 7} />}
              {!loading && filtered.length === 0 && (rows.length === 0 ? (
                <EmptyRow cols={canPayrollRead ? 8 : 7} icon={IdentificationCard} title="No employees yet"
                  hint="Add your team to track attendance, leave and salary."
                  actionLabel={canCreate ? "Add employee" : undefined}
                  onAction={() => { setShowForm(true); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
              ) : (
                <EmptyRow cols={canPayrollRead ? 8 : 7} icon={MagnifyingGlass} title="No matches" hint="Try a different search or filter." />
              ))}
            </tbody>
          </table>{filteredPager}</div>
        </div>
      )}
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
