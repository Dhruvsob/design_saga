import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../lib/api";
import { safeExternalUrl } from "../lib/url";
import { useAuth } from "../context/AuthContext";
import { dateForInput, formatDate, formatINR, statusLabel } from "../lib/format";
import EmployeeAdvances from "../components/EmployeeAdvances";
import {
  ArrowLeft, FloppyDisk, Plus, Trash, PencilSimple, UserMinus, Warning, Trophy,
  FileText, ArrowSquareOut, ShieldWarning,
  TrendUp, ClockCounterClockwise, Key, Receipt,
} from "@phosphor-icons/react";
import { askForm, confirmAction } from "../lib/confirm";
import useUnsavedWarning from "../lib/useUnsavedWarning";
import RowActions from "../components/RowActions";
import { PaySalaryBlock, cancelSalaryRun, editSalaryRun, salaryPeriod, salarySlipPath } from "../components/SalaryPayment";

const TABS = ["Overview", "Employment", "Salary & Bank", "Documents", "Performance", "ERP Access"];
const fmt = (n) => formatINR(n, { decimals: 0 });
const STATUS_CHIP = {
  active: "chip-paid", probation: "chip-medium",
  notice: "chip-overdue", terminated: "chip-draft",
};

export default function EmployeeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { hasPerm, user } = useAuth();
  const [emp, setEmp] = useState(null);
  const [meta, setMeta] = useState({ departments: [], employment_types: [], employment_statuses: [] });
  const [tab, setTab] = useState("Overview");
  const [advanceVersion, setAdvanceVersion] = useState(0);
  const [dirty, setDirty] = useState(false);
  useUnsavedWarning(dirty);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const canEdit = hasPerm("employees.update");
  const canDelete = hasPerm("employees.delete") || user?.role === "Admin";
  const canPayrollRead = hasPerm("payroll.read");
  const canPayrollWrite = hasPerm("payroll.create");
  const canCorrectPayroll = canPayrollWrite && hasPerm("finance.update");
  const canReadUsers = hasPerm("users.read");
  const visibleTabs = TABS.filter((name) => {
    if (name === "Salary & Bank") return canPayrollRead;
    if (name === "Documents" || name === "Performance") return canEdit;
    if (name === "ERP Access") return canReadUsers;
    return true;
  });

  const load = useCallback(async () => {
    try {
      const [e, m] = await Promise.all([
        api.get(`/employees/${id}`),
        api.get("/employees/meta"),
      ]);
      setEmp(e.data);
      setMeta(m.data);
      setDirty(false);
      setErr("");
    } catch (ex) {
      setErr(ex?.response?.data?.detail || "Failed to load");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const patch = (updater) => {
    setEmp((prev) => ({ ...prev, ...updater(prev) }));
    setDirty(true);
  };

  const patchSalary = (k, v) => patch((p) => ({
    salary: { ...(p.salary || {}), [k]: v === "" ? "" : Number(v) },
  }));
  const patchBank = (k, v) => patch((p) => ({ bank: { ...(p.bank || {}), [k]: v } }));
  const patchEmergency = (k, v) => patch((p) => ({
    emergency_contact: { ...(p.emergency_contact || {}), [k]: v },
  }));

  const save = async () => {
    if (!emp) return;
    setSaving(true); setErr("");
    try {
      const payload = { ...emp };
      // strip readonly-ish fields
      delete payload.id; delete payload.employee_id;
      delete payload.documents; delete payload.performance;
      delete payload.created_at; delete payload.created_by;
      delete payload._id;
      if (!canPayrollWrite) {
        delete payload.salary; delete payload.salary_history;
        delete payload.monthly_salary; delete payload.payroll_basis_days;
        delete payload.bank;
      }
      const { data } = await api.put(`/employees/${id}`, payload);
      setEmp(data);
      setDirty(false);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!await confirmAction("Terminate this employee? Their login will be disabled, while attendance, payroll, and accounting history will be retained.")) return;
    await api.delete(`/employees/${id}`);
    navigate("/employees");
  };

  // For someone added by mistake: allowed only when there is no salary/accounting history.
  const removeForever = async () => {
    const name = [emp?.first_name, emp?.last_name].filter(Boolean).join(" ") || "this employee";
    if (!await confirmAction(`Delete ${name} permanently? Their attendance and leave records are deleted too. This cannot be undone.`)) return;
    try {
      await api.delete(`/employees/${id}/permanent`);
      toast.success(`${name} deleted`);
      navigate("/employees");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not delete this employee");
    }
  };

  const addWarning = async () => {
    const v = await askForm({ title: "Add warning", fields: [
      { name: "reason", label: "Reason", required: true },
      { name: "note", label: "Additional note", multiline: true },
    ] });
    if (!v) return;
    await api.post(`/employees/${id}/warnings`, v);
    load();
  };

  const addReward = async () => {
    const v = await askForm({ title: "Add reward", fields: [
      { name: "title", label: "Reward title", required: true },
      { name: "note", label: "Description", multiline: true },
    ] });
    if (!v) return;
    await api.post(`/employees/${id}/rewards`, v);
    load();
  };

  const editWarning = async (warning) => {
    const v = await askForm({ title: "Edit warning", fields: [
      { name: "reason", label: "Reason", required: true, defaultValue: warning.reason || "" },
      { name: "note", label: "Additional note", multiline: true, defaultValue: warning.note || "" },
    ] });
    if (!v) return;
    await api.patch(`/employees/${id}/warnings/${warning.id}`, v);
    await load();
  };

  const deleteWarning = async (warning) => {
    if (!await confirmAction("Delete this warning? The action will remain in the audit log.")) return;
    await api.delete(`/employees/${id}/warnings/${warning.id}`);
    await load();
  };

  const editReward = async (reward) => {
    const v = await askForm({ title: "Edit reward", fields: [
      { name: "title", label: "Reward title", required: true, defaultValue: reward.title || "" },
      { name: "note", label: "Description", multiline: true, defaultValue: reward.note || "" },
    ] });
    if (!v) return;
    await api.patch(`/employees/${id}/rewards/${reward.id}`, v);
    await load();
  };

  const deleteReward = async (reward) => {
    if (!await confirmAction("Delete this reward? The action will remain in the audit log.")) return;
    await api.delete(`/employees/${id}/rewards/${reward.id}`);
    await load();
  };

  const addDocument = async () => {
    const v = await askForm({ title: "Add document", fields: [
      { name: "label", label: "Label", required: true, placeholder: "e.g. Aadhaar, Offer letter" },
      { name: "url", label: "Link (URL)", required: true, type: "url", placeholder: "https://…" },
    ] });
    if (!v) return;
    await api.post(`/employees/${id}/documents`, v);
    load();
  };

  const removeDocument = async (docId) => {
    if (!await confirmAction("Remove this document?")) return;
    await api.delete(`/employees/${id}/documents/${docId}`);
    load();
  };

  const editDocument = async (document) => {
    const v = await askForm({ title: "Edit document", fields: [
      { name: "label", label: "Label", required: true, defaultValue: document.label || "" },
      { name: "url", label: "Link (URL)", required: true, type: "url", defaultValue: document.url || "" },
    ] });
    if (!v) return;
    await api.patch(`/employees/${id}/documents/${document.id}`, v);
    await load();
  };

  if (!emp) {
    return (
      <div className="space-y-4" data-testid="emp-detail-loading">
        <div className="skeleton h-8 w-48" />
        <div className="skeleton h-32 w-full" />
        {err && <p className="text-sm text-[var(--danger)]">{err}</p>}
      </div>
    );
  }

  const perf = emp.performance || { warnings: [], rewards: [], current_kpi_score: 0 };
  const s = emp.salary || {};

  return (
    <div className="space-y-8 pb-16" data-testid="emp-detail">
      <Link to="/employees" className="inline-flex items-center gap-1 text-sm text-[var(--ink-2)] hover:text-[var(--ink)]">
        <ArrowLeft size={14} /> All employees
      </Link>

      {/* Header */}
      <div className="border border-[var(--line)] p-6 flex flex-wrap gap-6 items-start justify-between bg-white">
        <div className="flex items-start gap-5 flex-1 min-w-[280px]">
          {emp.photo ? (
            <img src={emp.photo} alt="" className="w-20 h-20 object-cover ring-1 ring-[var(--line)]" />
          ) : (
            <div className="w-20 h-20 bg-[var(--ink)] text-white flex items-center justify-center font-display font-bold text-3xl">
              {(emp.first_name || "?").slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <div className="overline mb-2 flex items-center gap-3 flex-wrap">
              {emp.employee_id}
              <span className={`status-chip ${STATUS_CHIP[emp.employment_status] || "chip-draft"}`}>{statusLabel(emp.employment_status)}</span>
              <span className="status-chip chip-medium no-dot">{emp.employment_type?.replace("_", " ")}</span>
            </div>
            <h1 className="font-display font-bold tracking-tighter text-3xl">
              {emp.first_name} {emp.last_name}
            </h1>
            <div className="mt-2 text-sm text-[var(--ink-2)]">
              {emp.designation || "—"} · {emp.department}
              {emp.joining_date && <> · joined {formatDate(emp.joining_date)}</>}
            </div>
          </div>
        </div>
        {canPayrollRead && (
          <div className="text-right">
            <div className="overline">NET / MONTH</div>
            <div className="font-display font-bold text-3xl tracking-tighter accent-blue">{fmt(s.net_monthly)}</div>
            <div className="overline mt-1">CTC {fmt(s.ctc_annual)}</div>
          </div>
        )}
      </div>

      {err && (
        <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)] flex items-center gap-2">
          <ShieldWarning size={16} /> {err}
        </div>
      )}

      {/* Actions */}
      {canEdit && (
        <div className="flex flex-wrap gap-2">
          <button onClick={save} disabled={!dirty || saving} className="btn-primary" data-testid="emp-save-btn">
            <FloppyDisk size={14} /> {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
          <button onClick={addWarning} className="btn-ghost" data-testid="emp-warning-btn">
            <Warning size={14} /> Log warning
          </button>
          <button onClick={addReward} className="btn-ghost" data-testid="emp-reward-btn">
            <Trophy size={14} /> Log reward
          </button>
          <button onClick={addDocument} className="btn-ghost" data-testid="emp-doc-btn">
            <FileText size={14} /> Add document
          </button>
          {canDelete && emp?.employment_status !== "terminated" && (
            <button onClick={remove} className="btn-ghost ml-auto" style={{ color: "#B22B22", borderColor: "#B22B22" }}>
              <UserMinus size={14} /> Terminate
            </button>
          )}
          {canDelete && emp?.employment_status === "terminated" && (
            <button onClick={removeForever} className="btn-ghost ml-auto" style={{ color: "#B22B22", borderColor: "#B22B22" }}
              data-testid="emp-delete-permanent">
              <Trash size={14} /> Delete permanently
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-[var(--line)]">
        {visibleTabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            data-testid={`emp-tab-${t.replace(/[\s&]/g, "-")}`}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition ${
              tab === t ? "border-[var(--accent)] text-[var(--accent-strong)]" : "border-transparent text-[var(--ink-2)] hover:text-[var(--ink)]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab body */}
      {tab === "Overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="emp-tab-overview">
          <Card title="PERSONAL">
            <Row label="First name">
              <input disabled={!canEdit} className="input-flat" value={emp.first_name || ""} onChange={(e) => patch(() => ({ first_name: e.target.value }))} />
            </Row>
            <Row label="Last name">
              <input disabled={!canEdit} className="input-flat" value={emp.last_name || ""} onChange={(e) => patch(() => ({ last_name: e.target.value }))} />
            </Row>
            <Row label="Email">
              <input disabled={!canEdit} className="input-flat" value={emp.email || ""} onChange={(e) => patch(() => ({ email: e.target.value }))} />
            </Row>
            <Row label="Phone">
              <input disabled={!canEdit} className="input-flat" value={emp.phone || ""} onChange={(e) => patch(() => ({ phone: e.target.value }))} />
            </Row>
            <Row label="Photo URL">
              <input disabled={!canEdit} className="input-flat" value={emp.photo || ""} onChange={(e) => patch(() => ({ photo: e.target.value }))} placeholder="https://…" />
            </Row>
            {canEdit && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Row label="Date of birth">
                    <input type="date" className="input-flat" value={emp.dob || ""} onChange={(e) => patch(() => ({ dob: e.target.value }))} />
                  </Row>
                  <Row label="Gender">
                    <select aria-label="Gender" className="input-flat" value={emp.gender || ""} onChange={(e) => patch(() => ({ gender: e.target.value }))}>
                      <option value="">—</option>
                      <option value="Female">Female</option>
                      <option value="Male">Male</option>
                      <option value="Other">Other</option>
                      <option value="Prefer not to say">Prefer not to say</option>
                    </select>
                  </Row>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Row label="Blood group">
                    <input className="input-flat" value={emp.blood_group || ""} onChange={(e) => patch(() => ({ blood_group: e.target.value }))} />
                  </Row>
                  <Row label="Aadhaar">
                    <input className="input-flat" value={emp.aadhaar || ""} onChange={(e) => patch(() => ({ aadhaar: e.target.value }))} />
                  </Row>
                </div>
                <Row label="PAN">
                  <input className="input-flat" value={emp.pan || ""} onChange={(e) => patch(() => ({ pan: e.target.value }))} />
                </Row>
              </>
            )}
          </Card>

          {canEdit && <Card title="ADDRESS & EMERGENCY">
            <Row label="Address">
              <textarea disabled={!canEdit} rows={2} className="input-flat" value={emp.address || ""} onChange={(e) => patch(() => ({ address: e.target.value }))} />
            </Row>
            <div className="grid grid-cols-3 gap-3">
              <Row label="City">
                <input disabled={!canEdit} className="input-flat" value={emp.city || ""} onChange={(e) => patch(() => ({ city: e.target.value }))} />
              </Row>
              <Row label="State">
                <input disabled={!canEdit} className="input-flat" value={emp.state || ""} onChange={(e) => patch(() => ({ state: e.target.value }))} />
              </Row>
              <Row label="Pincode">
                <input disabled={!canEdit} className="input-flat" value={emp.pincode || ""} onChange={(e) => patch(() => ({ pincode: e.target.value }))} />
              </Row>
            </div>
            <div className="border-t border-[var(--line-soft)] pt-4 mt-2">
              <div className="overline mb-3">EMERGENCY CONTACT</div>
              <div className="grid grid-cols-3 gap-3">
                <Row label="Name">
                  <input disabled={!canEdit} className="input-flat" value={emp.emergency_contact?.name || ""} onChange={(e) => patchEmergency("name", e.target.value)} />
                </Row>
                <Row label="Phone">
                  <input disabled={!canEdit} className="input-flat" value={emp.emergency_contact?.phone || ""} onChange={(e) => patchEmergency("phone", e.target.value)} />
                </Row>
                <Row label="Relation">
                  <input disabled={!canEdit} className="input-flat" value={emp.emergency_contact?.relation || ""} onChange={(e) => patchEmergency("relation", e.target.value)} />
                </Row>
              </div>
            </div>
          </Card>}
        </div>
      )}

      {tab === "Employment" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="emp-tab-employment">
          <Card title="ROLE & TEAM">
            <Row label="Department">
              <select aria-label="Department" disabled={!canEdit} className="input-flat" value={emp.department || ""} onChange={(e) => patch(() => ({ department: e.target.value }))}>
                {meta.departments.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </Row>
            <Row label="Designation">
              <input disabled={!canEdit} className="input-flat" value={emp.designation || ""} onChange={(e) => patch(() => ({ designation: e.target.value }))} />
            </Row>
            <Row label="Employment type">
              <select aria-label="Employment type" disabled={!canEdit} className="input-flat" value={emp.employment_type || ""} onChange={(e) => patch(() => ({ employment_type: e.target.value }))}>
                {meta.employment_types.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
              </select>
            </Row>
            <Row label="Status">
              <select aria-label="Employment status" disabled={!canEdit} className="input-flat" value={emp.employment_status || ""} onChange={(e) => patch(() => ({ employment_status: e.target.value }))}>
                {meta.employment_statuses.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Row>
          </Card>

          <Card title="DATES & SHIFT">
            <div className="grid grid-cols-2 gap-3">
              <Row label="Joining date">
                <input disabled={!canEdit} type="date" className="input-flat" value={emp.joining_date || ""} onChange={(e) => patch(() => ({ joining_date: e.target.value }))} />
              </Row>
              <Row label="Probation ends">
                <input disabled={!canEdit} type="date" className="input-flat" value={emp.probation_end_date || ""} onChange={(e) => patch(() => ({ probation_end_date: e.target.value }))} />
              </Row>
              <Row label="Notice period (days)">
                <input disabled={!canEdit} type="number" min="0" className="input-flat" placeholder="Enter days" value={emp.notice_period_days ?? ""} onChange={(e) => patch(() => ({ notice_period_days: e.target.value === "" ? "" : Number(e.target.value) }))} />
              </Row>
              <Row label="Weekly hours">
                <input disabled={!canEdit} type="number" min="0" className="input-flat" placeholder="Enter hours" value={emp.weekly_hours ?? ""} onChange={(e) => patch(() => ({ weekly_hours: e.target.value === "" ? "" : Number(e.target.value) }))} />
              </Row>
              <Row label="Shift start">
                <input disabled={!canEdit} type="time" className="input-flat" value={emp.shift_start || ""} onChange={(e) => patch(() => ({ shift_start: e.target.value }))} />
              </Row>
              <Row label="Shift end">
                <input disabled={!canEdit} type="time" className="input-flat" value={emp.shift_end || ""} onChange={(e) => patch(() => ({ shift_end: e.target.value }))} />
              </Row>
            </div>
          </Card>
        </div>
      )}

      {tab === "Salary & Bank" && canPayrollRead && (
        <div className="space-y-6" data-testid="emp-tab-salary">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card title="EARNINGS (MONTHLY)" testid="salary-earnings">
            {["basic", "hra", "conveyance", "medical", "other_allowances"].map((k) => (
              <Row key={k} label={k.replace("_", " ").toUpperCase()}>
                <input disabled={!canPayrollWrite} type="number" min="0" className="input-flat text-right font-mono" placeholder="Enter amount" value={s[k] ?? ""} onChange={(e) => patchSalary(k, e.target.value)} />
              </Row>
            ))}
            <div className="border-t border-[var(--ink)] mt-2 pt-3 flex items-center justify-between">
              <div className="font-display font-bold">Gross</div>
              <div className="font-mono font-bold">{fmt(s.gross_monthly)}</div>
            </div>
          </Card>

          <Card title="DEDUCTIONS (MONTHLY)" testid="salary-deductions">
            {["pf_employee", "esi_employee", "professional_tax", "tds"].map((k) => (
              <Row key={k} label={k.replace("_", " ").toUpperCase()}>
                <input disabled={!canPayrollWrite} type="number" min="0" className="input-flat text-right font-mono" placeholder="Enter amount" value={s[k] ?? ""} onChange={(e) => patchSalary(k, e.target.value)} />
              </Row>
            ))}
            <div className="border-t border-[var(--ink)] mt-2 pt-3 flex items-center justify-between">
              <div className="font-display font-bold">Total deductions</div>
              <div className="font-mono font-bold">{fmt(s.total_deductions)}</div>
            </div>
            <div className="mt-3 border border-[var(--ink)] p-4 bg-[var(--surface-2)]">
              <div className="overline mb-1">NET / MONTH</div>
              <div className="font-display font-bold text-3xl tracking-tighter accent-blue">{fmt(s.net_monthly)}</div>
              <div className="text-xs text-[var(--ink-2)] mt-1">CTC · {fmt(s.ctc_annual)} / year</div>
            </div>
          </Card>

          <Card title="BANK DETAILS" testid="salary-bank">
            <Row label="Account holder">
              <input disabled={!canPayrollWrite} className="input-flat" value={emp.bank?.account_holder || ""} onChange={(e) => patchBank("account_holder", e.target.value)} />
            </Row>
            <Row label="Account number">
              <input disabled={!canPayrollWrite} className="input-flat font-mono" value={emp.bank?.account_number || ""} onChange={(e) => patchBank("account_number", e.target.value)} />
            </Row>
            <Row label="IFSC">
              <input disabled={!canPayrollWrite} className="input-flat font-mono" value={emp.bank?.ifsc || ""} onChange={(e) => patchBank("ifsc", e.target.value)} />
            </Row>
            <Row label="Bank name">
              <input disabled={!canPayrollWrite} className="input-flat" value={emp.bank?.bank_name || ""} onChange={(e) => patchBank("bank_name", e.target.value)} />
            </Row>
            <Row label="UPI">
              <input disabled={!canPayrollWrite} className="input-flat font-mono" value={emp.bank?.upi || ""} onChange={(e) => patchBank("upi", e.target.value)} />
            </Row>
          </Card>
          </div>

          {canPayrollWrite && (
            <PaySalaryBlock employeeId={emp.id} netMonthly={s.net_monthly} advanceVersion={advanceVersion} />
          )}

          <EmployeeAdvances employeeId={emp.id} canWrite={canPayrollWrite}
                            onChanged={() => setAdvanceVersion((v) => v + 1)} />

          <SalaryRevisionsBlock employeeId={emp.id} currentSalary={s} canEdit={canPayrollWrite} />

          <PaymentHistoryBlock employeeId={emp.id} canCorrect={canCorrectPayroll} />
        </div>
      )}

      {tab === "Documents" && (
        <Card title={`DOCUMENTS · ${(emp.documents || []).length}`}
              actions={canEdit && <button onClick={addDocument} className="btn-ghost text-xs"><Plus size={12} /> Add</button>}
              testid="emp-tab-documents">
          {(emp.documents || []).length === 0 ? (
            <p className="text-sm text-[var(--ink-2)]">No documents yet. Add offer letter, Aadhaar, PAN, contract etc.</p>
          ) : (
            <div className="space-y-2">
              {(emp.documents || []).map((d) => {
                const safeUrl = safeExternalUrl(d.url);
                return (
                <div key={d.id} className="border border-[var(--line)] p-3 flex items-center justify-between hover:border-[var(--ink)] transition">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm">{d.label}</div>
                    <div className="text-xs text-[var(--ink-2)] font-mono truncate">{d.url}</div>
                    <div className="text-[10px] text-[var(--ink-3)] font-mono tracking-widest uppercase mt-1">
                      UPLOADED {formatDate(d.uploaded_at)} · {d.uploaded_by || "—"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {safeUrl && (
                      <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="btn-ghost text-xs">
                        <ArrowSquareOut size={12} /> Open
                      </a>
                    )}
                    {canEdit && (
                      <RowActions label={d.label || "document"} testid={`doc-actions-${d.id}`} actions={[
                        { label: "Edit document", icon: PencilSimple, onSelect: () => editDocument(d) },
                        { divider: true },
                        { label: "Remove document", icon: Trash, danger: true, onSelect: () => removeDocument(d.id) },
                      ]} />
                    )}
                  </div>
                </div>
                );
              })}
            </div>
          )}
        </Card>
      )}

      {tab === "Performance" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="emp-tab-performance">
          <Card title="CURRENT KPI">
            <div className="text-center py-4">
              <div className="font-display font-bold tracking-tighter text-6xl accent-blue">
                {perf.current_kpi_score || 0}
              </div>
              <div className="overline mt-2">SCORE / 100</div>
            </div>
            {canEdit && (
              <Row label="Update KPI (0-100)">
                <input type="number" min={0} max={100} className="input-flat" placeholder="Enter score (0-100)" value={perf.current_kpi_score ?? ""} onChange={(e) => patch(() => ({ current_kpi_score: e.target.value === "" ? "" : Number(e.target.value) }))} />
              </Row>
            )}
            <div className="mt-3 h-2 bg-[var(--line-soft)] relative">
              <div className="h-2 bg-[var(--accent)]" style={{ width: `${Math.min(100, Math.max(0, perf.current_kpi_score || 0))}%` }} />
            </div>
          </Card>

          <Card title={`WARNINGS · ${(perf.warnings || []).length}`}
                actions={canEdit && <button onClick={addWarning} className="btn-ghost text-xs"><Plus size={12} /> Log</button>}>
            {(perf.warnings || []).length === 0 ? (
              <p className="text-sm text-[var(--ink-2)]">No warnings recorded.</p>
            ) : (
              <div className="space-y-2">
                {[...(perf.warnings || [])].reverse().map((w) => (
                  <div key={w.id} className="border-l-2 border-[var(--danger)] pl-3 py-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-semibold text-sm">{w.reason}</div>
                      {canEdit && <RowActions label="warning" testid={`warning-actions-${w.id}`} actions={[
                        { label: "Edit warning", icon: PencilSimple, onSelect: () => editWarning(w) },
                        { divider: true },
                        { label: "Delete warning", icon: Trash, danger: true, onSelect: () => deleteWarning(w) },
                      ]} />}
                    </div>
                    {w.note && <p className="text-xs text-[var(--ink-2)] mt-1">{w.note}</p>}
                    <div className="text-[10px] font-mono tracking-widest uppercase text-[var(--ink-3)] mt-1">
                      {formatDate(w.at)} · {w.by || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title={`REWARDS · ${(perf.rewards || []).length}`}
                actions={canEdit && <button onClick={addReward} className="btn-ghost text-xs"><Plus size={12} /> Log</button>}>
            {(perf.rewards || []).length === 0 ? (
              <p className="text-sm text-[var(--ink-2)]">No rewards yet.</p>
            ) : (
              <div className="space-y-2">
                {[...(perf.rewards || [])].reverse().map((r) => (
                  <div key={r.id} className="border-l-2 border-[var(--success)] pl-3 py-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-semibold text-sm">{r.title}</div>
                      {canEdit && <RowActions label="reward" testid={`reward-actions-${r.id}`} actions={[
                        { label: "Edit reward", icon: PencilSimple, onSelect: () => editReward(r) },
                        { divider: true },
                        { label: "Delete reward", icon: Trash, danger: true, onSelect: () => deleteReward(r) },
                      ]} />}
                    </div>
                    {r.note && <p className="text-xs text-[var(--ink-2)] mt-1">{r.note}</p>}
                    <div className="text-[10px] font-mono tracking-widest uppercase text-[var(--ink-3)] mt-1">
                      {formatDate(r.at)} · {r.by || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === "ERP Access" && (
        <ErpAccessTab employeeId={id} isAdmin={user?.role === "Admin" || user?.is_super_admin} />
      )}
    </div>
  );
}

function Card({ title, children, actions, testid }) {
  return (
    <div className="card-flat" data-testid={testid}>
      <div className="flex items-center justify-between mb-4">
        <div className="overline">{title}</div>
        {actions}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Row({ label, children }) {
  return (
    <label className="block">
      <div className="overline mb-1">{label}</div>
      {children}
    </label>
  );
}

function ErpAccessTab({ employeeId, isAdmin }) {
  const [acct, setAcct] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", role: "Employee" });
  const [roles, setRoles] = useState(["Admin", "Director", "ProjectManager", "Accountant", "HR", "Employee"]);
  const [newPass, setNewPass] = useState("");
  const [pwMsg, setPwMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api.get(`/employees/${employeeId}/account`);
      setAcct(r.data);
      setErr("");
    } catch (ex) {
      setErr(ex?.response?.data?.detail || "Failed to load account");
    }
  }, [employeeId]);

  useEffect(() => {
    load();
    api.get("/rbac/roles").then((r) => {
      const list = Array.isArray(r.data) ? r.data : (r.data?.roles || []);
      const names = list.map((x) => (typeof x === "string" ? x : x?.name)).filter(Boolean);
      if (names.length) setRoles(names.filter((n) => n !== "SuperAdmin"));
    }).catch(() => {});
  }, [load]);

  const createAccount = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.post(`/employees/${employeeId}/account`, {
        password: form.password, role: form.role,
        ...(form.email ? { email: form.email } : {}),
      });
      setForm({ email: "", password: "", role: "Employee" });
      await load();
    } catch (ex) {
      setErr(ex?.response?.data?.detail || "Failed to create login");
    } finally { setBusy(false); }
  };

  const changeRole = async (role) => {
    if (!acct?.user?.user_id) return;
    try {
      await api.patch(`/rbac/users/${acct.user.user_id}/role`, { role });
      await load();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Role change failed");
    }
  };

  const toggleActive = async () => {
    try {
      await api.post(`/employees/${employeeId}/account/status`, { active: !(acct?.user?.is_active ?? true) });
      await load();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Status change failed");
    }
  };

  const resetPassword = async () => {
    if (!/^(?=.*[A-Za-z])(?=.*\d).{8,128}$/.test(newPass)) {
      setPwMsg("Password must be 8–128 characters and include a letter and a digit");
      return;
    }
    setPwMsg("");
    try {
      await api.post(`/employees/${employeeId}/account/reset-password`, { password: newPass });
      setNewPass("");
      setPwMsg("Password reset. All sessions and the old app PIN were cleared; the employee must sign in again.");
    } catch (ex) {
      setPwMsg(ex?.response?.data?.detail || "Reset failed");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="emp-tab-erp-access">
      <Card title="ERP LOGIN" testid="erp-access-card">
        {err && <div className="text-xs text-[var(--danger)] border border-[var(--danger)] bg-[var(--danger-soft)] p-2">{String(err)}</div>}
        {!acct && !err && <div className="skeleton h-24 w-full" />}
        {acct && acct.linked && (
          <div className="space-y-3">
            <Row label="Email / Login"><div className="font-mono text-sm">{acct.user.email}</div></Row>
            <Row label="Employee ID"><div className="font-mono text-sm">{acct.user.employee_id || "—"}</div></Row>
            <Row label="Status">
              <span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${acct.user.is_active !== false ? "bg-[var(--success-soft)] text-[var(--success)]" : "bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
                {acct.user.is_active !== false ? "active" : "deactivated"}
              </span>
            </Row>
            <Row label="Last login">
              <div className="font-mono text-xs">{(acct.user.last_login || "never").slice(0, 19).replace("T", " ")}</div>
            </Row>
            {isAdmin && (
              <>
                <Row label="Role">
                  <select aria-label="Role" className="input-flat" value={acct.user.role || "Employee"}
                          onChange={(e) => changeRole(e.target.value)} data-testid="erp-role-select">
                    {roles.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </Row>
                <button onClick={toggleActive} className="btn-ghost text-xs" data-testid="erp-toggle-active">
                  {acct.user.is_active !== false ? "Deactivate login" : "Reactivate login"}
                </button>
                <div className="border-t border-[var(--line)] pt-3 mt-1 space-y-2">
                  <div className="overline flex items-center gap-1.5"><Key size={12} /> Reset password</div>
                  <div className="flex items-center gap-2">
                    <input type="password" minLength={8} maxLength={128} autoComplete="new-password"
                           className="input-flat flex-1" placeholder="Letters + digits, min 8"
                           value={newPass} onChange={(e) => setNewPass(e.target.value)}
                           data-testid="erp-reset-password-input" />
                    <button type="button" onClick={resetPassword}
                            disabled={!/^(?=.*[A-Za-z])(?=.*\d).{8,128}$/.test(newPass)}
                            className="btn-ghost text-xs disabled:opacity-40" data-testid="erp-reset-password-btn">Set</button>
                  </div>
                  {pwMsg && <div className="text-[11px] text-[var(--accent-strong)]" data-testid="erp-reset-password-msg">{pwMsg}</div>}
                </div>
              </>
            )}
          </div>
        )}
        {acct && !acct.linked && !isAdmin && (
          <p className="text-sm text-[var(--ink-2)]">No ERP login linked. Ask an Admin to create one.</p>
        )}
        {acct && !acct.linked && isAdmin && (
          <form onSubmit={createAccount} className="space-y-3" data-testid="erp-create-form">
            <p className="text-xs text-[var(--ink-2)]">
              No ERP login yet — create one so this employee can sign in with role-based access.
            </p>
            <Row label="Email (defaults to employee email)">
              <input className="input-flat" type="email" value={form.email}
                     onChange={(e) => setForm({ ...form, email: e.target.value })}
                     placeholder="Leave blank to use employee email" />
            </Row>
            <Row label="Temporary password (letters + digits, min 8)">
              <input className="input-flat" type="password" required minLength={8} maxLength={128}
                     autoComplete="new-password" pattern="(?=.*[A-Za-z])(?=.*\d).{8,128}"
                     title="Use at least 8 characters with at least one letter and one digit"
                     value={form.password}
                     onChange={(e) => setForm({ ...form, password: e.target.value })}
                     data-testid="erp-create-password" />
            </Row>
            <Row label="Role">
              <select aria-label="Role" className="input-flat" value={form.role}
                      onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="erp-create-role">
                {roles.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Row>
            <button type="submit" disabled={busy} className="btn-primary text-xs" data-testid="erp-create-btn">
              {busy ? "Creating…" : "Create ERP login"}
            </button>
          </form>
        )}
      </Card>
      <Card title="HOW ACCESS WORKS">
        <ul className="text-xs text-[var(--ink-2)] space-y-2 list-disc pl-4">
          <li>Each employee can have one ERP login tied to their Employee ID.</li>
          <li>The role controls what they can see and do — enforced by the server on every request.</li>
          <li>Deactivating a login instantly ends all of that person's sessions.</li>
          <li>An Admin password reset signs the employee out everywhere and clears any old app PIN.</li>
        </ul>
      </Card>
    </div>
  );
}


const EARN_KEYS = ["basic", "hra", "conveyance", "medical", "other_allowances"];
const DED_KEYS = ["pf_employee", "esi_employee", "professional_tax", "tds"];

function SalaryRevisionsBlock({ employeeId, currentSalary, canEdit }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [correctingId, setCorrectingId] = useState(null);
  const today = dateForInput(new Date());
  const [form, setForm] = useState({ effective_date: today, reason: "", note: "", salary: {} });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/employees/${employeeId}/salary/history`);
      setHistory(data?.history || []);
    } catch {
      setHistory([]);
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => { load(); }, [load]);

  const openForm = (revision = null) => {
    const base = {};
    const source = revision?.salary || currentSalary || {};
    [...EARN_KEYS, ...DED_KEYS].forEach((k) => { base[k] = source[k] ?? 0; });
    setForm({
      effective_date: revision?.effective_date || today,
      reason: revision ? `Correction: ${revision.reason || "salary revision"}` : "",
      note: revision?.note || "",
      salary: base,
    });
    setCorrectingId(revision?.id || null);
    setMsg("");
    setOpen(true);
  };

  const setAmt = (k, v) => setForm((f) => ({ ...f, salary: { ...f.salary, [k]: v === "" ? 0 : Number(v) } }));
  const previewGross = EARN_KEYS.reduce((a, k) => a + Number(form.salary[k] || 0), 0);
  const previewDed = DED_KEYS.reduce((a, k) => a + Number(form.salary[k] || 0), 0);
  const previewNet = previewGross - previewDed;
  const deltaNet = previewNet - Number(currentSalary?.net_monthly || 0);
  const latestActiveId = history.find((row) => !row.superseded_at)?.id;

  const save = async () => {
    if (!form.effective_date) { setMsg("Effective date is required"); return; }
    setBusy(true); setMsg("");
    try {
      const endpoint = correctingId
        ? `/employees/${employeeId}/salary/revisions/${correctingId}/supersede`
        : `/employees/${employeeId}/salary/increment`;
      await api.post(endpoint, {
        effective_date: form.effective_date,
        reason: form.reason,
        note: form.note,
        salary: form.salary,
        apply_now: true,
      });
      setOpen(false);
      setCorrectingId(null);
      await load();
    } catch (ex) {
      setMsg(ex?.response?.data?.detail || "Could not save the revision");
    } finally { setBusy(false); }
  };

  return (
    <div className="card-flat" data-testid="salary-revisions-block">
      <div className="flex items-center justify-between mb-4">
        <div className="overline flex items-center gap-1.5"><TrendUp size={13} /> SALARY REVISIONS · effective-dated increments</div>
        {canEdit && !open && (
          <button onClick={() => openForm()} className="btn-ghost text-xs" data-testid="salary-revision-add-btn">
            <Plus size={13} /> Record increment
          </button>
        )}
      </div>

      {open && (
        <div className="border border-[var(--ink)] p-4 mb-4 space-y-3" data-testid="salary-revision-form">
          {correctingId && <div className="text-xs border border-[var(--warning)] bg-[var(--warning-soft)] p-2">
            This correction preserves the original revision as superseded and creates a replacement.
          </div>}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-xs">
              <div className="overline mb-1">Effective from</div>
              <input type="date" className="input-flat w-full" value={form.effective_date}
                     onChange={(e) => setForm({ ...form, effective_date: e.target.value })}
                     data-testid="salary-revision-date" />
            </label>
            <label className="text-xs md:col-span-2">
              <div className="overline mb-1">Reason</div>
              <input className="input-flat w-full" placeholder="Annual increment, promotion…"
                     value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}
                     data-testid="salary-revision-reason" />
            </label>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {EARN_KEYS.map((k) => (
              <label key={k} className="text-xs">
                <div className="overline mb-1">{k.replace(/_/g, " ")}</div>
                <input type="number" min="0" className="input-flat w-full text-right font-mono" value={form.salary[k] ?? 0}
                       onChange={(e) => setAmt(k, e.target.value)} data-testid={`salary-revision-${k}`} />
              </label>
            ))}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {DED_KEYS.map((k) => (
              <label key={k} className="text-xs">
                <div className="overline mb-1">{k.replace(/_/g, " ")}</div>
                <input type="number" min="0" className="input-flat w-full text-right font-mono" value={form.salary[k] ?? 0}
                       onChange={(e) => setAmt(k, e.target.value)} data-testid={`salary-revision-${k}`} />
              </label>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-4 border-t border-[var(--line)] pt-3">
            <div><span className="overline">New gross</span> <span className="font-mono font-bold ml-1">{fmt(previewGross)}</span></div>
            <div><span className="overline">New net</span> <span className="font-mono font-bold ml-1 accent-blue">{fmt(previewNet)}</span></div>
            <div>
              <span className="overline">Change</span>{" "}
              <span className={`font-mono font-bold ml-1 ${deltaNet >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`} data-testid="salary-revision-delta">
                {deltaNet >= 0 ? "+" : ""}{fmt(deltaNet)}
              </span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button onClick={() => { setOpen(false); setCorrectingId(null); }} className="btn-ghost text-xs">Cancel</button>
              <button onClick={save} disabled={busy} className="btn-primary text-xs disabled:opacity-40" data-testid="salary-revision-save-btn">
                {busy ? "Saving…" : correctingId ? "Save correction" : "Save revision"}
              </button>
            </div>
          </div>
          {msg && <div className="text-xs text-[var(--danger)]">{msg}</div>}
        </div>
      )}

      {loading ? (
        <div className="skeleton h-16 w-full" />
      ) : history.length === 0 ? (
        <div className="text-xs text-[var(--ink-3)] py-4 text-center border border-dashed border-[var(--line)]" data-testid="salary-history-empty">
          No revisions recorded yet. Record an increment to start a history — past payslips remain unchanged.
        </div>
      ) : (
        <div className="space-y-2" data-testid="salary-history-list">
          {history.map((h) => (
            <div key={h.id} className={`flex items-center justify-between border border-[var(--line)] px-3 py-2 ${h.superseded_at ? "bg-[var(--hover)] opacity-70" : "bg-[var(--surface-2)]"}`} data-testid={`salary-history-${h.id}`}>
              <div className="min-w-0">
                <div className="text-sm font-semibold flex items-center gap-2">
                  <ClockCounterClockwise size={13} className="text-[var(--accent-strong)]" />
                  {h.reason || "Salary revision"}
                  {h.superseded_at && <span className="text-[9px] font-mono uppercase border px-1">Superseded</span>}
                </div>
                <div className="text-[11px] text-[var(--ink-2)] font-mono">
                  Effective {formatDate(h.effective_date)} · by {h.changed_by_name || "—"}
                  {h.note ? ` · ${h.note}` : ""}
                </div>
              </div>
              <div className="text-right shrink-0 flex items-center gap-2">
                {canEdit && h.id === latestActiveId && !h.superseded_at && (
                  <button type="button" className="btn-ghost text-xs" onClick={() => openForm(h)}>
                    <PencilSimple size={12} /> Correct
                  </button>
                )}
                <div>
                <div className="font-mono font-bold">{fmt(h.net_monthly)}<span className="text-[10px] text-[var(--ink-3)]"> net</span></div>
                {typeof h.delta_net === "number" && (
                  <div className={`text-[11px] font-mono ${h.delta_net >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                    {h.delta_net >= 0 ? "+" : ""}{fmt(h.delta_net)}
                  </div>
                )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PaymentHistoryBlock({ employeeId, canCorrect }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showOld, setShowOld] = useState(false);

  const load = useCallback(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await api.get(`/payroll/runs?employee_id=${employeeId}`);
        if (alive) setRuns(Array.isArray(data) ? data : []);
      } catch {
        if (alive) setRuns([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [employeeId]);
  useEffect(() => load(), [load]);

  const period = salaryPeriod;
  // Months that already have a live payment: their cancelled/replaced rows are history only.
  const paidPeriods = new Set(runs.filter((r) => r.status === "paid").map((r) => `${r.year}-${r.month}`));
  const current = runs.filter((r) => r.status === "paid" || r.status === "processing");
  const old = runs.filter((r) => !current.includes(r));
  const shown = showOld ? runs : current;

  const cancel = async (run) => { if (await cancelSalaryRun(run)) load(); };
  const edit = async (run) => { if (await editSalaryRun(run)) load(); };
  const slipUrl = (run) => `${api.defaults.baseURL}${salarySlipPath(run)}`;

  return (
    <div className="card-flat" data-testid="payment-history-block">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="overline flex items-center gap-1.5"><Receipt size={13} /> SALARY PAYMENT HISTORY</div>
        {old.length > 0 && (
          <label className="text-xs text-[var(--ink-2)] inline-flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} data-testid="show-cancelled-runs" />
            Show cancelled ({old.length})
          </label>
        )}
      </div>
      {loading ? (
        <div className="skeleton h-16 w-full" />
      ) : shown.length === 0 ? (
        <div className="text-xs text-[var(--ink-3)] py-4 text-center border border-dashed border-[var(--line)]" data-testid="payment-history-empty">
          No salary payments recorded yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="payment-history-table">
            <thead>
              <tr className="text-left overline border-b border-[var(--line)]">
                <th className="py-2 pr-3">Period</th>
                <th className="py-2 pr-3 text-right">Net paid</th>
                <th className="py-2 pr-3">Paid on</th>
                <th className="py-2 pr-3">Paid from</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 w-10"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const live = r.status === "paid";
                const canRepay = r.status === "reversed" && !paidPeriods.has(`${r.year}-${r.month}`);
                return (
                  <tr key={r.id} className={`border-b border-[var(--line-soft)] ${live ? "" : "text-[var(--ink-3)]"}`} data-testid={`payment-run-${r.id}`}>
                    <td className="py-2 pr-3">{period(r)}</td>
                    <td className={`py-2 pr-3 text-right tabular-nums font-semibold ${live ? "" : "line-through"}`}>{fmt(r.net)}</td>
                    <td className="py-2 pr-3 text-xs">{formatDate(r.payment_date || r.paid_at)}</td>
                    <td className="py-2 pr-3 text-xs">{r.paid_from_account_name || "—"}{r.reference ? ` · ${r.reference}` : ""}</td>
                    <td className="py-2 pr-3 text-xs">
                      {live ? (r.extras?.bonus ? `Paid · incl. bonus ${fmt(r.extras.bonus)}` : "Paid")
                        : r.status === "corrected" ? "Replaced by edit" : r.status === "reversed" ? "Cancelled" : r.status}
                    </td>
                    <td className="py-2 text-right">
                      <RowActions label={`${period(r)} salary`} testid={`payment-actions-${r.id}`} actions={[
                        { label: "Salary slip (PDF)", icon: FileText, hidden: !live, onSelect: () => window.open(slipUrl(r), "_blank", "noopener") },
                        { label: "Edit payment", icon: PencilSimple, hidden: !canCorrect || !live, onSelect: () => edit(r), testid: `payment-edit-${r.id}` },
                        { label: "Pay again with correct amount", icon: PencilSimple, hidden: !canCorrect || !canRepay, onSelect: () => edit(r), testid: `payment-repay-${r.id}` },
                        { label: "Cancel payment", icon: ClockCounterClockwise, danger: true, divider: true,
                          hidden: !canCorrect || !live, onSelect: () => cancel(r), testid: `payment-cancel-${r.id}` },
                      ]} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
