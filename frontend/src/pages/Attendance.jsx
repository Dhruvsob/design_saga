import { useEffect, useState } from "react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import {
  SignIn, SignOut, Clock, CheckCircle, Warning, Calendar as CalendarIcon,
  Plus, X, PaperPlaneRight,
} from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";

const STATUS_COLORS = {
  present: "#1D633E", absent: "#B4001C", half_day: "#F0A93A",
  leave: "#8A6DFF", holiday: "#3B82F6", week_off: "#5C5C5C",
};

export default function Attendance() {
  const { hasPerm } = useAuth();
  const isHR = hasPerm("employees.read");
  const [tab, setTab] = useState("me");
  const [today, setToday] = useState(null);
  const [summary, setSummary] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [leaves, setLeaves] = useState([]);
  const [meta, setMeta] = useState(null);
  const [ym, setYm] = useState(() => {
    const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() + 1 };
  });
  const [showLeaveForm, setShowLeaveForm] = useState(false);
  const [leaveForm, setLeaveForm] = useState({ leave_type: "casual", from_date: "", to_date: "", reason: "" });
  const [siteVisit, setSiteVisit] = useState(false);
  const [projects, setProjects] = useState([]);
  const [siteForm, setSiteForm] = useState({ project_id: "", site_location: "", reason: "", expected_time: "" });

  const loadMe = async () => {
    const [t, s, l, m, p] = await Promise.all([
      api.get("/attendance/me/today"),
      api.get(`/attendance/me/summary?year=${ym.y}&month=${ym.m}`),
      api.get("/leaves?mine=true"),
      api.get("/attendance/meta"),
      api.get("/projects"),
    ]);
    setToday(t.data); setSummary(s.data); setLeaves(l.data); setMeta(m.data); setProjects(p.data);
  };
  const loadMonthly = async () => {
    const { data } = await api.get(`/attendance/monthly?year=${ym.y}&month=${ym.m}`);
    setMonthly(data);
  };
  useEffect(() => { loadMe(); if (isHR && tab === "monthly") loadMonthly(); }, [ym, tab]);

  const checkIn = async () => {
    const payload = siteVisit
      ? { attendance_type: "site_visit", ...siteForm }
      : { location: "Office" };
    await api.post("/attendance/check-in", payload);
    setSiteVisit(false);
    setSiteForm({ project_id: "", site_location: "", reason: "", expected_time: "" });
    loadMe();
  };
  const checkOut = async () => {
    await api.post("/attendance/check-out", {});
    loadMe();
  };

  const submitLeave = async (e) => {
    e.preventDefault();
    await api.post("/leaves", leaveForm);
    setLeaveForm({ leave_type: "casual", from_date: "", to_date: "", reason: "" });
    setShowLeaveForm(false);
    loadMe();
    if (tab === "leaves-admin") loadPendingLeaves();
  };

  const [pendingLeaves, setPendingLeaves] = useState([]);
  const [pendingSite, setPendingSite] = useState([]);
  const loadPendingLeaves = async () => {
    const { data } = await api.get("/leaves?status=pending");
    setPendingLeaves(data);
  };
  const loadPendingSite = async () => {
    const { data } = await api.get("/attendance/pending-approvals");
    setPendingSite(data);
  };
  useEffect(() => {
    if (isHR && tab === "leaves-admin") loadPendingLeaves();
    if (isHR && tab === "site-approvals") loadPendingSite();
  }, [tab, isHR]);

  const actLeave = async (id, action) => {
    await api.post(`/leaves/${id}/action`, { action });
    loadPendingLeaves();
  };
  const actSite = async (id, action) => {
    await api.post(`/attendance/${id}/approve`, { action });
    loadPendingSite();
  };

  const rec = today?.record;
  const checkedIn = !!rec?.check_in;
  const checkedOut = !!rec?.check_out;

  return (
    <div className="space-y-6" data-testid="attendance-page">
      <PageHero
        eyebrow="HR / ATTENDANCE"
        title="Every hour, on the record."
        kicker="Check in, check out, plan your leaves — feeds straight into payroll."
      />

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[#E5E5E5]">
        <TabBtn id="me" tab={tab} setTab={setTab} label="My Attendance" />
        <TabBtn id="leaves" tab={tab} setTab={setTab} label="My Leaves" />
        {isHR && <TabBtn id="monthly" tab={tab} setTab={setTab} label="Monthly Sheet" />}
        {isHR && <TabBtn id="leaves-admin" tab={tab} setTab={setTab} label="Pending Leaves" />}
        {isHR && <TabBtn id="site-approvals" tab={tab} setTab={setTab} label="Site Approvals" />}
      </div>

      {tab === "me" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card-flat">
              <div className="overline mb-3">TODAY · {new Date().toDateString()}</div>

              {!checkedIn && (
                <div className="mb-3 flex items-center gap-2">
                  <button type="button" onClick={() => setSiteVisit(false)}
                    className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${!siteVisit
                      ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "border-[#E5E5E5] text-[#5C5C5C]"}`}
                    data-testid="type-office">Office</button>
                  <button type="button" onClick={() => setSiteVisit(true)}
                    className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${siteVisit
                      ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "border-[#E5E5E5] text-[#5C5C5C]"}`}
                    data-testid="type-site">Site Visit</button>
                </div>
              )}

              {!checkedIn && siteVisit && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3" data-testid="site-visit-form">
                  <select className="input-flat" value={siteForm.project_id}
                    onChange={(e) => setSiteForm({ ...siteForm, project_id: e.target.value })}>
                    <option value="">Project…</option>
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <input className="input-flat" placeholder="Site location / address" value={siteForm.site_location}
                    onChange={(e) => setSiteForm({ ...siteForm, site_location: e.target.value })} data-testid="site-location" />
                  <input type="time" className="input-flat" placeholder="Expected time" value={siteForm.expected_time}
                    onChange={(e) => setSiteForm({ ...siteForm, expected_time: e.target.value })} />
                  <input className="input-flat" placeholder="Reason / purpose" value={siteForm.reason}
                    onChange={(e) => setSiteForm({ ...siteForm, reason: e.target.value })} data-testid="site-reason" />
                  <div className="md:col-span-2 text-[11px] text-[#F0A93A] font-mono flex items-center gap-1">
                    <Warning size={12} /> Site check-ins require HR / Admin approval before counting as present.
                  </div>
                </div>
              )}

              <div className="flex items-center gap-4">
                {!checkedIn && (
                  <button onClick={checkIn} className="btn-primary" data-testid="check-in-btn">
                    <SignIn size={16} /> Check in {siteVisit ? "at site" : ""}
                  </button>
                )}
                {checkedIn && !checkedOut && (
                  <button onClick={checkOut} className="btn-primary bg-[#1D633E]" data-testid="check-out-btn">
                    <SignOut size={16} /> Check out
                  </button>
                )}
                {checkedOut && (
                  <div className="flex items-center gap-2 text-[#1D633E]"><CheckCircle size={18} weight="fill" /> Day complete</div>
                )}
                {checkedIn && (
                  <div className="text-xs font-mono text-[#5C5C5C]">
                    IN · {rec.check_in?.slice(11, 16)}
                    {checkedOut && <> · OUT · {rec.check_out?.slice(11, 16)} · {rec.worked_hours}h</>}
                    · IP {rec.check_in_ip}
                    {rec.attendance_type === "site_visit" && (
                      <> · <span className="text-[#8A6DFF] font-semibold">SITE</span>
                         {rec.approval_status === "pending" && <span className="text-[#F0A93A]"> · PENDING APPROVAL</span>}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="card-flat">
              <div className="flex items-center justify-between mb-3">
                <div className="overline">MONTH SUMMARY · {ym.y}-{String(ym.m).padStart(2,'0')}</div>
                <MonthPicker ym={ym} setYm={setYm} />
              </div>
              {summary && (
                <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                  {Object.entries(summary.counts).map(([k, v]) => (
                    <div key={k} className="border border-[#E5E5E5] p-3" data-testid={`count-${k}`}>
                      <div className="text-[10px] font-mono uppercase tracking-wider" style={{ color: STATUS_COLORS[k] }}>{k}</div>
                      <div className="font-display font-bold text-2xl">{v}</div>
                    </div>
                  ))}
                </div>
              )}
              {summary?.records?.length > 0 && (
                <div className="mt-4 max-h-64 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
                      <tr><th className="p-1 text-left">Date</th><th className="p-1 text-left">Status</th><th className="p-1">In</th><th className="p-1">Out</th><th className="p-1">Hrs</th></tr>
                    </thead>
                    <tbody>
                      {summary.records.slice().reverse().map((r) => (
                        <tr key={r.id} className="border-t border-[#F0F0F0]">
                          <td className="p-1 font-mono">{r.date}</td>
                          <td className="p-1"><span className="status-chip" style={{ background: `${STATUS_COLORS[r.status]}15`, color: STATUS_COLORS[r.status] }}>{r.status}</span></td>
                          <td className="p-1 text-center font-mono">{r.check_in?.slice(11,16) || "—"}</td>
                          <td className="p-1 text-center font-mono">{r.check_out?.slice(11,16) || "—"}</td>
                          <td className="p-1 text-center font-mono">{r.worked_hours || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          <div className="card-flat">
            <div className="overline mb-3">LEAVE BALANCE (est.)</div>
            {meta && Object.entries(meta.default_allowance).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-[#F0F0F0] py-2 text-sm">
                <span className="capitalize">{k}</span>
                <span className="font-mono">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "leaves" && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowLeaveForm(!showLeaveForm)} className="btn-primary" data-testid="new-leave-btn">
              <Plus size={14} /> {showLeaveForm ? "Cancel" : "Apply leave"}
            </button>
          </div>
          {showLeaveForm && (
            <form onSubmit={submitLeave} className="card-flat grid grid-cols-1 md:grid-cols-4 gap-3" data-testid="leave-form">
              <select className="input-flat" value={leaveForm.leave_type} onChange={(e) => setLeaveForm({ ...leaveForm, leave_type: e.target.value })}>
                {(meta?.leave_types || []).map((t) => <option key={t}>{t}</option>)}
              </select>
              <input type="date" required className="input-flat" value={leaveForm.from_date} onChange={(e) => setLeaveForm({ ...leaveForm, from_date: e.target.value })} data-testid="leave-from" />
              <input type="date" required className="input-flat" value={leaveForm.to_date} onChange={(e) => setLeaveForm({ ...leaveForm, to_date: e.target.value })} data-testid="leave-to" />
              <input className="input-flat" placeholder="Reason" value={leaveForm.reason} onChange={(e) => setLeaveForm({ ...leaveForm, reason: e.target.value })} />
              <button className="btn-primary md:col-span-4" data-testid="leave-submit"><PaperPlaneRight size={14} /> Submit</button>
            </form>
          )}
          <div className="border border-[#E5E5E5] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
                <tr><th className="p-2 text-left">Type</th><th className="p-2 text-left">From</th><th className="p-2 text-left">To</th><th className="p-2 text-left">Days</th><th className="p-2 text-left">Reason</th><th className="p-2 text-left">Status</th></tr>
              </thead>
              <tbody>
                {leaves.map((l) => (
                  <tr key={l.id} className="border-t border-[#F0F0F0]" data-testid={`leave-${l.id}`}>
                    <td className="p-2 capitalize">{l.leave_type}</td>
                    <td className="p-2 font-mono text-xs">{l.from_date}</td>
                    <td className="p-2 font-mono text-xs">{l.to_date}</td>
                    <td className="p-2 font-mono">{l.days}</td>
                    <td className="p-2 text-xs text-[#5C5C5C] truncate max-w-[300px]">{l.reason}</td>
                    <td className="p-2"><LeaveStatus s={l.status} /></td>
                  </tr>
                ))}
                {leaves.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-[#9A9A9A] text-sm">No leaves yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "monthly" && isHR && monthly && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <MonthPicker ym={ym} setYm={setYm} />
            <div className="text-xs font-mono text-[#5C5C5C]">Ready for payroll</div>
          </div>
          <div className="border border-[#E5E5E5] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
                <tr>
                  <th className="p-2 text-left">Employee</th>
                  <th className="p-2 text-left">Designation</th>
                  <th className="p-2">Present</th><th className="p-2">Absent</th>
                  <th className="p-2">Half</th><th className="p-2">Leave</th>
                  <th className="p-2">Week-off</th><th className="p-2">Hours</th>
                </tr>
              </thead>
              <tbody>
                {monthly.rows.map((r) => (
                  <tr key={r.employee.id} className="border-t border-[#F0F0F0]" data-testid={`monthly-${r.employee.id}`}>
                    <td className="p-2 font-semibold">{r.employee.name}</td>
                    <td className="p-2 text-xs text-[#5C5C5C]">{r.employee.designation || "—"}</td>
                    <td className="p-2 text-center font-mono text-[#1D633E]">{r.counts.present}</td>
                    <td className="p-2 text-center font-mono text-[#B4001C]">{r.counts.absent}</td>
                    <td className="p-2 text-center font-mono text-[#F0A93A]">{r.counts.half_day}</td>
                    <td className="p-2 text-center font-mono text-[#8A6DFF]">{r.counts.leave}</td>
                    <td className="p-2 text-center font-mono text-[#5C5C5C]">{r.counts.week_off}</td>
                    <td className="p-2 text-center font-mono">{r.worked_hours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "leaves-admin" && isHR && (
        <div className="space-y-3">
          <div className="overline">PENDING · {pendingLeaves.length} requests</div>
          {pendingLeaves.length === 0 && <div className="text-center text-[#9A9A9A] py-12">Nothing to review.</div>}
          {pendingLeaves.map((l) => (
            <div key={l.id} className="card-flat flex items-center gap-4" data-testid={`pending-${l.id}`}>
              <div className="flex-1">
                <div className="font-semibold">{l.employee_name} · <span className="capitalize text-sm text-[#5C5C5C]">{l.leave_type}</span></div>
                <div className="text-xs font-mono text-[#5C5C5C]">{l.from_date} → {l.to_date} · {l.days} days</div>
                {l.reason && <div className="text-xs text-[#5C5C5C] mt-1">&ldquo;{l.reason}&rdquo;</div>}
              </div>
              <button onClick={() => actLeave(l.id, "approve")} className="btn-primary bg-[#1D633E]" data-testid={`approve-${l.id}`}>
                <CheckCircle size={14} /> Approve
              </button>
              <button onClick={() => actLeave(l.id, "reject")} className="btn-ghost text-[#B4001C]" data-testid={`reject-${l.id}`}>
                <X size={14} /> Reject
              </button>
            </div>
          ))}
        </div>
      )}
      {tab === "site-approvals" && isHR && (
        <div className="space-y-3" data-testid="site-approvals-tab">
          <div className="overline">PENDING SITE VISITS · {pendingSite.length}</div>
          {pendingSite.length === 0 && <div className="text-center text-[#9A9A9A] py-12">All clear.</div>}
          {pendingSite.map((r) => (
            <div key={r.id} className="card-flat flex flex-wrap items-center gap-4" data-testid={`site-req-${r.id}`}>
              <div className="flex-1 min-w-[240px]">
                <div className="font-semibold">{r.employee_name}</div>
                <div className="text-xs font-mono text-[#5C5C5C]">
                  {r.date} · {r.check_in?.slice(11,16)} · IP {r.check_in_ip}
                </div>
                <div className="text-xs text-[#5C5C5C] mt-1">
                  {r.site_location && <>📍 {r.site_location} · </>}
                  {r.site_reason && <>&ldquo;{r.site_reason}&rdquo;</>}
                </div>
              </div>
              <button onClick={() => actSite(r.id, "approve")} className="btn-primary bg-[#1D633E]" data-testid={`site-approve-${r.id}`}>
                <CheckCircle size={14} /> Approve
              </button>
              <button onClick={() => actSite(r.id, "reject")} className="btn-ghost text-[#B4001C]" data-testid={`site-reject-${r.id}`}>
                <X size={14} /> Reject
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TabBtn({ id, tab, setTab, label }) {
  return (
    <button onClick={() => setTab(id)} data-testid={`tab-${id}`}
      className={`px-4 py-2.5 text-sm border-b-2 -mb-px transition ${tab === id
        ? "border-[#002FA7] text-[#002FA7] font-semibold"
        : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"}`}>
      {label}
    </button>
  );
}

function MonthPicker({ ym, setYm }) {
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return (
    <div className="flex items-center gap-2">
      <select className="input-flat" value={ym.m} onChange={(e) => setYm({ ...ym, m: Number(e.target.value) })}>
        {months.map((mn, i) => <option key={mn} value={i+1}>{mn}</option>)}
      </select>
      <input type="number" className="input-flat w-24" value={ym.y} onChange={(e) => setYm({ ...ym, y: Number(e.target.value) })} />
    </div>
  );
}

function LeaveStatus({ s }) {
  const col = { pending: "#F0A93A", approved: "#1D633E", rejected: "#B4001C", cancelled: "#5C5C5C" }[s] || "#5C5C5C";
  return <span className="status-chip" style={{ background: `${col}15`, color: col }}>{s}</span>;
}
