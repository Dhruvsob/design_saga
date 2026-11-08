import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "../lib/api";
import { dateForInput, formatDate, formatINR } from "../lib/format";
import { compatibleAccount, methodForAccount } from "../lib/cashbank";
import { askForm, confirmAction } from "../lib/confirm";
import SearchSelect from "./SearchSelect";

/**
 * Salary payment pieces shared by the employee profile (Salary & Bank) and the
 * Payroll page: the pay form, the "how this is calculated" working, and the
 * edit / cancel actions for a salary that was already paid.
 */

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmt = (n) => formatINR(n, { decimals: 0 });

export const salaryPeriod = (run) => `${MONTHS[(run.month || 1) - 1]} ${run.year}`;
export const salarySlipPath = (run) => `/payroll/runs/${run.id}/slip.pdf`;

async function cashAndBankAccounts() {
  const { data } = await api.get("/accounts?type=asset");
  return (data || []).filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name));
}

/** Cancel a paid salary (balanced reversal). Resolves true when it was cancelled. */
export async function cancelSalaryRun(run) {
  if (!await confirmAction(`Cancel the ${salaryPeriod(run)} salary of ${fmt(run.net)}? It is removed from the Daybook and this sheet (kept in the audit log), and the month can be paid again.`)) return false;
  try {
    await api.post(`/payroll/runs/${run.id}/reverse`);
    toast.success("Salary payment cancelled");
    return true;
  } catch (error) {
    toast.error(error?.response?.data?.detail || "Could not cancel salary payment");
    return false;
  }
}

/** Change what was actually paid for a salary. Resolves true when it was saved. */
export async function editSalaryRun(run) {
  let accounts = [];
  try {
    accounts = await cashAndBankAccounts();
  } catch { /* the dialog still opens; saving reports the problem */ }
  const values = await askForm({
    title: `Edit ${salaryPeriod(run)} salary`,
    body: "Change what was actually paid. The old entry is replaced everywhere: Daybook, ledgers, this sheet and the salary slip.",
    fields: [
      { name: "net", label: "Amount paid (₹)", type: "number", required: true, defaultValue: String(run.net ?? "") },
      { name: "bonus", label: "Of which bonus (₹)", type: "number", defaultValue: run.extras?.bonus ? String(run.extras.bonus) : "",
        hint: "Shown as Bonus on the salary slip, e.g. Diwali bonus." },
      { name: "payment_date", label: "Paid on", type: "date", required: true,
        defaultValue: dateForInput(run.payment_date || run.paid_at) },
      { name: "paid_from_account_id", label: "Paid from", required: true,
        defaultValue: run.paid_from_account_id || accounts[0]?.id || "",
        options: accounts.map((a) => ({ value: a.id, label: a.name })) },
      { name: "reference", label: "Reference (optional)", defaultValue: run.reference || "", placeholder: "UTR / cheque / voucher" },
    ],
    confirmLabel: "Save payment",
  });
  if (!values) return false;
  const account = accounts.find((a) => a.id === values.paid_from_account_id);
  const method = methodForAccount(account);
  const keepMethod = method !== "cash" && run.payment_method && run.payment_method !== "cash";
  try {
    await api.post(`/payroll/runs/${run.id}/correct`, {
      net: Number(values.net), bonus: values.bonus === "" ? 0 : Number(values.bonus),
      payment_date: values.payment_date, paid_from_account_id: values.paid_from_account_id,
      payment_method: keepMethod ? run.payment_method : method,
      reference: values.reference || null,
    });
    toast.success(`${salaryPeriod(run)} salary saved as ${fmt(Number(values.net))}`);
    return true;
  } catch (error) {
    toast.error(error?.response?.data?.detail || "Could not update salary payment");
    return false;
  }
}

/**
 * Pay one employee's salary for a month; posts the journal to Accounting.
 * `fixedPeriod` hides the month picker (the Payroll page has already chosen it);
 * `onPaid(run)` lets the caller refresh its list.
 */
export function PaySalaryBlock({
  employeeId, netMonthly, advanceVersion = 0,
  initialYear, initialMonth, fixedPeriod = false, onPaid, bare = false,
}) {
  const [advance, setAdvance] = useState({ outstanding: 0, suggested_recovery: 0 });
  const [todayYear, todayMonth] = dateForInput(new Date()).split("-").map(Number);
  const [year, setYear] = useState(initialYear || todayYear);
  const [month, setMonth] = useState(initialMonth || todayMonth);
  const [preview, setPreview] = useState(null);
  const [banks, setBanks] = useState([]);
  const [bankAccountId, setBankAccountId] = useState("");
  const [paymentDate, setPaymentDate] = useState(dateForInput(new Date()));
  const [paymentMethod, setPaymentMethod] = useState("bank_transfer");
  const [reference, setReference] = useState("");
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
      api.get(`/employees/${employeeId}/advances`).then(({ data: a }) => setAdvance(a)).catch(() => {});
      const cash = (accs || []).filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name));
      setBanks(cash);
      if (!bankAccountId && cash.length) {
        setBankAccountId(cash[0].id);
        setPaymentMethod(methodForAccount(cash[0]));
      }
    } catch (e) {
      setMsg(e?.response?.data?.detail || "Failed to load preview (need finance.read)");
    }
  }, [employeeId, year, month, extras, advanceVersion]);

  useEffect(() => { load(); }, [load]);

  const pay = async () => {
    setBusy(true); setMsg("");
    try {
      const { data } = await api.post(`/employees/${employeeId}/pay-salary`, {
        year, month, paid_from_account_id: bankAccountId,
        payment_date: paymentDate, payment_method: paymentMethod,
        reference, ...extras, notes,
      });
      setMsg(`✓ Paid ₹${data.run.net.toLocaleString("en-IN")} · JE ${data.journal.id}`);
      if (onPaid) onPaid(data.run);
      else load();
    } catch (e) {
      setMsg(e?.response?.data?.detail || "Payment failed");
    } finally { setBusy(false); }
  };

  const b = preview?.breakdown;
  const paid = preview?.already_paid;

  return (
    <div className={bare ? "" : "card-flat"} data-testid="pay-salary-block">
      {!bare && <div className="overline mb-4">RUN PAYROLL · posts to Accounting automatically</div>}
      <div className={`grid grid-cols-2 ${fixedPeriod ? "md:grid-cols-5" : "md:grid-cols-6"} gap-3 mb-4`}>
        {!fixedPeriod && (
          <>
            <label className="text-xs">
              <div className="overline mb-1">Year</div>
              <input type="number" min="2000" max="2100" className="input-flat w-full" value={year} onChange={(e) => setYear(Number(e.target.value))} />
            </label>
            <label className="text-xs">
              <div className="overline mb-1">Month</div>
              <select aria-label="Month" className="input-flat w-full" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </label>
          </>
        )}
        {["bonus", "incentives", "overtime", "advances_recovered", "other_deductions"].map((k) => (
          <label key={k} className="text-xs">
            <div className="overline mb-1">{k.replace(/_/g, " ")}</div>
            <input type="number" min="0" className="input-flat w-full text-right font-mono" value={extras[k]} onChange={(e) => setExtras({ ...extras, [k]: Number(e.target.value) || 0 })} data-testid={`extra-${k}`} />
            {k === "advances_recovered" && (
              advance.outstanding > 0 ? (
                <button type="button" className="mt-1 text-[11px] text-[var(--accent-strong)] underline"
                        onClick={() => setExtras({ ...extras, advances_recovered: advance.suggested_recovery || advance.outstanding })}
                        data-testid="use-suggested-recovery">
                  {fmt(advance.outstanding)} outstanding · use {fmt(advance.suggested_recovery || advance.outstanding)}
                </button>
              ) : <div className="mt-1 text-[11px] text-[var(--ink-3)]">No advance outstanding</div>
            )}
          </label>
        ))}
      </div>

      {b && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-sm">
          <StatBox label="Gross" value={fmt(b.gross)} />
          <StatBox label="Deductions" value={fmt(b.deductions_total)} tint="#B22B22" />
          <StatBox label="Additions" value={fmt(b.additions)} tint="#1D633E" />
          <StatBox label="Net payable" value={fmt(b.net)} tint="#8B7F6A" big />
        </div>
      )}
      {b && <SalaryWorking b={b} />}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs flex-1 min-w-[220px]">
          <div className="overline mb-1">Pay from</div>
          <SearchSelect className="input-flat w-full" value={bankAccountId} onChange={(e) => {
            const id = e.target.value;
            const account = banks.find((item) => item.id === id);
            setBankAccountId(id);
            setPaymentMethod(methodForAccount(account));
          }} data-testid="pay-from">
            {banks.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </SearchSelect>
        </label>
        <label className="text-xs min-w-[150px]">
          <div className="overline mb-1">Payment date</div>
          <input type="date" className="input-flat w-full" value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)} data-testid="salary-payment-date" />
        </label>
        {/* Cash is already said by "Pay from"; only a bank needs the how. */}
        {paymentMethod !== "cash" && (
          <label className="text-xs min-w-[170px]">
            <div className="overline mb-1">Paid by</div>
            <select aria-label="Payment method" className="input-flat w-full" value={paymentMethod}
              onChange={(e) => {
                const method = e.target.value;
                setPaymentMethod(method);
                const compatible = compatibleAccount(banks, method);
                if (compatible) setBankAccountId(compatible.id);
              }} data-testid="salary-payment-method">
              <option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option>
              <option value="cheque">Cheque</option><option value="online">Online</option>
              <option value="other">Other</option>
            </select>
          </label>
        )}
        <label className="text-xs flex-1 min-w-[180px]">
          <div className="overline mb-1">Reference</div>
          <input className="input-flat w-full" value={reference} onChange={(e) => setReference(e.target.value)}
            placeholder="UTR / cheque / voucher" data-testid="salary-payment-reference" />
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
      {msg && <div className="mt-3 text-sm text-[var(--accent-strong)]" data-testid="pay-msg">{msg}</div>}
      {paid && (
        <div className="mt-2 flex items-center justify-between gap-3" data-testid="paid-badge">
          <div className="text-xs text-[var(--ink-2)] font-mono">
            PAID ON {formatDate(paid.paid_at)} · NET {fmt(paid.net)} · Run {paid.id}
          </div>
          <a
            href={`${api.defaults.baseURL}${salarySlipPath(paid)}`}
            target="_blank" rel="noreferrer"
            className="btn-ghost text-xs"
            data-testid="download-slip-btn"
          >
            📄 Download salary slip
          </a>
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, tint = "#0A0A0A", big }) {
  return (
    <div className="border border-[var(--line)] p-3">
      <div className="overline">{label}</div>
      <div className={`font-mono font-bold ${big ? "text-2xl" : "text-lg"}`} style={{ color: tint }}>{value}</div>
    </div>
  );
}

/** "How this is calculated": formula inputs and a reason for every deduction. */
function SalaryWorking({ b }) {
  const sum = b.attendance_summary || {};
  const lines = b.deduction_lines || [];
  const money = (n) => formatINR(n, { decimals: 2 });
  const counts = [
    ["Present", sum.present], ["Late", sum.late], ["Half day", sum.half_day], ["Paid leave", sum.paid_leave],
    ["Unpaid leave", sum.unpaid_leave], ["Absent", sum.absent], ["Weekly off", sum.week_off], ["Holiday", sum.holidays],
  ].filter(([, v]) => Number(v) > 0);
  return (
    <details className="mb-4 border border-[var(--line)] rounded-lg bg-[var(--surface-2)]" data-testid="salary-working">
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold flex items-center justify-between gap-3">
        <span>How this is calculated</span>
        <span className="text-xs font-normal text-[var(--ink-2)]">
          {b.per_day_rate ? `${money(b.per_day_rate)} per day · ${b.basis_days}-day basis` : "Salary structure"}
        </span>
      </summary>
      <div className="px-4 pb-4 space-y-4 text-sm">
        {b.per_day_rate > 0 && (
          <p className="text-[var(--ink-2)]">
            Per-day rate = monthly salary {money(b.monthly_salary_used || b.basic)} ÷ {b.basis_days} days
            = <strong className="text-[var(--ink)]">{money(b.per_day_rate)}</strong>.
            Paid days this month: <strong className="text-[var(--ink)]">{b.payable_days}</strong>
            {Number(b.lop_days) > 0 && <> · loss-of-pay days: <strong className="text-[var(--danger)]">{b.lop_days}</strong></>}.
            {Number(b.monthly_paid_leave_allowance) > 0 && <> {b.paid_leave_allowance_used || 0} of {b.monthly_paid_leave_allowance} paid leave(s) used.</>}
          </p>
        )}
        {counts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {counts.map(([k, v]) => (
              <span key={k} className="text-xs px-2 py-1 rounded bg-white border border-[var(--line)]">{k}: <strong>{v}</strong></span>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1">
          <Item label="Gross earnings" value={money(b.gross)} />
          {Number(b.additions) > 0 && <Item label="Additions (bonus, incentives, overtime)" value={`+ ${money(b.additions)}`} good />}
          {Number(b.lop_deduction) > 0 && <Item label={`Loss of pay (${b.lop_days} day${b.lop_days === 1 ? "" : "s"})`} value={`− ${money(b.lop_deduction)}`} bad />}
          {Number(b.late_fine) > 0 && <Item label="Late fines" value={`− ${money(b.late_fine)}`} bad />}
          {Number(b.short_leave_deduction) > 0 && <Item label={`Short leave (${b.short_leave_hours} h)`} value={`− ${money(b.short_leave_deduction)}`} bad />}
          {Number(b.advances_recovered) > 0 && <Item label="Advance recovered" value={`− ${money(b.advances_recovered)}`} bad />}
          {Number(b.other_deductions) > 0 && <Item label="Other deductions" value={`− ${money(b.other_deductions)}`} bad />}
          <Item label="Net payable" value={money(b.net)} strong />
        </div>
        {lines.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-[var(--ink-2)] border-b border-[var(--line)]">
                <th className="py-1.5 pr-3 font-semibold">Date</th><th className="py-1.5 pr-3 font-semibold">Reason</th>
                <th className="py-1.5 text-right font-semibold">Deducted</th>
              </tr></thead>
              <tbody>
                {lines.map((l, i) => (
                  <tr key={`${l.date}-${l.kind}-${i}`} className="border-b border-[var(--line-soft)]">
                    <td className="py-1.5 pr-3 font-mono whitespace-nowrap">{formatDate(l.date)}</td>
                    <td className="py-1.5 pr-3">{l.reason}</td>
                    <td className="py-1.5 text-right font-mono text-[var(--danger)]">− {money(l.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-[11px] text-[var(--ink-3)] mt-2">Day-wise reasons come from attendance. Fix a wrong day in Attendance and the amount updates here.</p>
          </div>
        ) : (
          <p className="text-xs text-[var(--success)]">No attendance deductions this month.</p>
        )}
      </div>
    </details>
  );
}

function Item({ label, value, good, bad, strong }) {
  return (
    <div className={`flex justify-between gap-3 py-1 ${strong ? "border-t border-[var(--line)] mt-1 pt-2 font-semibold" : ""}`}>
      <span className="text-[var(--ink-2)]">{label}</span>
      <span className={`font-mono ${good ? "text-[var(--success)]" : bad ? "text-[var(--danger)]" : "text-[var(--ink)]"}`}>{value}</span>
    </div>
  );
}
