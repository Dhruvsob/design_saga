import { useEffect, useMemo, useState, useCallback } from "react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import GeoFenceMap from "../components/GeoFenceMap";
import {
  SignIn, SignOut, CheckCircle, Warning, Plus, X, PaperPlaneRight,
  Users, Broadcast, CurrencyInr, ClipboardText, Gear, MapPin,
  DownloadSimple, Clock, ArrowsClockwise,
} from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";

const STATUS_COLORS = {
  present: "#1D633E", late: "#B87500", absent: "#B4001C", half_day: "#F0A93A",
  leave: "#8A6DFF", paid_leave: "#8A6DFF", unpaid_leave: "#B4001C",
  holiday: "#3B82F6", week_off: "#5C5C5C", pending_approval: "#F0A93A",
  upcoming: "#C9C9C9", site_visit: "#0E7490",
};
const WEEKDAYS = [
  { v: 0, l: "Mon" }, { v: 1, l: "Tue" }, { v: 2, l: "Wed" }, { v: 3, l: "Thu" },
  { v: 4, l: "Fri" }, { v: 5, l: "Sat" }, { v: 6, l: "Sun" },
];
const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const capWords = (s) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
// Render a stored UTC ISO timestamp as HH:MM in IST
const fmtT = (iso) => {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata",
    });
  } catch { return iso.slice(11, 16); }
};

async function downloadPayslip(employeeId, y, m) {
  const res = await api.get(
    `/payroll/payslip.pdf?employee_id=${employeeId}&year=${y}&month=${m}`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `payslip_${employeeId}_${y}_${String(m).padStart(2, "0")}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Attendance() {
  const { hasPerm } = useAuth();
  const isHR = hasPerm("employees.read");
  const isHRWrite = hasPerm("employees.update");
  const isAdmin = hasPerm("*.*");
  const [tab, setTab] = useState("me");
  const [today, setToday] = useState(null);
  const [summary, setSummary] = useState(null);
  const [mySalary, setMySalary] = useState(null);
  const [monthly, setMonthly] = useState(null);
  const [leaves, setLeaves] = useState([]);
  const [myCorrections, setMyCorrections] = useState([]);
  const [meta, setMeta] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [ym, setYm] = useState(() => {
    const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() + 1 };
  });
  const [showLeaveForm, setShowLeaveForm] = useState(false);
  const [leaveForm, setLeaveForm] = useState({ leave_type: "casual", from_date: "", to_date: "", reason: "" });
  const [showCorrForm, setShowCorrForm] = useState(false);
  const [corrForm, setCorrForm] = useState({ date: "", in_time: "", out_time: "", reason: "" });
  const [siteVisit, setSiteVisit] = useState(false);
  const [projects, setProjects] = useState([]);
  const [siteForm, setSiteForm] = useState({ project_id: "", site_location: "", reason: "", expected_time: "" });

  const loadMe = async () => {
    const [t, s, l, m, p, pol, sal, corr] = await Promise.all([
      api.get("/attendance/me/today"),
      api.get(`/attendance/me/summary?year=${ym.y}&month=${ym.m}`),
      api.get("/leaves?mine=true"),
      api.get("/attendance/meta"),
      api.get("/projects"),
      api.get("/attendance/policy").catch(() => ({ data: null })),
      api.get(`/attendance/my-salary?year=${ym.y}&month=${ym.m}`).catch(() => ({ data: null })),
      api.get("/attendance/corrections?mine=true").catch(() => ({ data: [] })),
    ]);
    setToday(t.data); setSummary(s.data); setLeaves(l.data); setMeta(m.data);
    setProjects(p.data); setPolicy(pol.data); setMySalary(sal.data);
    setMyCorrections(corr.data || []);
  };
  const loadMonthly = async () => {
    const { data } = await api.get(`/attendance/monthly?year=${ym.y}&month=${ym.m}`);
    setMonthly(data);
  };
  useEffect(() => { loadMe(); if (isHR && tab === "monthly") loadMonthly(); }, [ym, tab]);

  const [attType, setAttType] = useState("office");
  const [checkInBusy, setCheckInBusy] = useState(false);
  const [outsideBlock, setOutsideBlock] = useState(null);
  const [accuracyBlock, setAccuracyBlock] = useState(null);
  const [lateReasonNeeded, setLateReasonNeeded] = useState(null);
  const [lateReason, setLateReason] = useState("");
  const [lateCategory, setLateCategory] = useState("");

  const deviceId = useMemo(() => {
    let id = localStorage.getItem("ds_device_id");
    if (!id) {
      id = "dev_" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
      localStorage.setItem("ds_device_id", id);
    }
    return id;
  }, []);
  const deviceLabel = useMemo(() => {
    const ua = navigator.userAgent || "";
    const platform = navigator.platform || "";
    const browser = /Edg/.test(ua) ? "Edge"
      : /Chrome/.test(ua) ? "Chrome"
      : /Firefox/.test(ua) ? "Firefox"
      : /Safari/.test(ua) ? "Safari" : "Browser";
    return `${browser} / ${platform || "Unknown"}`;
  }, []);

  const _getGPS = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("Geolocation not supported by this browser."));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy_m: p.coords.accuracy }),
      (err) => reject(new Error(err.message || "Unable to fetch GPS location. Please allow location permission.")),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 },
    );
  });

  const doCheckIn = async (opts = {}) => {
    setCheckInBusy(true);
    if (!opts.force && !opts.retryLate) setOutsideBlock(null);
    setAccuracyBlock(null);
    try {
      let gps = {};
      try { gps = await _getGPS(); }
      catch (ge) {
        setCheckInBusy(false);
        alert(ge.message || "GPS required for check-in");
        return;
      }
      const base = {
        attendance_type: attType, ...gps,
        force_outside: !!opts.force,
        device_id: deviceId, device_label: deviceLabel,
        user_agent: navigator.userAgent,
      };
      if (opts.lateReason) base.late_reason = opts.lateReason;
      if (opts.lateCategory) base.late_category = opts.lateCategory;
      const extra = attType === "office"
        ? { location: "Office" }
        : { ...siteForm };
      await api.post("/attendance/check-in", { ...base, ...extra });
      setSiteVisit(false);
      setSiteForm({ project_id: "", site_location: "", reason: "", expected_time: "" });
      setLateReasonNeeded(null); setLateReason(""); setLateCategory("");
      loadMe();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "outside_geofence") {
        setOutsideBlock(detail);
      } else if (detail && typeof detail === "object" && detail.code === "gps_accuracy_low") {
        setAccuracyBlock(detail);
      } else if (detail && typeof detail === "object" && detail.code === "late_reason_required") {
        setLateReasonNeeded(detail);
      } else {
        const msg = typeof detail === "string" ? detail : (detail?.message || "Check-in failed");
        alert(msg);
      }
    } finally { setCheckInBusy(false); }
  };

  const checkIn = () => doCheckIn();
  const requestApproval = () => doCheckIn({ force: true });
  const submitLateReason = () => {
    if (!lateReason.trim() && !lateCategory) { alert("Please pick a category or share a brief reason"); return; }
    doCheckIn({ lateReason: lateReason.trim(), lateCategory, retryLate: true });
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
  };
  const submitCorrection = async (e) => {
    e.preventDefault();
    if (!corrForm.date || !corrForm.reason.trim()) { alert("Date and reason are required"); return; }
    const payload = { date: corrForm.date, reason: corrForm.reason };
    if (corrForm.in_time) payload.requested_check_in = `${corrForm.date}T${corrForm.in_time}:00+05:30`;
    if (corrForm.out_time) payload.requested_check_out = `${corrForm.date}T${corrForm.out_time}:00+05:30`;
    await api.post("/attendance/corrections", payload);
    setCorrForm({ date: "", in_time: "", out_time: "", reason: "" });
    setShowCorrForm(false);
    loadMe();
  };

  const rec = today?.record;
  const checkedIn = !!rec?.check_in;
  const checkedOut = !!rec?.check_out;

  // Live late detection vs policy shift (shown before check-in) — Jewellers UX
  const lateInfo = useMemo(() => {
    if (!policy?.office_start || checkedIn) return null;
    const [hh, mm] = String(policy.office_start).split(":").map(Number);
    if (Number.isNaN(hh)) return null;
    const n = new Date();
    const lateMinutes = (n.getHours() * 60 + n.getMinutes()) - (hh * 60 + (mm || 0));
    if (lateMinutes <= 0) return null;
    const grace = Number(policy.grace_minutes ?? 0);
    return { lateMinutes, grace, fineApplies: lateMinutes > grace && !!policy.late_fine_enabled };
  }, [policy, checkedIn]);

  return (
    <div className="space-y-6" data-testid="attendance-page">
      <PageHero
        eyebrow="HR / ATTENDANCE & PAYROLL"
        title="Every hour, on the record."
        kicker="Geo-fenced check-ins, leaves, salary impact — feeds straight into payroll."
      />

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[#E5E5E5] overflow-x-auto">
        <TabBtn id="me" tab={tab} setTab={setTab} label="My Attendance" />
        <TabBtn id="leaves" tab={tab} setTab={setTab} label="My Leaves" />
        {isHR && <TabBtn id="dashboard" tab={tab} setTab={setTab} label="Team Dashboard" />}
        {isHR && <TabBtn id="live" tab={tab} setTab={setTab} label="Live Board" />}
        {isHR && <TabBtn id="monthly" tab={tab} setTab={setTab} label="Monthly Sheet" />}
        {isHR && <TabBtn id="payroll" tab={tab} setTab={setTab} label="Payroll" />}
        {isHR && <TabBtn id="requests" tab={tab} setTab={setTab} label="Requests" />}
        {isHRWrite && <TabBtn id="setup" tab={tab} setTab={setTab} label="Shift & Salary Setup" />}
        {isAdmin && <TabBtn id="geo" tab={tab} setTab={setTab} label="Geo & Policy" />}
      </div>

      {tab === "me" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="card-flat">
              <div className="overline mb-3">TODAY · {new Date().toDateString()}</div>

              {!checkedIn && (
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  {[
                    ["office", "Office"],
                    ["site_visit", "Site Visit"],
                    ["client_meeting", "Client Meeting"],
                    ["warehouse", "Warehouse"],
                    ["vendor_visit", "Vendor Visit"],
                  ].map(([k, l]) => (
                    <button key={k} type="button" onClick={() => { setAttType(k); setSiteVisit(k !== "office"); }}
                      className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${attType === k
                        ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "border-[#E5E5E5] text-[#5C5C5C]"}`}
                      data-testid={`type-${k}`}>{l}</button>
                  ))}
                </div>
              )}

              {!checkedIn && lateInfo && attType === "office" && (
                <div className={`border p-3 mb-3 ${lateInfo.fineApplies ? "border-[#B87500] bg-[#FFF6E5]" : "border-[#3B82F6] bg-[#F5F4F0]"}`}
                  data-testid="late-banner">
                  <div className={`flex items-center gap-2 font-semibold text-sm ${lateInfo.fineApplies ? "text-[#B87500]" : "text-[#76705E]"}`}
                    data-testid="late-banner-text">
                    <Warning size={14} /> You are {lateInfo.lateMinutes} minute{lateInfo.lateMinutes === 1 ? "" : "s"} late.
                  </div>
                  {lateInfo.fineApplies ? (
                    <div className="text-xs text-[#8a5a00] mt-1">
                      Late fine of <b>{inr(policy.late_fine_amount)}</b> per occurrence may apply
                      (grace {lateInfo.grace} min · cap <b>{inr(policy.late_fine_daily_cap)}/day</b>).
                      Late is never auto half-day — your manager can approve to waive the fine.
                    </div>
                  ) : (
                    <div className="text-xs text-[#76705E] mt-1">
                      {lateInfo.lateMinutes <= lateInfo.grace
                        ? `Within the ${lateInfo.grace}-minute grace period — no penalty.`
                        : "The late fine system is off — a reason may still be required."}
                    </div>
                  )}
                </div>
              )}

              {!checkedIn && siteVisit && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3" data-testid="site-visit-form">
                  <select className="input-flat" value={siteForm.project_id}
                    onChange={(e) => setSiteForm({ ...siteForm, project_id: e.target.value })}>
                    <option value="">Project (optional)…</option>
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <input className="input-flat" placeholder="Location / address" value={siteForm.site_location}
                    onChange={(e) => setSiteForm({ ...siteForm, site_location: e.target.value })} data-testid="site-location" />
                  <input type="time" className="input-flat" placeholder="Expected time" value={siteForm.expected_time}
                    onChange={(e) => setSiteForm({ ...siteForm, expected_time: e.target.value })} />
                  <input className="input-flat" placeholder="Reason / purpose" value={siteForm.reason}
                    onChange={(e) => setSiteForm({ ...siteForm, reason: e.target.value })} data-testid="site-reason" />
                  <div className="md:col-span-2 text-[11px] text-[#F0A93A] font-mono flex items-center gap-1">
                    <Warning size={12} /> Non-office check-ins require HR / Admin approval before counting as present.
                  </div>
                </div>
              )}

              {outsideBlock && (
                <div className="border border-[#B22B22] bg-[#FCEEEC] p-3 mb-3" data-testid="outside-fence-banner">
                  <div className="flex items-center gap-2 text-[#B22B22] font-semibold mb-1">
                    <Warning size={14}/> You are outside the authorized location.
                  </div>
                  <div className="text-xs text-[#B22B22] mb-2">{outsideBlock.message}</div>
                  <div className="flex flex-wrap gap-2">
                    <button onClick={requestApproval} className="btn-primary text-xs bg-[#B87500]" data-testid="request-approval-btn">
                      Request Approval
                    </button>
                    <button onClick={checkIn} className="btn-ghost text-xs" data-testid="retry-checkin-btn">Retry</button>
                    <button onClick={() => window.open("mailto:admin@" + (window.location.hostname||""))} className="btn-ghost text-xs">
                      Contact Admin
                    </button>
                  </div>
                </div>
              )}

              {accuracyBlock && (
                <div className="border border-[#B87500] bg-[#FFF6E5] p-3 mb-3" data-testid="accuracy-block">
                  <div className="flex items-center gap-2 text-[#B87500] font-semibold mb-1">
                    <Warning size={14}/> GPS accuracy too low
                  </div>
                  <div className="text-xs text-[#5C5C5C] mb-2">{accuracyBlock.message}</div>
                  <button onClick={checkIn} className="btn-ghost text-xs" data-testid="accuracy-retry-btn">
                    Retry with better GPS
                  </button>
                </div>
              )}

              {lateReasonNeeded && (
                <div className="border border-[#B87500] bg-[#FFF6E5] p-3 mb-3" data-testid="late-reason-block">
                  <div className="flex items-center gap-2 text-[#B87500] font-semibold mb-1">
                    <Warning size={14}/> Late arrival — pick a category / share a reason
                  </div>
                  <div className="text-xs text-[#5C5C5C] mb-2">{lateReasonNeeded.message}</div>
                  <div className="flex flex-col sm:flex-row gap-2 mb-2">
                    <select className="input-flat sm:w-56" value={lateCategory}
                      onChange={(e) => setLateCategory(e.target.value)} data-testid="late-category-select">
                      <option value="">Category…</option>
                      {((lateReasonNeeded.categories?.length ? lateReasonNeeded.categories : policy?.late_reason_categories) || [])
                        .map((c) => <option key={c} value={c}>{capWords(c)}</option>)}
                    </select>
                    <input
                      className="input-flat flex-1 text-sm"
                      placeholder="Brief note — traffic, personal work, medical…"
                      value={lateReason}
                      onChange={(e) => setLateReason(e.target.value)}
                      data-testid="late-reason-input"
                    />
                  </div>
                  <button
                    onClick={submitLateReason}
                    disabled={checkInBusy}
                    className="btn-primary text-xs"
                    data-testid="late-reason-submit-btn"
                  >
                    Submit & Check In
                  </button>
                </div>
              )}

              <div className="flex items-center gap-4">
                {!checkedIn && (
                  <button onClick={checkIn} disabled={checkInBusy} className="btn-primary" data-testid="check-in-btn">
                    <SignIn size={16} /> {checkInBusy ? "Checking GPS…" : `Check in${attType !== "office" ? ` – ${attType.replace("_"," ")}` : ""}`}
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
                    IN · {fmtT(rec.check_in)}
                    {checkedOut && <> · OUT · {fmtT(rec.check_out)} · {rec.worked_hours}h</>}
                    {rec.status === "late" && (
                      <> · <span className="text-[#B87500] font-semibold">LATE {rec.late_minutes}m</span>
                        {rec.late_approval_status === "pending" && <span className="text-[#F0A93A]"> · APPROVAL PENDING</span>}
                        {rec.late_approval_status === "approved" && <span className="text-[#1D633E]"> · APPROVED (FINE WAIVED)</span>}
                        {rec.late_approval_status === "rejected" && <span className="text-[#B4001C]"> · REJECTED (FINE {inr(rec.late_fine_amount)})</span>}
                      </>
                    )}
                    {rec.attendance_type !== "office" && (
                      <> · <span className="text-[#8A6DFF] font-semibold uppercase">{rec.attendance_type?.replace("_"," ")}</span>
                         {rec.approval_status === "pending" && <span className="text-[#F0A93A]"> · PENDING APPROVAL</span>}
                      </>
                    )}
                    {rec.geo_location_matched && (
                      <> · 📍 {rec.geo_location_matched}{rec.geo_distance_m ? ` (${rec.geo_distance_m}m)` : ""}</>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Daily calendar grid (Jewellers UX) */}
            {mySalary?.has_employee && mySalary.daily && (
              <div className="card-flat" data-testid="daily-grid-card">
                <div className="flex items-center justify-between mb-3">
                  <div className="overline">DAILY GRID · {mySalary.month_label?.toUpperCase()}</div>
                  <div className="flex flex-wrap gap-3 text-[11px] font-mono text-[#5C5C5C]">
                    <span>P <b className="text-[#1D633E]">{mySalary.summary.present}</b></span>
                    <span>L <b className="text-[#B87500]">{mySalary.summary.late}</b></span>
                    <span>H <b className="text-[#F0A93A]">{mySalary.summary.half_day}</b></span>
                    <span>A <b className="text-[#B4001C]">{mySalary.summary.absent}</b></span>
                    <span>PAYABLE <b>{mySalary.payable_days}</b></span>
                  </div>
                </div>
                <div className="grid grid-cols-7 gap-1.5">
                  {mySalary.daily.map((d) => (
                    <div key={d.date} className="border border-[#F0F0F0] p-1.5 text-center"
                      style={{ background: `${STATUS_COLORS[d.status] || "#EEE"}12` }}
                      title={`${d.date} · ${d.status}${d.check_in ? ` · in ${d.check_in}` : ""}${d.check_out ? ` · out ${d.check_out}` : ""}`}>
                      <div className="text-[10px] font-mono">{Number(d.date.slice(8, 10))}</div>
                      <div className="text-[9px] capitalize truncate" style={{ color: STATUS_COLORS[d.status] || "#9A9A9A" }}>
                        {d.status.replace(/_/g, " ")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

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
                          <td className="p-1 text-center font-mono">{fmtT(r.check_in) || "—"}</td>
                          <td className="p-1 text-center font-mono">{fmtT(r.check_out) || "—"}</td>
                          <td className="p-1 text-center font-mono">{r.worked_hours || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            {/* Salary impact (Jewellers "My Salary") */}
            <div className="card-flat" data-testid="my-salary-card">
              <div className="overline mb-3">MY SALARY · {mySalary?.month_label?.toUpperCase() || ""}</div>
              {!mySalary?.has_employee ? (
                <div className="text-sm text-[#9A9A9A]">
                  Your login isn't linked to an employee record yet — ask your admin
                  to link it to see your live salary impact.
                </div>
              ) : (
                <>
                  <div className="font-display font-bold text-3xl mb-1" data-testid="my-net-payable">
                    {inr(mySalary.net_payable)}
                  </div>
                  <div className="text-[11px] font-mono text-[#5C5C5C] mb-3">
                    Estimated net payable {mySalary.salary_configured ? "" : "· salary not configured"}
                  </div>
                  <div className="space-y-1.5 text-sm">
                    <SalRow k="Monthly salary" v={inr(mySalary.employee?.monthly_salary)} />
                    <SalRow k={`Payable days (${mySalary.payable_days})`} v={inr(mySalary.per_day_rate)} sub="per day" />
                    <SalRow k={`LOP days (${mySalary.lop_days})`} v={`− ${inr(mySalary.lop_deduction)}`} red />
                    <SalRow k="Late fine" v={`− ${inr(mySalary.late_fine)}`} red={mySalary.late_fine > 0} />
                    <SalRow k={`Short leave (${mySalary.short_leave_hours}h)`} v={`− ${inr(mySalary.short_leave_deduction)}`} red={mySalary.short_leave_deduction > 0} />
                  </div>
                  <button onClick={() => downloadPayslip(mySalary.employee.id, ym.y, ym.m)}
                    className="btn-ghost text-xs mt-3" data-testid="my-payslip-btn">
                    <DownloadSimple size={13} /> Download payslip (PDF)
                  </button>
                </>
              )}
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
        </div>
      )}

      {tab === "leaves" && (
        <div className="space-y-4">
          <div className="flex justify-end gap-2">
            <button onClick={() => { setShowCorrForm(!showCorrForm); setShowLeaveForm(false); }} className="btn-ghost" data-testid="new-correction-btn">
              <Clock size={14} /> {showCorrForm ? "Cancel" : "Request correction"}
            </button>
            <button onClick={() => { setShowLeaveForm(!showLeaveForm); setShowCorrForm(false); }} className="btn-primary" data-testid="new-leave-btn">
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
          {showCorrForm && (
            <form onSubmit={submitCorrection} className="card-flat grid grid-cols-1 md:grid-cols-4 gap-3" data-testid="correction-form">
              <input type="date" required className="input-flat" value={corrForm.date} onChange={(e) => setCorrForm({ ...corrForm, date: e.target.value })} data-testid="corr-date" />
              <input type="time" className="input-flat" title="Requested check-in" value={corrForm.in_time} onChange={(e) => setCorrForm({ ...corrForm, in_time: e.target.value })} data-testid="corr-in" />
              <input type="time" className="input-flat" title="Requested check-out" value={corrForm.out_time} onChange={(e) => setCorrForm({ ...corrForm, out_time: e.target.value })} data-testid="corr-out" />
              <input required className="input-flat" placeholder="Reason — forgot to punch…" value={corrForm.reason} onChange={(e) => setCorrForm({ ...corrForm, reason: e.target.value })} data-testid="corr-reason" />
              <button className="btn-primary md:col-span-4" data-testid="corr-submit"><PaperPlaneRight size={14} /> Submit correction</button>
            </form>
          )}
          <div className="border border-[#E5E5E5] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
                <tr><th className="p-2 text-left">Employee</th><th className="p-2 text-left">Type</th><th className="p-2 text-left">From</th><th className="p-2 text-left">To</th><th className="p-2 text-left">Days</th><th className="p-2 text-left">Reason</th><th className="p-2 text-left">Status</th></tr>
              </thead>
              <tbody>
                {leaves.map((l) => (
                  <tr key={l.id} className="border-t border-[#F0F0F0]" data-testid={`leave-${l.id}`}>
                    <td className="p-2 font-semibold" data-testid={`leave-emp-${l.id}`}>{l.employee_name || "—"}</td>
                    <td className="p-2 capitalize">{l.leave_type}</td>
                    <td className="p-2 font-mono text-xs">{l.from_date}</td>
                    <td className="p-2 font-mono text-xs">{l.to_date}</td>
                    <td className="p-2 font-mono">{l.days}</td>
                    <td className="p-2 text-xs text-[#5C5C5C] truncate max-w-[300px]">{l.reason}</td>
                    <td className="p-2"><LeaveStatus s={l.status} /></td>
                  </tr>
                ))}
                {leaves.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-[#9A9A9A] text-sm">No leaves yet.</td></tr>}
              </tbody>
            </table>
          </div>
          {myCorrections.length > 0 && (
            <div className="card-flat" data-testid="my-corrections">
              <div className="overline mb-2">MY CORRECTION REQUESTS</div>
              {myCorrections.map((c) => (
                <div key={c.id} className="flex items-center justify-between border-b border-[#F0F0F0] py-2 text-sm">
                  <div>
                    <span className="font-mono text-xs">{c.date}</span>
                    <span className="text-[#5C5C5C] text-xs ml-2">{c.reason}</span>
                  </div>
                  <LeaveStatus s={c.status} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "dashboard" && isHR && <TeamDashboardTab />}
      {tab === "live" && isHR && <LiveBoardTab />}

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
                  <th className="p-2">Present</th><th className="p-2">Late</th><th className="p-2">Absent</th>
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
                    <td className="p-2 text-center font-mono text-[#B87500]">{r.counts.late || 0}</td>
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

      {tab === "payroll" && isHR && <PayrollTab />}
      {tab === "requests" && isHR && <RequestsTab canWrite={isHRWrite} />}
      {tab === "setup" && isHRWrite && <SetupTab policy={policy} onPolicySaved={loadMe} />}
      {tab === "geo" && isAdmin && <GeoPolicyTab projects={projects} />}
    </div>
  );
}

function SalRow({ k, v, sub, red }) {
  return (
    <div className="flex items-center justify-between border-b border-[#F0F0F0] py-1.5">
      <span className="text-[#5C5C5C] text-xs">{k}{sub ? <span className="text-[#9A9A9A]"> · {sub}</span> : null}</span>
      <span className={`font-mono text-xs ${red ? "text-[#B4001C]" : ""}`}>{v}</span>
    </div>
  );
}

/* ==================================================
   Team Dashboard — HR stats + today's punches
   ================================================== */
function TeamDashboardTab() {
  const [dash, setDash] = useState(null);
  const [recs, setRecs] = useState([]);
  const todayStr = new Date().toISOString().slice(0, 10);

  const load = useCallback(async () => {
    const [d, r] = await Promise.all([
      api.get("/attendance/dashboard"),
      api.get(`/attendance/records?start=${todayStr}&end=${todayStr}`),
    ]);
    setDash(d.data); setRecs(r.data);
  }, [todayStr]);
  useEffect(() => { load(); }, [load]);

  if (!dash) return <div className="skeleton h-64 w-full" />;
  const cards = [
    ["Present Today", dash.present_today, "#1D633E"],
    ["Late Today", dash.late_today, "#B87500"],
    ["Absent Today", dash.absent_today, "#B4001C"],
    ["On Leave", dash.on_leave, "#8A6DFF"],
    ["Checked In Now", dash.currently_checked_in, "#8B7F6A"],
    ["Checked Out", dash.checked_out, "#5C5C5C"],
    ["Pending Late Approvals", dash.pending_late_approvals, "#F0A93A"],
    ["Pending Leaves", dash.pending_leaves, "#0E7490"],
  ];
  return (
    <div className="space-y-6" data-testid="team-dashboard">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cards.map(([l, v, c]) => (
          <div key={l} className="card-flat" data-testid={`dash-${l.toLowerCase().replace(/ /g, "-")}`}>
            <div className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">{l}</div>
            <div className="font-display font-bold text-3xl mt-1" style={{ color: c }}>{v}</div>
          </div>
        ))}
      </div>

      <div className="card-flat" data-testid="today-punches">
        <div className="flex items-center justify-between mb-3">
          <div className="overline">TODAY'S CHECK-IN / CHECK-OUT</div>
          <button onClick={load} className="btn-ghost text-xs" data-testid="dash-refresh">
            <ArrowsClockwise size={13} /> Refresh
          </button>
        </div>
        {recs.length === 0 ? (
          <div className="text-sm text-[#9A9A9A] py-6 text-center">No employee has marked attendance today yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
                <tr><th className="p-2 text-left">Employee</th><th className="p-2">In</th><th className="p-2">Out</th><th className="p-2">Status</th><th className="p-2">Fence</th></tr>
              </thead>
              <tbody>
                {recs.map((r) => (
                  <tr key={r.id} className="border-t border-[#F0F0F0]" data-testid={`punch-${r.employee_id}`}>
                    <td className="p-2 font-semibold">{r.employee_name}</td>
                    <td className="p-2 text-center font-mono text-xs">{fmtT(r.check_in) || "—"}</td>
                    <td className="p-2 text-center font-mono text-xs">{fmtT(r.check_out) || "—"}</td>
                    <td className="p-2 text-center">
                      <span className="status-chip" style={{ background: `${STATUS_COLORS[r.status]}15`, color: STATUS_COLORS[r.status] }}>
                        {r.status?.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="p-2 text-center text-xs">
                      {r.check_in == null ? "—"
                        : r.geo_inside === false
                          ? <span className="text-[#B87500] font-semibold"><MapPin size={11} className="inline" /> Outside</span>
                          : <span className="text-[#1D633E] font-semibold"><MapPin size={11} className="inline" /> In fence</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ==================================================
   Live Board — auto-refreshing who's in / out
   ================================================== */
const LIVE_LABEL = {
  checked_in: ["Checked In", "#1D633E"], late: ["Late", "#B87500"],
  checked_out: ["Checked Out", "#5C5C5C"], absent: ["Absent", "#B4001C"],
  on_leave: ["On Leave", "#8A6DFF"], weekly_off: ["Weekly Off", "#9A9A9A"],
  holiday: ["Holiday", "#3B82F6"],
};
function LiveBoardTab() {
  const [data, setData] = useState(null);
  const load = useCallback(() => { api.get("/attendance/live").then((r) => setData(r.data)).catch(() => {}); }, []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  if (!data) return <div className="skeleton h-64 w-full" />;
  const c = data.counts;
  const chips = [
    ["Checked In", c.checked_in, "#1D633E"], ["Late", c.late, "#B87500"],
    ["Absent", c.absent, "#B4001C"], ["On Leave", c.on_leave, "#8A6DFF"],
    ["Checked Out", c.checked_out, "#5C5C5C"], ["Off / Holiday", c.off, "#3B82F6"],
  ];
  return (
    <div className="space-y-5" data-testid="live-board">
      <div className="flex items-center gap-2 text-xs font-mono text-[#5C5C5C]">
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#1D633E] opacity-50" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#1D633E]" />
        </span>
        LIVE · updated {data.generated_at} IST · auto-refresh 15s
      </div>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {chips.map(([l, v, col]) => (
          <div key={l} className="card-flat text-center">
            <div className="font-display font-bold text-2xl" style={{ color: col }}>{v}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C] mt-1">{l}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {data.people.map((p) => {
          const [label, col] = LIVE_LABEL[p.status] || LIVE_LABEL.checked_out;
          return (
            <div key={p.employee_id} className="card-flat flex items-center justify-between" data-testid={`live-${p.employee_id}`}>
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-full border border-[#E5E5E5] flex items-center justify-center font-display font-bold text-sm shrink-0">
                  {(p.name || "?").charAt(0)}
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-sm truncate">{p.name}</div>
                  <div className="text-[11px] text-[#9A9A9A] truncate">{p.department || "Staff"}{p.shift_start ? ` · ${p.shift_start}` : ""}</div>
                </div>
              </div>
              <div className="text-right shrink-0 ml-2">
                <span className="status-chip" style={{ background: `${col}15`, color: col }}>{label}</span>
                {p.check_in && <div className="text-[10px] font-mono text-[#9A9A9A] mt-0.5">in {p.check_in}{p.check_out ? ` · out ${p.check_out}` : ""}</div>}
              </div>
            </div>
          );
        })}
        {data.people.length === 0 && <div className="col-span-full text-center text-[#9A9A9A] py-10">No employees yet.</div>}
      </div>
    </div>
  );
}

/* ==================================================
   Payroll Preview — Jewellers engine (LOP + fines + short leave)
   ================================================== */
function PayrollTab() {
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get(`/payroll/preview?year=${ym.y}&month=${ym.m}`);
      setData(d);
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to load payroll preview");
    } finally { setLoading(false); }
  }, [ym]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="payroll-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <MonthPicker ym={ym} setYm={setYm} />
        {data && (
          <div className="text-sm text-[#5C5C5C]">
            Total net payable:{" "}
            <span className="font-display font-bold text-xl text-[#0A0A0A]" data-testid="payroll-total-net">
              {inr(data.total_net_payable)}
            </span>
          </div>
        )}
      </div>
      {data?.unconfigured_salary_count > 0 && (
        <div className="border border-[#B87500] bg-[#FFF6E5] p-3 text-xs text-[#8a5a00] flex items-start gap-2" data-testid="payroll-unconfigured-warning">
          <Warning size={14} className="shrink-0 mt-0.5" />
          <span><b>{data.unconfigured_salary_count}</b> employee(s) have no salary configured — their net shows ₹0.
          Set the salary structure on the employee profile or a flat monthly salary in <b>Shift & Salary Setup</b>.</span>
        </div>
      )}
      <div className="border border-[#E5E5E5] overflow-x-auto">
        {loading ? <div className="skeleton h-40 w-full" /> : (
          <table className="w-full text-sm">
            <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
              <tr>
                <th className="p-2 text-left">Employee</th>
                <th className="p-2 text-right">Salary</th>
                <th className="p-2">Payable Days</th>
                <th className="p-2">Present</th><th className="p-2">Absent</th>
                <th className="p-2">LOP</th>
                <th className="p-2 text-right">Fine / Hourly</th>
                <th className="p-2 text-right">Deduction</th>
                <th className="p-2 text-right">Net Payable</th>
                <th className="p-2">Slip</th>
              </tr>
            </thead>
            <tbody>
              {(data?.employees || []).map((r) => (
                <tr key={r.employee_id} className="border-t border-[#F0F0F0]" data-testid={`payroll-row-${r.employee_id}`}>
                  <td className="p-2">
                    <div className="font-semibold">{r.employee_name}</div>
                    <div className="text-[11px] text-[#9A9A9A]">{r.department || "Staff"}{r.already_paid ? " · PAID" : ""}</div>
                  </td>
                  <td className="p-2 text-right font-mono text-xs">
                    {r.salary_configured ? inr(r.monthly_salary)
                      : <span className="text-[#B87500] font-semibold" data-testid={`salary-not-set-${r.employee_id}`}>Not set</span>}
                  </td>
                  <td className="p-2 text-center font-mono font-semibold">{r.payable_days}</td>
                  <td className="p-2 text-center font-mono text-[#1D633E]">{r.present + r.late}</td>
                  <td className="p-2 text-center font-mono text-[#B4001C]">{r.absent}</td>
                  <td className="p-2 text-center font-mono text-[#F0A93A]">{r.lop_days}</td>
                  <td className="p-2 text-right font-mono text-xs text-[#B87500]">
                    {(r.late_fine || r.short_leave_deduction)
                      ? inr((r.late_fine || 0) + (r.short_leave_deduction || 0))
                      : "—"}
                    {r.short_leave_hours ? <div className="text-[10px] text-[#0E7490]">{r.short_leave_hours}h</div> : null}
                  </td>
                  <td className="p-2 text-right font-mono text-xs text-[#B4001C]">{inr(r.deduction)}</td>
                  <td className="p-2 text-right font-mono font-bold" data-testid={`net-${r.employee_id}`}>{inr(r.net_payable)}</td>
                  <td className="p-2 text-center">
                    <button onClick={() => downloadPayslip(r.employee_id, ym.y, ym.m)}
                      className="btn-ghost text-xs px-2" title="Download payslip PDF"
                      data-testid={`payslip-${r.employee_id}`}>
                      <DownloadSimple size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {(!data || data.employees.length === 0) && !loading && (
                <tr><td colSpan={10} className="p-8 text-center text-[#9A9A9A]">No employees.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      <div className="text-[11px] text-[#9A9A9A] font-mono">
        Net = monthly salary − (LOP deduction + late fines + short-leave hours). Actual payment posts a journal entry to Accounting from the employee profile.
      </div>
    </div>
  );
}

/* ==================================================
   Requests — late approvals + leaves + corrections + site visits
   ================================================== */
function RequestsTab({ canWrite }) {
  const [lates, setLates] = useState([]);
  const [pendingLeaves, setPendingLeaves] = useState([]);
  const [corrections, setCorrections] = useState([]);
  const [pendingSite, setPendingSite] = useState([]);

  const load = useCallback(async () => {
    const [l, lv, c, s] = await Promise.all([
      api.get("/attendance/late-approvals?status=pending").catch(() => ({ data: [] })),
      api.get("/leaves?status=pending").catch(() => ({ data: [] })),
      api.get("/attendance/corrections?status=pending").catch(() => ({ data: [] })),
      api.get("/attendance/pending-approvals").catch(() => ({ data: [] })),
    ]);
    setLates(l.data); setPendingLeaves(lv.data); setCorrections(c.data); setPendingSite(s.data);
  }, []);
  useEffect(() => { load(); }, [load]);

  const reviewLate = async (id, status) => {
    await api.put(`/attendance/${id}/late-review`, { status });
    load();
  };
  const actLeave = async (id, action) => {
    await api.post(`/leaves/${id}/action`, { action });
    load();
  };
  const reviewCorr = async (id, status) => {
    await api.put(`/attendance/corrections/${id}/review`, { status });
    load();
  };
  const actSite = async (id, action) => {
    await api.post(`/attendance/${id}/approve`, { action });
    load();
  };

  return (
    <div className="space-y-6" data-testid="requests-tab">
      {/* Late arrival approvals */}
      <div className="card-flat" data-testid="late-approvals-card">
        <div className="overline mb-3">LATE ARRIVAL APPROVALS · {lates.length} PENDING</div>
        {lates.length === 0 && <div className="text-sm text-[#9A9A9A] py-4 text-center">No late arrivals awaiting approval.</div>}
        <div className="space-y-2">
          {lates.map((l) => (
            <div key={l.id} className="flex flex-wrap items-center gap-3 border border-[#F0F0F0] p-3" data-testid={`late-row-${l.id}`}>
              <div className="flex-1 min-w-[220px]">
                <div className="font-semibold" data-testid={`late-emp-${l.id}`}>{l.employee_name}</div>
                <div className="text-xs font-mono text-[#5C5C5C]">
                  {l.date} · {l.late_minutes}m late
                  {l.late_fine_amount > 0 && <span className="text-[#B87500]"> · Fine {inr(l.late_fine_amount)} — approve to waive</span>}
                </div>
                <div className="text-xs text-[#5C5C5C] mt-0.5">
                  {l.late_category ? capWords(l.late_category) : "No category"}
                  {l.late_reason ? ` — “${l.late_reason}”` : ""}
                </div>
              </div>
              {canWrite && (
                <>
                  <button onClick={() => reviewLate(l.id, "approved")} className="btn-primary bg-[#1D633E] text-xs" data-testid={`late-approve-${l.id}`}>
                    <CheckCircle size={13} /> Approve (waive fine)
                  </button>
                  <button onClick={() => reviewLate(l.id, "rejected")} className="btn-ghost text-[#B4001C] text-xs" data-testid={`late-reject-${l.id}`}>
                    <X size={13} /> Reject (keep fine)
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Leave permissions — employee name MUST be prominent */}
        <div className="card-flat" data-testid="pending-leaves-card">
          <div className="overline mb-3">LEAVE PERMISSIONS · {pendingLeaves.length} PENDING</div>
          {pendingLeaves.length === 0 && <div className="text-sm text-[#9A9A9A] py-4 text-center">Nothing to review.</div>}
          <div className="space-y-2">
            {pendingLeaves.map((l) => (
              <div key={l.id} className="border border-[#F0F0F0] p-3" data-testid={`pending-${l.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-display font-bold text-base" data-testid={`leave-employee-name-${l.id}`}>
                      {l.employee_name || "Unknown employee"}
                    </div>
                    <div className="text-xs font-mono text-[#5C5C5C] mt-0.5">
                      <span className="capitalize text-[#8A6DFF] font-semibold">{l.leave_type}</span>
                      {" · "}{l.from_date} → {l.to_date} · {l.days} day{l.days !== 1 ? "s" : ""}
                    </div>
                    {l.reason && <div className="text-xs text-[#5C5C5C] mt-1">“{l.reason}”</div>}
                  </div>
                </div>
                {canWrite && (
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => actLeave(l.id, "approve")} className="btn-primary bg-[#1D633E] text-xs" data-testid={`approve-${l.id}`}>
                      <CheckCircle size={13} /> Approve
                    </button>
                    <button onClick={() => actLeave(l.id, "reject")} className="btn-ghost text-[#B4001C] text-xs" data-testid={`reject-${l.id}`}>
                      <X size={13} /> Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Corrections */}
        <div className="card-flat" data-testid="corrections-card">
          <div className="overline mb-3">ATTENDANCE CORRECTIONS · {corrections.length} PENDING</div>
          {corrections.length === 0 && <div className="text-sm text-[#9A9A9A] py-4 text-center">No correction requests.</div>}
          <div className="space-y-2">
            {corrections.map((c) => (
              <div key={c.id} className="border border-[#F0F0F0] p-3" data-testid={`corr-${c.id}`}>
                <div className="font-semibold">{c.employee_name}</div>
                <div className="text-xs font-mono text-[#5C5C5C]">{c.date}
                  {c.requested_check_in ? ` · in ${fmtT(c.requested_check_in)}` : ""}
                  {c.requested_check_out ? ` · out ${fmtT(c.requested_check_out)}` : ""}
                </div>
                <div className="text-xs text-[#5C5C5C] mt-1">“{c.reason}”</div>
                {canWrite && (
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => reviewCorr(c.id, "approved")} className="btn-primary bg-[#1D633E] text-xs" data-testid={`corr-approve-${c.id}`}>
                      <CheckCircle size={13} /> Approve
                    </button>
                    <button onClick={() => reviewCorr(c.id, "rejected")} className="btn-ghost text-[#B4001C] text-xs" data-testid={`corr-reject-${c.id}`}>
                      <X size={13} /> Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Site visit approvals (existing flow, preserved) */}
      <div className="card-flat" data-testid="site-approvals-card">
        <div className="overline mb-3">SITE VISIT / OUT-OF-FENCE APPROVALS · {pendingSite.length} PENDING</div>
        {pendingSite.length === 0 && <div className="text-sm text-[#9A9A9A] py-4 text-center">All clear.</div>}
        <div className="space-y-2">
          {pendingSite.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-3 border border-[#F0F0F0] p-3" data-testid={`site-req-${r.id}`}>
              <div className="flex-1 min-w-[240px]">
                <div className="font-semibold">{r.employee_name}</div>
                <div className="text-xs font-mono text-[#5C5C5C]">
                  {r.date} · {fmtT(r.check_in)}
                  {r.geo_distance_m && r.geo_inside === false ? ` · ${Math.round(r.geo_distance_m)}m outside fence` : ""}
                </div>
                <div className="text-xs text-[#5C5C5C] mt-1">
                  {r.site_location && <>📍 {r.site_location} · </>}
                  {r.site_reason && <>“{r.site_reason}”</>}
                </div>
              </div>
              {canWrite && (
                <>
                  <button onClick={() => actSite(r.id, "approve")} className="btn-primary bg-[#1D633E] text-xs" data-testid={`site-approve-${r.id}`}>
                    <CheckCircle size={13} /> Approve
                  </button>
                  <button onClick={() => actSite(r.id, "reject")} className="btn-ghost text-[#B4001C] text-xs" data-testid={`site-reject-${r.id}`}>
                    <X size={13} /> Reject
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ==================================================
   Setup — per-employee shift/salary + short leave + late fine config
   ================================================== */
function SetupTab({ policy, onPolicySaved }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="setup-tab">
      <div className="space-y-6">
        <EmployeeSetupCard />
        <ShortLeaveCard />
      </div>
      <div className="space-y-6">
        <LateConfigCard policy={policy} onSaved={onPolicySaved} />
        <ManualAttendanceCard />
      </div>
    </div>
  );
}

function EmployeeSetupCard() {
  const [emps, setEmps] = useState([]);
  const [sel, setSel] = useState("");
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState(null);

  useEffect(() => {
    api.get("/employees").then((r) => setEmps(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    if (!sel) { setCfg(null); return; }
    api.get(`/attendance/employees/${sel}/config`).then((r) => setCfg({
      shift_start: r.data.shift_start || "10:00",
      shift_end: r.data.shift_end || "19:00",
      grace_minutes: r.data.grace_minutes ?? "",
      weekly_offs: r.data.weekly_offs,
      monthly_salary: r.data.monthly_salary || 0,
      payroll_basis_days: r.data.payroll_basis_days || 26,
      net_monthly_structure: r.data.net_monthly_structure,
      effective_monthly_salary: r.data.effective_monthly_salary,
      name: r.data.name,
    })).catch(() => {});
  }, [sel]);

  const toggleOff = (v) => setCfg((c) => {
    const cur = c.weekly_offs == null ? [] : c.weekly_offs;
    return { ...c, weekly_offs: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] };
  });

  const save = async () => {
    if (!sel) { alert("Select an employee"); return; }
    setBusy(true);
    try {
      await api.put(`/attendance/employees/${sel}/config`, {
        shift_start: cfg.shift_start, shift_end: cfg.shift_end,
        grace_minutes: cfg.grace_minutes === "" ? null : Number(cfg.grace_minutes),
        weekly_offs: cfg.weekly_offs,
        monthly_salary: Number(cfg.monthly_salary) || 0,
        payroll_basis_days: Number(cfg.payroll_basis_days) || 26,
      });
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to save");
    } finally { setBusy(false); }
  };

  const empLabel = (e) => `${e.first_name || ""} ${e.last_name || ""}`.trim() || e.employee_id || e.id;

  return (
    <div className="card-flat space-y-3" data-testid="employee-setup-card">
      <div className="flex items-center justify-between">
        <div className="overline">EMPLOYEE SHIFT, WEEKLY-OFF & SALARY</div>
        {savedAt && <span className="text-xs text-[#1D633E] font-mono">SAVED</span>}
      </div>
      <select className="input-flat w-full" value={sel} onChange={(e) => setSel(e.target.value)} data-testid="setup-employee-select">
        <option value="">Select employee…</option>
        {emps.map((e) => <option key={e.id} value={e.id}>{empLabel(e)} — {e.department || "Staff"}</option>)}
      </select>
      {cfg && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Shift start"><input type="time" className="input-flat w-full" value={cfg.shift_start} onChange={(e) => setCfg({ ...cfg, shift_start: e.target.value })} data-testid="setup-shift-start" /></Field>
            <Field label="Shift end"><input type="time" className="input-flat w-full" value={cfg.shift_end} onChange={(e) => setCfg({ ...cfg, shift_end: e.target.value })} /></Field>
            <Field label="Grace (min · blank = policy)"><input type="number" className="input-flat w-full" value={cfg.grace_minutes} onChange={(e) => setCfg({ ...cfg, grace_minutes: e.target.value })} data-testid="setup-grace" /></Field>
            <Field label="Payroll basis days"><input type="number" className="input-flat w-full" value={cfg.payroll_basis_days} onChange={(e) => setCfg({ ...cfg, payroll_basis_days: e.target.value })} data-testid="setup-basis" /></Field>
            <Field label="Flat monthly salary (₹)"><input type="number" className="input-flat w-full" value={cfg.monthly_salary} onChange={(e) => setCfg({ ...cfg, monthly_salary: e.target.value })} data-testid="setup-monthly-salary" /></Field>
            <Field label="Effective salary used">
              <div className="input-flat w-full bg-[#FAFAFA] font-mono text-sm">{inr(cfg.net_monthly_structure > 0 ? cfg.net_monthly_structure : cfg.monthly_salary)}</div>
            </Field>
          </div>
          <div className="text-[11px] text-[#9A9A9A]">
            If a detailed salary structure exists on the employee profile, its net monthly is used;
            otherwise the flat monthly salary above applies.
          </div>
          <div>
            <div className="text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">
              Weekly offs <span className="text-[#9A9A9A] normal-case">(per-employee override · blank = org policy)</span>
            </div>
            <div className="flex gap-1.5 flex-wrap" data-testid="setup-weekly-offs">
              {WEEKDAYS.map((d) => (
                <button key={d.v} type="button" onClick={() => toggleOff(d.v)}
                  className={`px-3 py-1.5 text-xs font-mono border ${cfg.weekly_offs != null && cfg.weekly_offs.includes(d.v)
                    ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "border-[#E5E5E5] text-[#5C5C5C]"}`}
                  data-testid={`weekly-off-${d.v}`}>{d.l}</button>
              ))}
              <button type="button" onClick={() => setCfg({ ...cfg, weekly_offs: null })}
                className="px-3 py-1.5 text-xs font-mono border border-[#E5E5E5] text-[#9A9A9A]">
                Use policy
              </button>
            </div>
          </div>
          <button onClick={save} disabled={busy} className="btn-primary text-xs" data-testid="setup-save">
            {busy ? "Saving…" : "Save configuration"}
          </button>
        </>
      )}
    </div>
  );
}

function ShortLeaveCard() {
  const [emps, setEmps] = useState([]);
  const [form, setForm] = useState({ employee_id: "", date: "", hours: 1, reason: "" });
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  useEffect(() => { api.get("/employees").then((r) => setEmps(r.data)).catch(() => {}); }, []);
  const save = async () => {
    if (!form.employee_id) { alert("Select an employee"); return; }
    if (!form.date) { alert("Pick a date"); return; }
    if (!form.hours || form.hours <= 0) { alert("Hours must be > 0"); return; }
    setBusy(true);
    try {
      await api.post("/attendance/short-leave", { ...form, hours: Number(form.hours) });
      setOk(true); setTimeout(() => setOk(false), 2500);
      setForm((f) => ({ ...f, reason: "", hours: 1 }));
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };
  const empLabel = (e) => `${e.first_name || ""} ${e.last_name || ""}`.trim() || e.employee_id || e.id;
  return (
    <div className="card-flat space-y-3" data-testid="short-leave-card">
      <div className="flex items-center justify-between">
        <div className="overline">SHORT / HOURLY LEAVE</div>
        {ok && <span className="text-xs text-[#1D633E] font-mono">RECORDED</span>}
      </div>
      <div className="text-[11px] text-[#9A9A9A]">
        Record a few hours off on a day. Salary deducts <b>hourly-rate × hours</b> (hourly rate = per-day ÷ full-day hours).
      </div>
      <select className="input-flat w-full" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="sl-employee">
        <option value="">Select employee…</option>
        {emps.map((e) => <option key={e.id} value={e.id}>{empLabel(e)} — {e.department || "Staff"}</option>)}
      </select>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Date"><input type="date" className="input-flat w-full" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="sl-date" /></Field>
        <Field label="Hours"><input type="number" min="0.5" step="0.5" className="input-flat w-full" value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} data-testid="sl-hours" /></Field>
      </div>
      <input className="input-flat w-full" placeholder="Reason (optional) — e.g. doctor visit" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} data-testid="sl-reason" />
      <button onClick={save} disabled={busy} className="btn-primary text-xs" data-testid="sl-save">
        <Plus size={13} /> {busy ? "Saving…" : "Record short leave"}
      </button>
    </div>
  );
}

function LateConfigCard({ policy, onSaved }) {
  const [p, setP] = useState(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  useEffect(() => {
    if (policy) setP({ ...policy });
    else api.get("/attendance/policy").then((r) => setP(r.data)).catch(() => {});
  }, [policy]);
  if (!p) return <div className="skeleton h-48 w-full" />;
  const cats = p.late_reason_categories || [];
  const addCat = () => {
    const key = input.trim().toLowerCase().replace(/\s+/g, "_");
    if (key && !cats.includes(key)) setP({ ...p, late_reason_categories: [...cats, key] });
    setInput("");
  };
  const save = async () => {
    setBusy(true);
    try {
      await api.put("/attendance/policy", {
        ...p,
        grace_minutes: Number(p.grace_minutes) || 0,
        late_fine_amount: Number(p.late_fine_amount) || 0,
        late_fine_daily_cap: Number(p.late_fine_daily_cap) || 0,
      });
      setSavedAt(Date.now()); setTimeout(() => setSavedAt(null), 2500);
      onSaved && onSaved();
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to save");
    } finally { setBusy(false); }
  };
  return (
    <div className="card-flat space-y-3" data-testid="late-config-card">
      <div className="flex items-center justify-between">
        <div className="overline">LATE FINE, GRACE & CATEGORIES</div>
        {savedAt && <span className="text-xs text-[#1D633E] font-mono">SAVED</span>}
      </div>
      <div className="border border-[#F0A93A] bg-[#FFF9EE] p-3 space-y-3">
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input type="checkbox" checked={!!p.late_fine_enabled}
            onChange={(e) => setP({ ...p, late_fine_enabled: e.target.checked })}
            className="accent-[#8B7F6A] w-4 h-4" data-testid="late-fine-toggle" />
          <span className="font-semibold">Enable ₹ late fine per occurrence</span>
        </label>
        <div className="text-[11px] text-[#8a5a00]">
          A late arrival is <b>never</b> auto-converted to half-day. Approving a late arrival waives its fine; rejecting keeps it.
        </div>
        {p.late_fine_enabled && (
          <div className="grid grid-cols-3 gap-2">
            <Field label="Fine / occurrence (₹)"><input type="number" min="0" className="input-flat w-full" value={p.late_fine_amount ?? 100} onChange={(e) => setP({ ...p, late_fine_amount: e.target.value })} data-testid="late-fine-amount" /></Field>
            <Field label="Max / day (₹, 0=∞)"><input type="number" min="0" className="input-flat w-full" value={p.late_fine_daily_cap ?? 500} onChange={(e) => setP({ ...p, late_fine_daily_cap: e.target.value })} data-testid="late-fine-cap" /></Field>
            <Field label="Grace (min)"><input type="number" min="0" className="input-flat w-full" value={p.grace_minutes ?? 15} onChange={(e) => setP({ ...p, grace_minutes: e.target.value })} data-testid="late-grace" /></Field>
          </div>
        )}
      </div>
      <div>
        <div className="text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Late reason categories</div>
        <div className="flex flex-wrap gap-1.5 mb-2" data-testid="late-cats">
          {cats.map((c) => (
            <span key={c} className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-[#F5F4F0] text-[#8B7F6A] font-mono">
              {capWords(c)}
              <button onClick={() => setP({ ...p, late_reason_categories: cats.filter((x) => x !== c) })}
                className="text-[#9A9A9A] hover:text-[#B4001C]"><X size={11} /></button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input className="input-flat flex-1" placeholder="Add category — e.g. Public Transport" value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCat(); } }}
            data-testid="late-cat-input" />
          <button onClick={addCat} className="btn-ghost text-xs" data-testid="late-cat-add"><Plus size={13} /> Add</button>
        </div>
      </div>
      <Field label="If fine system is OFF and a late arrival is REJECTED, deduct">
        <select className="input-flat w-full" value={p.late_rejection_penalty || "half_day"}
          onChange={(e) => setP({ ...p, late_rejection_penalty: e.target.value })} data-testid="late-penalty-select">
          <option value="half_day">Half day (0.5 day)</option>
          <option value="full_day">Full day (1 day)</option>
          <option value="none">No deduction (warning only)</option>
        </select>
      </Field>
      <button onClick={save} disabled={busy} className="btn-primary text-xs" data-testid="late-config-save">
        <Gear size={13} /> {busy ? "Saving…" : "Save late settings"}
      </button>
    </div>
  );
}

function ManualAttendanceCard() {
  const [emps, setEmps] = useState([]);
  const [meta, setMeta] = useState(null);
  const [form, setForm] = useState({ employee_id: "", date: "", status: "present", in_time: "", out_time: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  useEffect(() => {
    api.get("/employees").then((r) => setEmps(r.data)).catch(() => {});
    api.get("/attendance/meta").then((r) => setMeta(r.data)).catch(() => {});
  }, []);
  const save = async () => {
    if (!form.employee_id || !form.date) { alert("Employee and date are required"); return; }
    setBusy(true);
    try {
      const payload = {
        employee_id: form.employee_id, date: form.date, status: form.status,
        notes: form.notes || null,
      };
      if (form.in_time) payload.check_in = `${form.date}T${form.in_time}:00+05:30`;
      if (form.out_time) payload.check_out = `${form.date}T${form.out_time}:00+05:30`;
      await api.post("/attendance/manual", payload);
      setOk(true); setTimeout(() => setOk(false), 2500);
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };
  const empLabel = (e) => `${e.first_name || ""} ${e.last_name || ""}`.trim() || e.employee_id || e.id;
  return (
    <div className="card-flat space-y-3" data-testid="manual-attendance-card">
      <div className="flex items-center justify-between">
        <div className="overline">MANUAL ATTENDANCE ENTRY</div>
        {ok && <span className="text-xs text-[#1D633E] font-mono">SAVED</span>}
      </div>
      <select className="input-flat w-full" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="manual-employee">
        <option value="">Select employee…</option>
        {emps.map((e) => <option key={e.id} value={e.id}>{empLabel(e)} — {e.department || "Staff"}</option>)}
      </select>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Date"><input type="date" className="input-flat w-full" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="manual-date" /></Field>
        <Field label="Status">
          <select className="input-flat w-full" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="manual-status">
            {(meta?.statuses || ["present", "absent", "half_day", "leave"]).map((s) => <option key={s} value={s}>{capWords(s)}</option>)}
          </select>
        </Field>
        <Field label="Check-in (optional)"><input type="time" className="input-flat w-full" value={form.in_time} onChange={(e) => setForm({ ...form, in_time: e.target.value })} /></Field>
        <Field label="Check-out (optional)"><input type="time" className="input-flat w-full" value={form.out_time} onChange={(e) => setForm({ ...form, out_time: e.target.value })} /></Field>
      </div>
      <input className="input-flat w-full" placeholder="Notes (optional)" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      <button onClick={save} disabled={busy} className="btn-primary text-xs" data-testid="manual-save">
        <ClipboardText size={13} /> {busy ? "Saving…" : "Save attendance"}
      </button>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">{label}</label>
      {children}
    </div>
  );
}

/* ==================================================
   Geo & Policy — Admin configuration (preserved)
   ================================================== */
function GeoPolicyTab({ projects }) {
  const [policy, setPolicy] = useState(null);
  const [locations, setLocations] = useState([]);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [locForm, setLocForm] = useState({
    name: "", kind: "office", lat: "", lng: "", radius_m: 150, project_id: "", address: "",
  });
  const [locBusy, setLocBusy] = useState(false);
  const [gpsBusy, setGpsBusy] = useState(false);

  const load = async () => {
    const [p, l] = await Promise.all([
      api.get("/attendance/policy"),
      api.get("/attendance/locations"),
    ]);
    setPolicy(p.data); setLocations(l.data);
  };
  useEffect(() => { load(); }, []);

  const setP = (patch) => setPolicy((p) => ({ ...p, ...patch }));

  const savePolicy = async () => {
    setSaving(true);
    try {
      const payload = {
        ...policy,
        office_start: policy.office_start, office_end: policy.office_end,
        grace_minutes: Number(policy.grace_minutes) || 0,
        half_day_min_hours: Number(policy.half_day_min_hours) || 4,
        full_day_min_hours: Number(policy.full_day_min_hours) || 8,
        weekly_off_days: policy.weekly_off_days || [6],
        holidays: policy.holidays || [],
        geo_fencing_enabled: !!policy.geo_fencing_enabled,
        require_geo_for_office: !!policy.require_geo_for_office,
        approval_required_when_outside: !!policy.approval_required_when_outside,
        default_office_lat: policy.default_office_lat === "" ? null : policy.default_office_lat,
        default_office_lng: policy.default_office_lng === "" ? null : policy.default_office_lng,
        default_office_radius_m: Number(policy.default_office_radius_m) || 150,
        max_gps_accuracy_m: Number(policy.max_gps_accuracy_m) || 100,
        require_late_reason: !!policy.require_late_reason,
      };
      await api.put("/attendance/policy", payload);
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to save policy");
    } finally { setSaving(false); }
  };

  const captureMyLocation = (target) => {
    if (!navigator.geolocation) { alert("Geolocation not supported"); return; }
    setGpsBusy(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const lat = Number(p.coords.latitude.toFixed(6));
        const lng = Number(p.coords.longitude.toFixed(6));
        if (target === "policy") setP({ default_office_lat: lat, default_office_lng: lng });
        else setLocForm((f) => ({ ...f, lat, lng }));
        setGpsBusy(false);
      },
      (err) => { alert(err.message || "Could not fetch GPS"); setGpsBusy(false); },
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const addLocation = async (e) => {
    e.preventDefault();
    if (!locForm.name.trim() || locForm.lat === "" || locForm.lng === "") {
      alert("Name, latitude and longitude are required"); return;
    }
    setLocBusy(true);
    try {
      await api.post("/attendance/locations", {
        name: locForm.name.trim(), kind: locForm.kind,
        lat: Number(locForm.lat), lng: Number(locForm.lng),
        radius_m: Number(locForm.radius_m) || 150,
        project_id: locForm.project_id || null,
        address: locForm.address || null, is_active: true,
      });
      setLocForm({ name: "", kind: "office", lat: "", lng: "", radius_m: 150, project_id: "", address: "" });
      load();
    } catch (e2) {
      alert(e2?.response?.data?.detail || "Failed to add location");
    } finally { setLocBusy(false); }
  };

  const deleteLocation = async (id) => {
    if (!window.confirm("Remove this geofence location?")) return;
    await api.delete(`/attendance/locations/${id}`);
    load();
  };

  if (!policy) return <div className="skeleton h-64 w-full" />;

  const KIND_LABELS = { office: "Office", site: "Project Site", warehouse: "Warehouse", client: "Client", vendor: "Vendor" };

  return (
    <div className="space-y-6" data-testid="geo-policy-tab">
      {/* -------- Interactive geofence map -------- */}
      <div className="card-flat">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="overline">GEOFENCE MAP</div>
          <button type="button" onClick={() => captureMyLocation("policy")} disabled={gpsBusy}
                  className="btn-ghost text-xs" data-testid="map-use-my-location">
            <MapPin size={13} /> {gpsBusy ? "Locating…" : "Use my current location"}
          </button>
        </div>
        <GeoFenceMap
          lat={policy.default_office_lat}
          lng={policy.default_office_lng}
          radius={policy.default_office_radius_m}
          locations={locations}
          onPick={(la, ln) => setP({ default_office_lat: la, default_office_lng: ln })}
          height={340}
        />
        <p className="text-[11px] text-[#9B9B9B] mt-2 leading-relaxed">
          Click anywhere on the map or drag the pin to set the <b>default office fence</b>.
          The solid circle is the office radius; dashed gold circles are saved geofence
          locations. Use <b>current location</b> to drop the pin where you are standing.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* -------- Policy editor -------- */}
      <div className="card-flat space-y-4">
        <div className="flex items-center justify-between">
          <div className="overline">ATTENDANCE POLICY</div>
          <div className="flex items-center gap-2">
            {savedAt && <span className="text-xs text-[#1D633E] font-mono">SAVED</span>}
            <button onClick={savePolicy} disabled={saving} className="btn-primary text-xs" data-testid="save-policy-btn">
              {saving ? "Saving…" : "Save policy"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Office start</label>
            <input type="time" className="input-flat w-full" value={policy.office_start || "10:00"}
                   onChange={(e) => setP({ office_start: e.target.value })} data-testid="policy-office-start" />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Office end</label>
            <input type="time" className="input-flat w-full" value={policy.office_end || "19:00"}
                   onChange={(e) => setP({ office_end: e.target.value })} />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Grace (minutes)</label>
            <input type="number" className="input-flat w-full" value={policy.grace_minutes ?? 15}
                   onChange={(e) => setP({ grace_minutes: e.target.value })} data-testid="policy-grace" />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase text-[#5C5C5C] mb-1">Max GPS accuracy (m)</label>
            <input type="number" className="input-flat w-full" value={policy.max_gps_accuracy_m ?? 100}
                   onChange={(e) => setP({ max_gps_accuracy_m: e.target.value })} data-testid="policy-accuracy" />
          </div>
        </div>

        <div className="space-y-2 pt-1">
          {[
            ["geo_fencing_enabled", "Enable geo-fencing for check-ins"],
            ["require_geo_for_office", "Require GPS for office check-in"],
            ["approval_required_when_outside", "Allow \u201cRequest approval\u201d when outside a fence"],
            ["require_late_reason", "Require a reason for late check-ins"],
          ].map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input type="checkbox" checked={!!policy[key]}
                     onChange={(e) => setP({ [key]: e.target.checked })}
                     data-testid={`policy-${key}`} className="accent-[#8B7F6A] w-4 h-4" />
              {label}
            </label>
          ))}
        </div>

        <div className="border-t border-[#F0F0F0] pt-3">
          <div className="overline mb-2">DEFAULT OFFICE FENCE (fallback)</div>
          <div className="grid grid-cols-3 gap-2">
            <input type="number" step="any" className="input-flat" placeholder="Latitude"
                   value={policy.default_office_lat ?? ""}
                   onChange={(e) => setP({ default_office_lat: e.target.value === "" ? "" : Number(e.target.value) })}
                   data-testid="policy-office-lat" />
            <input type="number" step="any" className="input-flat" placeholder="Longitude"
                   value={policy.default_office_lng ?? ""}
                   onChange={(e) => setP({ default_office_lng: e.target.value === "" ? "" : Number(e.target.value) })}
                   data-testid="policy-office-lng" />
            <input type="number" className="input-flat" placeholder="Radius m"
                   value={policy.default_office_radius_m ?? 150}
                   onChange={(e) => setP({ default_office_radius_m: e.target.value })} />
          </div>
          <button type="button" onClick={() => captureMyLocation("policy")} disabled={gpsBusy}
                  className="btn-ghost text-xs mt-2" data-testid="policy-use-my-location">
            📍 {gpsBusy ? "Locating…" : "Use my current location"}
          </button>
        </div>
      </div>

      {/* -------- Locations manager -------- */}
      <div className="space-y-4">
        <form onSubmit={addLocation} className="card-flat space-y-3" data-testid="add-location-form">
          <div className="overline">ADD GEOFENCE LOCATION</div>
          <div className="grid grid-cols-2 gap-2">
            <input className="input-flat" placeholder="Name — e.g. Head Office" value={locForm.name}
                   onChange={(e) => setLocForm({ ...locForm, name: e.target.value })} data-testid="loc-name" />
            <select className="input-flat" value={locForm.kind}
                    onChange={(e) => setLocForm({ ...locForm, kind: e.target.value })} data-testid="loc-kind">
              {Object.entries(KIND_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <input type="number" step="any" className="input-flat" placeholder="Latitude" value={locForm.lat}
                   onChange={(e) => setLocForm({ ...locForm, lat: e.target.value })} data-testid="loc-lat" />
            <input type="number" step="any" className="input-flat" placeholder="Longitude" value={locForm.lng}
                   onChange={(e) => setLocForm({ ...locForm, lng: e.target.value })} data-testid="loc-lng" />
            <input type="number" className="input-flat" placeholder="Radius (m)" value={locForm.radius_m}
                   onChange={(e) => setLocForm({ ...locForm, radius_m: e.target.value })} data-testid="loc-radius" />
            {locForm.kind === "site" && (
              <select className="input-flat" value={locForm.project_id}
                      onChange={(e) => setLocForm({ ...locForm, project_id: e.target.value })} data-testid="loc-project">
                <option value="">Link project (optional)…</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            )}
          </div>
          <input className="input-flat w-full" placeholder="Address (optional)" value={locForm.address}
                 onChange={(e) => setLocForm({ ...locForm, address: e.target.value })} />
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => captureMyLocation("form")} disabled={gpsBusy}
                    className="btn-ghost text-xs" data-testid="loc-use-my-location">
              📍 {gpsBusy ? "Locating…" : "Use my location"}
            </button>
            <button type="submit" disabled={locBusy} className="btn-primary text-xs ml-auto" data-testid="loc-add-btn">
              <Plus size={12} /> Add location
            </button>
          </div>
        </form>

        <div className="card-flat" data-testid="locations-list">
          <div className="overline mb-3">GEOFENCED LOCATIONS · {locations.length}</div>
          {locations.length === 0 && (
            <div className="text-sm text-[#9A9A9A] py-6 text-center">
              No geofences yet. While geo-fencing is enabled, out-of-fence check-ins
              go for approval — add a location here or set the default office fence,
              or disable geo-fencing in the policy.
            </div>
          )}
          <div className="space-y-2">
            {locations.map((l) => (
              <div key={l.id} className="flex items-center gap-3 border border-[#F0F0F0] p-2.5" data-testid={`loc-${l.id}`}>
                <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 bg-[#F5F4F0] text-[#8B7F6A]">
                  {KIND_LABELS[l.kind] || l.kind}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate">{l.name}</div>
                  <div className="text-[11px] font-mono text-[#5C5C5C]">
                    {Number(l.lat).toFixed(4)}, {Number(l.lng).toFixed(4)} · {l.radius_m}m radius
                  </div>
                </div>
                <button onClick={() => deleteLocation(l.id)} className="btn-ghost text-[#B4001C] px-2"
                        data-testid={`loc-delete-${l.id}`}>
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
    </div>
  );
}

function TabBtn({ id, tab, setTab, label }) {
  return (
    <button onClick={() => setTab(id)} data-testid={`tab-${id}`}
      className={`px-4 py-2.5 text-sm border-b-2 -mb-px transition whitespace-nowrap ${tab === id
        ? "border-[#8B7F6A] text-[#8B7F6A] font-semibold"
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
