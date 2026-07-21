import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  ArrowLeft, FloppyDisk, Plus, Trash, Warning, Trophy,
  FileText, ArrowSquareOut, ShieldWarning,
} from "@phosphor-icons/react";

const TABS = ["Overview", "Employment", "Salary & Bank", "Documents", "Performance"];
const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
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
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const canEdit = hasPerm("employees.update");
  const canDelete = hasPerm("employees.delete") || user?.role === "Admin";

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
    salary: { ...(p.salary || {}), [k]: Number(v) || 0 },
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
    if (!window.confirm("Delete this employee record permanently?")) return;
    await api.delete(`/employees/${id}`);
    navigate("/employees");
  };

  const addWarning = async () => {
    const reason = window.prompt("Warning reason?");
    if (!reason) return;
    const note = window.prompt("Additional note (optional):") || "";
    await api.post(`/employees/${id}/warnings`, { reason, note });
    load();
  };

  const addReward = async () => {
    const title = window.prompt("Reward title?");
    if (!title) return;
    const note = window.prompt("Description (optional):") || "";
    await api.post(`/employees/${id}/rewards`, { title, note });
    load();
  };

  const addDocument = async () => {
    const label = window.prompt("Document label? (e.g. Aadhaar, Offer letter)");
    if (!label) return;
    const url = window.prompt("Document URL:");
    if (!url) return;
    await api.post(`/employees/${id}/documents`, { label, url });
    load();
  };

  const removeDocument = async (docId) => {
    if (!window.confirm("Remove this document?")) return;
    await api.delete(`/employees/${id}/documents/${docId}`);
    load();
  };

  if (!emp) {
    return (
      <div className="space-y-4" data-testid="emp-detail-loading">
        <div className="skeleton h-8 w-48" />
        <div className="skeleton h-32 w-full" />
        {err && <p className="text-sm text-[#FF2A00]">{err}</p>}
      </div>
    );
  }

  const perf = emp.performance || { warnings: [], rewards: [], current_kpi_score: 0 };
  const s = emp.salary || {};

  return (
    <div className="space-y-8 pb-16" data-testid="emp-detail">
      <Link to="/employees" className="inline-flex items-center gap-1 text-sm text-[#5C5C5C] hover:text-[#0A0A0A]">
        <ArrowLeft size={14} /> All employees
      </Link>

      {/* Header */}
      <div className="border border-[#E5E5E5] p-6 flex flex-wrap gap-6 items-start justify-between bg-white">
        <div className="flex items-start gap-5 flex-1 min-w-[280px]">
          {emp.photo ? (
            <img src={emp.photo} alt="" className="w-20 h-20 object-cover ring-1 ring-[#E5E5E5]" />
          ) : (
            <div className="w-20 h-20 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-3xl">
              {(emp.first_name || "?").slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <div className="overline mb-2 flex items-center gap-3 flex-wrap">
              {emp.employee_id}
              <span className={`status-chip ${STATUS_CHIP[emp.employment_status] || "chip-draft"}`}>{emp.employment_status}</span>
              <span className="status-chip chip-medium no-dot">{emp.employment_type?.replace("_", " ")}</span>
            </div>
            <h1 className="font-display font-bold tracking-tighter text-3xl">
              {emp.first_name} {emp.last_name}
            </h1>
            <div className="mt-2 text-sm text-[#5C5C5C]">
              {emp.designation || "—"} · {emp.department}
              {emp.joining_date && <> · joined {emp.joining_date}</>}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="overline">NET / MONTH</div>
          <div className="font-display font-bold text-3xl tracking-tighter accent-blue">{fmt(s.net_monthly)}</div>
          <div className="overline mt-1">CTC {fmt(s.ctc_annual)}</div>
        </div>
      </div>

      {err && (
        <div className="border border-[#FF2A00] bg-[#FFF5F3] p-3 text-sm text-[#FF2A00] flex items-center gap-2">
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
          {canDelete && (
            <button onClick={remove} className="btn-ghost ml-auto" style={{ color: "#FF2A00", borderColor: "#FF2A00" }}>
              <Trash size={14} /> Delete
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-[#E5E5E5]">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            data-testid={`emp-tab-${t.replace(/[\s&]/g, "-")}`}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition ${
              tab === t ? "border-[#002FA7] text-[#002FA7]" : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"
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
            <div className="grid grid-cols-2 gap-3">
              <Row label="Date of birth">
                <input disabled={!canEdit} type="date" className="input-flat" value={emp.dob || ""} onChange={(e) => patch(() => ({ dob: e.target.value }))} />
              </Row>
              <Row label="Gender">
                <select disabled={!canEdit} className="input-flat" value={emp.gender || ""} onChange={(e) => patch(() => ({ gender: e.target.value }))}>
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
                <input disabled={!canEdit} className="input-flat" value={emp.blood_group || ""} onChange={(e) => patch(() => ({ blood_group: e.target.value }))} />
              </Row>
              <Row label="Aadhaar">
                <input disabled={!canEdit} className="input-flat" value={emp.aadhaar || ""} onChange={(e) => patch(() => ({ aadhaar: e.target.value }))} />
              </Row>
            </div>
            <Row label="PAN">
              <input disabled={!canEdit} className="input-flat" value={emp.pan || ""} onChange={(e) => patch(() => ({ pan: e.target.value }))} />
            </Row>
          </Card>

          <Card title="ADDRESS & EMERGENCY">
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
            <div className="border-t border-[#F0F0F0] pt-4 mt-2">
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
          </Card>
        </div>
      )}

      {tab === "Employment" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="emp-tab-employment">
          <Card title="ROLE & TEAM">
            <Row label="Department">
              <select disabled={!canEdit} className="input-flat" value={emp.department || ""} onChange={(e) => patch(() => ({ department: e.target.value }))}>
                {meta.departments.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </Row>
            <Row label="Designation">
              <input disabled={!canEdit} className="input-flat" value={emp.designation || ""} onChange={(e) => patch(() => ({ designation: e.target.value }))} />
            </Row>
            <Row label="Employment type">
              <select disabled={!canEdit} className="input-flat" value={emp.employment_type || ""} onChange={(e) => patch(() => ({ employment_type: e.target.value }))}>
                {meta.employment_types.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
              </select>
            </Row>
            <Row label="Status">
              <select disabled={!canEdit} className="input-flat" value={emp.employment_status || ""} onChange={(e) => patch(() => ({ employment_status: e.target.value }))}>
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
                <input disabled={!canEdit} type="number" className="input-flat" value={emp.notice_period_days || 0} onChange={(e) => patch(() => ({ notice_period_days: Number(e.target.value) || 0 }))} />
              </Row>
              <Row label="Weekly hours">
                <input disabled={!canEdit} type="number" className="input-flat" value={emp.weekly_hours || 0} onChange={(e) => patch(() => ({ weekly_hours: Number(e.target.value) || 0 }))} />
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

      {tab === "Salary & Bank" && (
        <div className="space-y-6" data-testid="emp-tab-salary">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card title="EARNINGS (MONTHLY)" testid="salary-earnings">
            {["basic", "hra", "conveyance", "medical", "other_allowances"].map((k) => (
              <Row key={k} label={k.replace("_", " ").toUpperCase()}>
                <input disabled={!canEdit} type="number" className="input-flat text-right font-mono" value={s[k] || 0} onChange={(e) => patchSalary(k, e.target.value)} />
              </Row>
            ))}
            <div className="border-t border-[#0A0A0A] mt-2 pt-3 flex items-center justify-between">
              <div className="font-display font-bold">Gross</div>
              <div className="font-mono font-bold">{fmt(s.gross_monthly)}</div>
            </div>
          </Card>

          <Card title="DEDUCTIONS (MONTHLY)" testid="salary-deductions">
            {["pf_employee", "esi_employee", "professional_tax", "tds"].map((k) => (
              <Row key={k} label={k.replace("_", " ").toUpperCase()}>
                <input disabled={!canEdit} type="number" className="input-flat text-right font-mono" value={s[k] || 0} onChange={(e) => patchSalary(k, e.target.value)} />
              </Row>
            ))}
            <div className="border-t border-[#0A0A0A] mt-2 pt-3 flex items-center justify-between">
              <div className="font-display font-bold">Total deductions</div>
              <div className="font-mono font-bold">{fmt(s.total_deductions)}</div>
            </div>
            <div className="mt-3 border border-[#0A0A0A] p-4 bg-[#FAFAFA]">
              <div className="overline mb-1">NET / MONTH</div>
              <div className="font-display font-bold text-3xl tracking-tighter accent-blue">{fmt(s.net_monthly)}</div>
              <div className="text-xs text-[#5C5C5C] mt-1">CTC · {fmt(s.ctc_annual)} / year</div>
            </div>
          </Card>

          <Card title="BANK DETAILS" testid="salary-bank">
            <Row label="Account holder">
              <input disabled={!canEdit} className="input-flat" value={emp.bank?.account_holder || ""} onChange={(e) => patchBank("account_holder", e.target.value)} />
            </Row>
            <Row label="Account number">
              <input disabled={!canEdit} className="input-flat font-mono" value={emp.bank?.account_number || ""} onChange={(e) => patchBank("account_number", e.target.value)} />
            </Row>
            <Row label="IFSC">
              <input disabled={!canEdit} className="input-flat font-mono" value={emp.bank?.ifsc || ""} onChange={(e) => patchBank("ifsc", e.target.value)} />
            </Row>
            <Row label="Bank name">
              <input disabled={!canEdit} className="input-flat" value={emp.bank?.bank_name || ""} onChange={(e) => patchBank("bank_name", e.target.value)} />
            </Row>
            <Row label="UPI">
              <input disabled={!canEdit} className="input-flat font-mono" value={emp.bank?.upi || ""} onChange={(e) => patchBank("upi", e.target.value)} />
            </Row>
          </Card>
          </div>

          {hasPerm("payroll.create") && (
            <PaySalaryBlock employeeId={emp.id} netMonthly={s.net_monthly} />
          )}
        </div>
      )}

      {tab === "Documents" && (
        <Card title={`DOCUMENTS · ${(emp.documents || []).length}`}
              actions={canEdit && <button onClick={addDocument} className="btn-ghost text-xs"><Plus size={12} /> Add</button>}
              testid="emp-tab-documents">
          {(emp.documents || []).length === 0 ? (
            <p className="text-sm text-[#5C5C5C]">No documents yet. Add offer letter, Aadhaar, PAN, contract etc.</p>
          ) : (
            <div className="space-y-2">
              {(emp.documents || []).map((d) => (
                <div key={d.id} className="border border-[#E5E5E5] p-3 flex items-center justify-between hover:border-[#0A0A0A] transition">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm">{d.label}</div>
                    <div className="text-xs text-[#5C5C5C] font-mono truncate">{d.url}</div>
                    <div className="text-[10px] text-[#9A9A9A] font-mono tracking-widest uppercase mt-1">
                      UPLOADED {(d.uploaded_at || "").slice(0, 10)} · {d.uploaded_by || "—"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <a href={d.url} target="_blank" rel="noreferrer" className="btn-ghost text-xs">
                      <ArrowSquareOut size={12} /> Open
                    </a>
                    {canEdit && (
                      <button onClick={() => removeDocument(d.id)} className="text-[#FF2A00] hover:scale-110 transition p-2">
                        <Trash size={14} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
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
                <input type="number" min={0} max={100} className="input-flat" value={perf.current_kpi_score || 0} onChange={(e) => patch(() => ({ current_kpi_score: Number(e.target.value) || 0 }))} />
              </Row>
            )}
            <div className="mt-3 h-2 bg-[#F0F0F0] relative">
              <div className="h-2 bg-[#002FA7]" style={{ width: `${Math.min(100, Math.max(0, perf.current_kpi_score || 0))}%` }} />
            </div>
          </Card>

          <Card title={`WARNINGS · ${(perf.warnings || []).length}`}
                actions={canEdit && <button onClick={addWarning} className="btn-ghost text-xs"><Plus size={12} /> Log</button>}>
            {(perf.warnings || []).length === 0 ? (
              <p className="text-sm text-[#5C5C5C]">No warnings recorded.</p>
            ) : (
              <div className="space-y-2">
                {[...(perf.warnings || [])].reverse().map((w) => (
                  <div key={w.id} className="border-l-2 border-[#FF2A00] pl-3 py-1">
                    <div className="font-semibold text-sm">{w.reason}</div>
                    {w.note && <p className="text-xs text-[#5C5C5C] mt-1">{w.note}</p>}
                    <div className="text-[10px] font-mono tracking-widest uppercase text-[#9A9A9A] mt-1">
                      {(w.at || "").slice(0, 10)} · {w.by || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title={`REWARDS · ${(perf.rewards || []).length}`}
                actions={canEdit && <button onClick={addReward} className="btn-ghost text-xs"><Plus size={12} /> Log</button>}>
            {(perf.rewards || []).length === 0 ? (
              <p className="text-sm text-[#5C5C5C]">No rewards yet.</p>
            ) : (
              <div className="space-y-2">
                {[...(perf.rewards || [])].reverse().map((r) => (
                  <div key={r.id} className="border-l-2 border-[#1D633E] pl-3 py-1">
                    <div className="font-semibold text-sm">{r.title}</div>
                    {r.note && <p className="text-xs text-[#5C5C5C] mt-1">{r.note}</p>}
                    <div className="text-[10px] font-mono tracking-widest uppercase text-[#9A9A9A] mt-1">
                      {(r.at || "").slice(0, 10)} · {r.by || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
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

function PaySalaryBlock({ employeeId, netMonthly }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [preview, setPreview] = useState(null);
  const [banks, setBanks] = useState([]);
  const [bankAccountId, setBankAccountId] = useState("");
  const [extras, setExtras] = useState({ bonus: 0, incentives: 0, overtime: 0, advances_recovered: 0, other_deductions: 0 });
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setMsg("");
    try {
      const qs = new URLSearchParams({ year, month, ...extras }).toString();
      const [{ data: p }, { data: accs }] = await Promise.all([
        api.get(`/employees/${employeeId}/salary/preview?${qs}`),
        api.get("/accounts?type=asset"),
      ]);
      setPreview(p);
      const cash = (accs || []).filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name));
      setBanks(cash);
      if (!bankAccountId && cash.length) setBankAccountId(cash[0].id);
    } catch (e) {
      setMsg(e?.response?.data?.detail || "Failed to load preview (need finance.read)");
    }
  }, [employeeId, year, month, extras]);

  useEffect(() => { load(); }, [load]);

  const pay = async () => {
    setBusy(true); setMsg("");
    try {
      const { data } = await api.post(`/employees/${employeeId}/pay-salary`, {
        year, month, paid_from_account_id: bankAccountId,
        ...extras, notes,
      });
      setMsg(`✓ Paid ₹${data.run.net.toLocaleString("en-IN")} · JE ${data.journal.id}`);
      load();
    } catch (e) {
      setMsg(e?.response?.data?.detail || "Payment failed");
    } finally { setBusy(false); }
  };

  const b = preview?.breakdown;
  const paid = preview?.already_paid;

  return (
    <div className="card-flat" data-testid="pay-salary-block">
      <div className="overline mb-4">RUN PAYROLL · posts to Accounting automatically</div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4">
        <label className="text-xs">
          <div className="overline mb-1">Year</div>
          <input type="number" className="input-flat w-full" value={year} onChange={(e) => setYear(Number(e.target.value))} />
        </label>
        <label className="text-xs">
          <div className="overline mb-1">Month</div>
          <select className="input-flat w-full" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].map((m, i) => <option key={m} value={i+1}>{m}</option>)}
          </select>
        </label>
        {["bonus","incentives","overtime","advances_recovered","other_deductions"].map((k) => (
          <label key={k} className="text-xs">
            <div className="overline mb-1">{k.replace(/_/g, " ")}</div>
            <input type="number" className="input-flat w-full text-right font-mono" value={extras[k]} onChange={(e) => setExtras({ ...extras, [k]: Number(e.target.value) || 0 })} data-testid={`extra-${k}`} />
          </label>
        ))}
      </div>

      {b && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-sm">
          <StatBox label="Gross" value={fmt(b.gross)} />
          <StatBox label="Deductions" value={fmt(b.deductions_total)} tint="#B4001C" />
          <StatBox label="Additions" value={fmt(b.additions)} tint="#1D633E" />
          <StatBox label="Net payable" value={fmt(b.net)} tint="#002FA7" big />
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs flex-1 min-w-[220px]">
          <div className="overline mb-1">Pay from</div>
          <select className="input-flat w-full" value={bankAccountId} onChange={(e) => setBankAccountId(e.target.value)} data-testid="pay-from">
            {banks.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label className="text-xs flex-1 min-w-[220px]">
          <div className="overline mb-1">Notes</div>
          <input className="input-flat w-full" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button
          onClick={pay}
          disabled={busy || !bankAccountId || !b || !!paid}
          className="btn-primary disabled:opacity-40"
          data-testid="pay-salary-btn">
          {paid ? "Already paid" : busy ? "Processing…" : `Pay ${fmt(b?.net || netMonthly)}`}
        </button>
      </div>
      {msg && <div className="mt-3 text-sm text-[#002FA7]" data-testid="pay-msg">{msg}</div>}
      {paid && (
        <div className="mt-2 text-xs text-[#5C5C5C] font-mono" data-testid="paid-badge">
          PAID ON {paid.paid_at?.slice(0, 10)} · NET {fmt(paid.net)} · Run {paid.id}
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, tint = "#0A0A0A", big }) {
  return (
    <div className="border border-[#E5E5E5] p-3">
      <div className="overline">{label}</div>
      <div className={`font-mono font-bold ${big ? "text-2xl" : "text-lg"}`} style={{ color: tint }}>{value}</div>
    </div>
  );
}

