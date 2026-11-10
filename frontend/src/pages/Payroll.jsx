import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  CaretLeft, CaretRight, ClockCounterClockwise, FileText, MagnifyingGlass, Money,
  PencilSimple, UserCircle, Warning, X,
} from "@phosphor-icons/react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import RowActions from "../components/RowActions";
import PdfPreviewModal from "../components/PdfPreview";
import { EmptyRow, SkeletonRows } from "../components/TableState";
import { PaySalaryBlock, cancelSalaryRun, editSalaryRun, salarySlipPath } from "../components/SalaryPayment";
import { useAuth } from "../context/AuthContext";
import { dateForInput, formatDate, formatINR } from "../lib/format";

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];
const inr = (n) => formatINR(n, { decimals: 0 });

function currentMonth() {
  const [y, m] = dateForInput(new Date()).split("-").map(Number);
  return { y, m };
}

/** Month read from ?month=YYYY-MM, else this month (India time). */
function monthFromParams(params) {
  const raw = params.get("month") || "";
  const match = /^(\d{4})-(\d{2})$/.exec(raw);
  if (match) {
    const y = Number(match[1]);
    const m = Number(match[2]);
    if (y >= 2000 && y <= 2100 && m >= 1 && m <= 12) return { y, m };
  }
  return currentMonth();
}

/**
 * Payroll — one month, every employee: what each person is owed, whether it
 * has been paid, and the actions to pay, correct, cancel or print the slip.
 */
export default function Payroll() {
  const { hasPerm } = useAuth();
  const navigate = useNavigate();
  const canPay = hasPerm("payroll.create");
  const canCorrect = canPay && hasPerm("finance.update");
  const [params, setParams] = useSearchParams();
  const ym = monthFromParams(params);
  const [preview, setPreview] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState("");
  const [q, setQ] = useState("");
  const [show, setShow] = useState("all");        // all | unpaid | paid
  const [paying, setPaying] = useState(null);     // row being paid
  const [slip, setSlip] = useState(null);         // { path, title, filename }

  const setMonth = (next) => {
    const p = new URLSearchParams(params);
    p.set("month", `${next.y}-${String(next.m).padStart(2, "0")}`);
    setParams(p, { replace: true });
  };
  const shiftMonth = (delta) => {
    const index = ym.y * 12 + (ym.m - 1) + delta;
    setMonth({ y: Math.floor(index / 12), m: (index % 12) + 1 });
  };
  const isThisMonth = (() => { const c = currentMonth(); return c.y === ym.y && c.m === ym.m; })();

  const load = useCallback(async () => {
    setLoading(true);
    setFailed("");
    try {
      const [p, r] = await Promise.all([
        api.get(`/payroll/preview?year=${ym.y}&month=${ym.m}`),
        api.get(`/payroll/runs?year=${ym.y}&month=${ym.m}`),
      ]);
      setPreview(p.data);
      setRuns(Array.isArray(r.data) ? r.data : []);
    } catch (error) {
      setPreview(null);
      setRuns([]);
      setFailed(error?.response?.data?.detail || "Payroll could not be loaded");
    } finally {
      setLoading(false);
    }
  }, [ym.y, ym.m]);
  useEffect(() => { load(); }, [load]);

  // One row per employee: the month's figures, plus the live payment if any.
  const rows = useMemo(() => {
    const live = new Map();
    for (const run of runs) {
      if (run.status === "paid" || run.status === "processing") live.set(run.employee_id, run);
    }
    const list = (preview?.employees || []).map((e) => ({ ...e, run: live.get(e.employee_id) || null }));
    // Someone paid this month who has since left still belongs on the sheet.
    const listed = new Set(list.map((r) => r.employee_id));
    for (const [employeeId, run] of live) {
      if (listed.has(employeeId)) continue;
      list.push({
        employee_id: employeeId, employee_name: run.employee_name || "Former employee",
        department: "Left the studio", salary_configured: true, monthly_salary: null,
        payable_days: run.breakdown?.payable_days ?? null, lop_days: run.breakdown?.lop_days ?? null,
        deduction: null, net_payable: run.net, run,
      });
    }
    return list;
  }, [preview, runs]);

  const totals = useMemo(() => {
    const paid = rows.filter((r) => r.run);
    const unpaid = rows.filter((r) => !r.run && r.salary_configured);
    return {
      payable: rows.reduce((s, r) => s + Number((r.run ? r.run.net : r.net_payable) || 0), 0),
      paidCount: paid.length,
      paidAmount: paid.reduce((s, r) => s + Number(r.run.net || 0), 0),
      unpaidCount: unpaid.length,
      unpaidAmount: unpaid.reduce((s, r) => s + Number(r.net_payable || 0), 0),
      notSet: rows.filter((r) => !r.run && !r.salary_configured).length,
    };
  }, [rows]);

  const visible = useMemo(() => {
    const s = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (show === "paid" && !r.run) return false;
      if (show === "unpaid" && r.run) return false;
      if (!s) return true;
      return [r.employee_name, r.employee_code, r.department].filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(s));
    });
  }, [rows, q, show]);

  const monthLabel = `${MONTH_NAMES[ym.m - 1]} ${ym.y}`;
  const openSlip = (row) => setSlip({
    path: salarySlipPath(row.run),
    title: `Salary slip · ${row.employee_name} · ${monthLabel}`,
    filename: `salary_slip_${(row.employee_code || row.employee_name || "employee").replace(/\s+/g, "_")}_${ym.y}_${String(ym.m).padStart(2, "0")}.pdf`,
  });
  const openPreviewSlip = (row) => setSlip({
    path: `/payroll/payslip.pdf?employee_id=${encodeURIComponent(row.employee_id)}&year=${ym.y}&month=${ym.m}`,
    title: `Salary working · ${row.employee_name} · ${monthLabel}`,
    filename: `payslip_${row.employee_id}_${ym.y}_${String(ym.m).padStart(2, "0")}.pdf`,
  });
  const edit = async (row) => { if (await editSalaryRun(row.run)) load(); };
  const cancel = async (row) => { if (await cancelSalaryRun(row.run)) load(); };

  return (
    <div className="space-y-6" data-testid="payroll-page">
      <PageHero
        title="Payroll"
        count={loading ? undefined : rows.length}
        kicker="Pay each person's salary for the month. Every payment posts to Accounting and gives a salary slip."
      >
        <div className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-white p-0.5" data-testid="payroll-month">
          <button type="button" className="btn-icon !w-8 !h-8" onClick={() => shiftMonth(-1)} aria-label="Previous month" data-testid="payroll-prev-month">
            <CaretLeft size={16} />
          </button>
          <label className="relative">
            <span className="sr-only">Month</span>
            <input type="month" className="input-flat !h-8 !border-0 !w-[190px] text-sm font-semibold text-center bg-transparent"
                   value={`${ym.y}-${String(ym.m).padStart(2, "0")}`}
                   onChange={(e) => { const [y, m] = e.target.value.split("-").map(Number); if (y && m) setMonth({ y, m }); }}
                   data-testid="payroll-month-input" />
          </label>
          <button type="button" className="btn-icon !w-8 !h-8" onClick={() => shiftMonth(1)} aria-label="Next month" data-testid="payroll-next-month">
            <CaretRight size={16} />
          </button>
        </div>
        {!isThisMonth && (
          <button type="button" className="btn-ghost text-xs" onClick={() => setMonth(currentMonth())} data-testid="payroll-this-month">
            This month
          </button>
        )}
      </PageHero>

      {/* Month summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="payroll-summary">
        <SummaryTile label={`Payable for ${MONTH_NAMES[ym.m - 1]}`} value={loading ? null : inr(totals.payable)}
                     hint={loading ? "" : `${rows.length} employee${rows.length === 1 ? "" : "s"}`} testid="payroll-total-net" />
        <SummaryTile label="Paid" value={loading ? null : inr(totals.paidAmount)} tone="success"
                     hint={loading ? "" : `${totals.paidCount} paid`} testid="payroll-total-paid" />
        <SummaryTile label="Still to pay" value={loading ? null : inr(totals.unpaidAmount)} tone={totals.unpaidCount ? "warning" : undefined}
                     hint={loading ? "" : `${totals.unpaidCount} to pay`} testid="payroll-total-unpaid" />
        <SummaryTile label="Salary not set" value={loading ? null : String(totals.notSet)} tone={totals.notSet ? "danger" : undefined}
                     hint={totals.notSet ? "Set it on the employee profile" : "Everyone has a salary"} testid="payroll-not-set" />
      </div>

      {totals.notSet > 0 && !loading && (
        <div className="rounded-lg border border-[var(--warning)] bg-[var(--warning-soft)] px-4 py-3 text-sm text-[var(--warning)] flex items-start gap-2" data-testid="payroll-unconfigured-warning">
          <Warning size={16} className="shrink-0 mt-0.5" />
          <span>
            <b>{totals.notSet}</b> employee{totals.notSet === 1 ? " has" : "s have"} no salary, so their net shows ₹0.
            Set the salary on the employee profile (Salary &amp; Bank), or a flat monthly salary in{" "}
            <Link to="/attendance?tab=settings" className="underline underline-offset-2">Attendance → Settings</Link>.
          </span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2" data-testid="payroll-toolbar">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, code or department"
                 className="input-flat !pl-9 w-full" aria-label="Search employees" data-testid="payroll-search" />
        </div>
        <div className="flex rounded-lg border border-[var(--line)] bg-[var(--surface-2)] p-0.5" role="group" aria-label="Show">
          {[["all", "All", rows.length], ["unpaid", "To pay", rows.filter((r) => !r.run).length], ["paid", "Paid", totals.paidCount]].map(([id, label, n]) => (
            <button key={id} type="button" aria-pressed={show === id} onClick={() => setShow(id)}
                    className={`px-3 h-8 rounded-md text-xs font-semibold transition-colors ${show === id
                      ? "bg-white text-[var(--ink)] shadow-[0_1px_2px_rgba(17,17,17,0.06)]" : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}
                    data-testid={`payroll-show-${id}`}>
              {label} <span className="font-normal text-[var(--ink-3)] tabular">{loading ? "" : n}</span>
            </button>
          ))}
        </div>
      </div>

      {failed ? (
        <div className="card-flat text-sm text-[var(--danger)] flex items-center justify-between gap-3" role="alert" data-testid="payroll-error">
          <span>{failed}</span>
          <button type="button" className="btn-ghost text-xs" onClick={load}>Try again</button>
        </div>
      ) : (
        <div className="card-flat !p-0 overflow-x-auto table-scroll">
          <table className="w-full text-sm min-w-[760px]" data-testid="payroll-table">
            <thead className="text-left text-[11px] font-semibold text-[var(--ink-2)] bg-[var(--surface-2)] border-b border-[var(--line)]">
              <tr>
                <th className="px-4 py-2.5">Employee</th>
                <th className="px-3 py-2.5 text-right">Salary</th>
                <th className="px-3 py-2.5 text-center">Paid days</th>
                <th className="px-3 py-2.5 text-right">Deductions</th>
                <th className="px-3 py-2.5 text-right">Net payable</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {loading && <SkeletonRows cols={7} />}
              {!loading && rows.length === 0 && (
                <EmptyRow cols={7} icon={UserCircle} title="No employees yet"
                          hint="Add employees first; their salaries show here every month." testid="payroll-empty" />
              )}
              {!loading && rows.length > 0 && visible.length === 0 && (
                <EmptyRow cols={7} icon={MagnifyingGlass} title="No one matches"
                          hint="Clear the search or show everyone." testid="payroll-no-match" />
              )}
              {!loading && visible.map((r) => {
                const run = r.run;
                const notSet = !run && !r.salary_configured;
                const deduction = Number(r.deduction || 0);
                return (
                  <tr key={r.employee_id} className="border-t border-[var(--line-soft)] hover:bg-[var(--surface-2)]" data-testid={`payroll-row-${r.employee_id}`}>
                    <td className="px-4 py-3">
                      <Link to={`/employees/${r.employee_id}`} className="font-semibold text-[var(--ink)] hover:underline underline-offset-2">
                        {r.employee_name}
                      </Link>
                      <div className="text-[11px] text-[var(--ink-3)]">
                        {[r.employee_code, r.department].filter(Boolean).join(" · ") || "Staff"}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right tabular text-xs">
                      {r.monthly_salary == null ? "—" : r.salary_configured ? inr(r.monthly_salary)
                        : <span className="text-[var(--warning)] font-semibold" data-testid={`salary-not-set-${r.employee_id}`}>Not set</span>}
                    </td>
                    <td className="px-3 py-3 text-center tabular text-xs">
                      {r.payable_days == null ? "—" : r.payable_days}
                      {Number(r.lop_days) > 0 && <div className="text-[10px] text-[var(--danger)]">{r.lop_days} loss of pay</div>}
                      {Number(r.auto_paid_leave) > 0 && <div className="text-[10px]" style={{ color: "#1a7f5a" }}>{r.auto_paid_leave} auto paid leave</div>}
                    </td>
                    <td className={`px-3 py-3 text-right tabular text-xs ${deduction > 0 ? "text-[var(--danger)]" : "text-[var(--ink-3)]"}`}>
                      {r.deduction == null ? "—" : deduction > 0 ? `−${inr(deduction)}` : "—"}
                    </td>
                    <td className="px-3 py-3 text-right tabular font-semibold" data-testid={`net-${r.employee_id}`}>
                      {inr(run ? run.net : r.net_payable)}
                      {run && Number(run.net) !== Number(r.net_payable) && r.net_payable != null && (
                        <div className="text-[10px] font-normal text-[var(--ink-3)]">paid amount</div>
                      )}
                    </td>
                    <td className="px-3 py-3" data-testid={`payroll-status-${r.employee_id}`}>
                      {run ? (
                        <span className="status-chip chip-paid" title={run.paid_from_account_name ? `From ${run.paid_from_account_name}` : undefined}>
                          {run.status === "processing" ? "Processing" : `Paid ${formatDate(run.payment_date || run.paid_at)}`}
                        </span>
                      ) : notSet ? (
                        <span className="status-chip chip-overdue">Salary not set</span>
                      ) : (
                        <span className="status-chip chip-pending">To pay</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {run ? (
                          <button type="button" className="btn-ghost text-xs" onClick={() => openSlip(r)} disabled={run.status !== "paid"}
                                  data-testid={`payroll-slip-${r.employee_id}`}>
                            <FileText size={14} /> Slip
                          </button>
                        ) : canPay && !notSet ? (
                          <button type="button" className="btn-primary text-xs !h-8" onClick={() => setPaying(r)}
                                  data-testid={`payroll-pay-${r.employee_id}`}>
                            <Money size={14} /> Pay
                          </button>
                        ) : null}
                        <RowActions label={`${r.employee_name} salary`} testid={`payroll-actions-${r.employee_id}`} actions={[
                          { label: "Pay salary", icon: Money, hidden: !canPay || !!run || notSet, onSelect: () => setPaying(r) },
                          { label: "Salary slip (PDF)", icon: FileText, hidden: run?.status !== "paid", onSelect: () => openSlip(r) },
                          { label: "Salary working (PDF)", icon: FileText, hidden: !!run, onSelect: () => openPreviewSlip(r) },
                          { label: "Edit payment", icon: PencilSimple, hidden: !canCorrect || run?.status !== "paid",
                            onSelect: () => edit(r), testid: `payroll-edit-${r.employee_id}` },
                          { label: "Open employee", icon: UserCircle, onSelect: () => navigate(`/employees/${r.employee_id}`) },
                          { label: "Cancel payment", icon: ClockCounterClockwise, danger: true, divider: true,
                            hidden: !canCorrect || run?.status !== "paid", onSelect: () => cancel(r), testid: `payroll-cancel-${r.employee_id}` },
                        ]} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-[var(--ink-3)]">
        Net payable = monthly salary − loss of pay, late fines and short leave, from{" "}
        <Link to="/attendance?tab=monthly" className="underline underline-offset-2">attendance</Link>.
        Bonus, advance recovery and other deductions are added when you pay.
      </p>

      {paying && (
        <PayDialog row={paying} ym={ym} monthLabel={monthLabel}
                   onClose={() => setPaying(null)}
                   onPaid={(run) => {
                     toast.success(`${paying.employee_name}: ${inr(run.net)} paid for ${monthLabel}`);
                     setPaying(null);
                     load();
                   }} />
      )}
      {slip && <PdfPreviewModal path={slip.path} title={slip.title} filename={slip.filename} onClose={() => setSlip(null)} />}
    </div>
  );
}

function SummaryTile({ label, value, hint, tone, testid }) {
  const color = tone === "success" ? "var(--success)" : tone === "warning" ? "var(--warning)"
    : tone === "danger" ? "var(--danger)" : "var(--ink)";
  return (
    <div className="card-flat" data-testid={testid}>
      <div className="text-xs font-medium text-[var(--ink-2)]">{label}</div>
      {value == null
        ? <div className="skeleton h-7 w-24 rounded mt-1.5" />
        : <div className="font-display font-bold text-2xl tabular mt-1" style={{ color }}>{value}</div>}
      {hint && <div className="text-[11px] text-[var(--ink-3)] mt-0.5">{hint}</div>}
    </div>
  );
}

function PayDialog({ row, ym, monthLabel, onClose, onPaid }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="fixed inset-0 bg-black/40 z-50 flex items-start sm:items-center justify-center p-2 sm:p-6 overflow-y-auto"
         role="dialog" aria-modal="true" aria-labelledby="pay-dialog-title" data-testid="payroll-pay-dialog">
      <div className="bg-white border border-[var(--line)] rounded-xl w-full max-w-4xl p-5 my-auto shadow-2xl">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <div className="text-xs font-medium text-[var(--ink-3)]">Pay salary · {monthLabel}</div>
            <h2 id="pay-dialog-title" className="font-display font-bold text-2xl">{row.employee_name}</h2>
            <div className="text-xs text-[var(--ink-2)] mt-0.5">Posts the salary to Accounting and creates the salary slip.</div>
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close" data-testid="payroll-pay-close"><X size={18} /></button>
        </div>
        <PaySalaryBlock employeeId={row.employee_id} netMonthly={row.net_payable}
                        initialYear={ym.y} initialMonth={ym.m} fixedPeriod bare onPaid={onPaid} />
      </div>
    </div>,
    document.body,
  );
}
