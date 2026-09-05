import { useEffect, useState } from "react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import {
  Bank, Plus, Warning, Check, CurrencyInr, CalendarBlank, X,
  ChartLineUp, TrendUp, PencilSimple,
} from "@phosphor-icons/react";

function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}
const fmtMoney = (n) => "₹" + (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const fmtDate = (d) => (d || "").slice(0, 10);

export default function Loans() {
  const [loans, setLoans] = useState([]);
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [l, s, a] = await Promise.all([
        api.get("/loans"),
        api.get("/loans/summary/dashboard"),
        api.get("/accounts?type=asset"),
      ]);
      setLoans(l.data);
      setSummary(s.data);
      setAccounts(a.data.filter((x) => x.is_bank || ["Cash", "Bank - Primary", "Petty Cash"].includes(x.name)));
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Failed to load"));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading) return <div className="skeleton h-96 w-full"></div>;

  return (
    <div className="space-y-8" data-testid="loans-page">
      <PageHero
        eyebrow="FINANCE / LOANS & EMI"
        title="Debt, on autopilot."
        kicker="Track every loan, auto-post EMIs, prepay smart — all reconciled with Accounting."
        count={loans.length}
      >
        <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="create-loan-btn">
          <Plus size={13}/> Add loan
        </button>
      </PageHero>

      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] p-3 text-sm text-[#B22B22]"><Warning size={13} className="inline mr-1"/>{err}</div>}

      {/* Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI icon={Bank} label="ACTIVE LOANS" value={summary.active_loans} tone="#8B7F6A" />
          <KPI icon={CurrencyInr} label="TOTAL OUTSTANDING" display={fmtMoney(summary.total_outstanding)} tone="#B22B22" />
          <KPI icon={CalendarBlank} label="NEXT EMI DUE" display={summary.next_emi_due_date || "—"} tone="#B87500" />
          <KPI icon={ChartLineUp} label="NEXT EMI AMOUNT" display={fmtMoney(summary.next_emi_amount)} tone="#1D633E" />
        </div>
      )}

      <div className="card-flat p-0 overflow-hidden">
        <div className="p-6 pb-4"><div className="overline">LOAN LEDGER · {loans.length}</div></div>
        <div className="overflow-x-auto">
        <div className="overflow-x-auto"><table className="w-full min-w-[900px]" data-testid="loans-table">
          <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]"><tr className="text-left">
            <Th>Lender</Th><Th>Type</Th><Th>Principal</Th><Th>Rate</Th>
            <Th>Tenure</Th><Th>EMI</Th><Th>Outstanding</Th><Th>Next Due</Th><Th>Status</Th>
          </tr></thead>
          <tbody>
            {loans.map((l) => (
              <tr key={l.id} className="row-hover border-b border-[#F0F0F0] cursor-pointer"
                  onClick={() => setDetail(l.id)} data-testid={`loan-row-${l.id}`}>
                <Td>
                  <div className="font-semibold text-sm">{l.lender_name}</div>
                  <div className="text-xs text-[#5C5C5C]">{l.account_number || "—"}</div>
                </Td>
                <Td><span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#F5F4F0] text-[#8B7F6A]">{l.loan_type}</span></Td>
                <Td className="font-mono text-sm">{fmtMoney(l.principal)}</Td>
                <Td className="font-mono text-sm">{l.interest_rate_pa}%</Td>
                <Td className="font-mono text-sm">{l.tenure_months}mo</Td>
                <Td className="font-mono text-sm accent-blue">{fmtMoney(l.emi_amount)}</Td>
                <Td className="font-mono text-sm text-[#B22B22]">{fmtMoney(l.outstanding)}</Td>
                <Td className="font-mono text-xs">{fmtDate(l.next_due_date)}</Td>
                <Td>
                  {l.status === "closed" ? (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#EFF7EF] text-[#1D633E]">closed</span>
                  ) : (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#FFF4E5] text-[#7A4E1A]">active</span>
                  )}
                </Td>
              </tr>
            ))}
            {loans.length === 0 && (
              <tr><td colSpan={9} className="p-12 text-center text-[#5C5C5C]">
                No loans yet. Click <em>Add loan</em> to record one.
              </td></tr>
            )}
          </tbody>
        </table></div>
        </div>
      </div>

      {showCreate && <CreateLoanModal accounts={accounts}
                       onClose={() => setShowCreate(false)}
                       onCreated={() => { setShowCreate(false); load(); }} />}
      {detail && <LoanDetailModal loanId={detail} accounts={accounts}
                    onClose={() => setDetail(null)} onChange={load} />}
    </div>
  );
}

function KPI({ icon: Icon, label, value, display, tone }) {
  return (
    <div className="card-flat p-5 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: tone }} />
      <Icon size={20} style={{ color: tone }} weight="duotone" />
      <div className="overline text-[10px] text-[#5C5C5C] mt-2">{label}</div>
      <div className="font-display font-bold tracking-tighter text-2xl tabular-nums">{display ?? value ?? "—"}</div>
    </div>
  );
}

function CreateLoanModal({ accounts, onClose, onCreated }) {
  const [f, setF] = useState({
    lender_name: "", loan_type: "business", principal: 500000, interest_rate_pa: 9.5,
    tenure_months: 36, start_date: new Date().toISOString().slice(0,10), emi_day: 5,
    disbursement_account_id: accounts[0]?.id || "", account_number: "", notes: "",
  });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);

  // Live EMI preview
  const emiPreview = (() => {
    const P = Number(f.principal), r = Number(f.interest_rate_pa)/12/100, n = Number(f.tenure_months);
    if (!P || !n) return 0;
    if (r <= 0) return P/n;
    return P * r * Math.pow(1+r, n) / (Math.pow(1+r, n) - 1);
  })();

  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      await api.post("/loans", f);
      onCreated();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title="Record New Loan" eyebrow="LOAN INTAKE">
      <form onSubmit={submit} className="space-y-3" data-testid="loan-create-form">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <F label="Lender name *"><input required data-testid="l-lender" className="input-flat w-full" value={f.lender_name} onChange={(e) => setF({...f, lender_name: e.target.value})} /></F>
          <F label="Loan type">
            <select className="input-flat w-full" value={f.loan_type} onChange={(e) => setF({...f, loan_type: e.target.value})}>
              <option value="business">Business</option>
              <option value="term">Term</option>
              <option value="equipment">Equipment</option>
              <option value="personal">Personal</option>
              <option value="other">Other</option>
            </select>
          </F>
          <F label="Principal amount *"><input required type="number" min="1" data-testid="l-principal" className="input-flat w-full font-mono" value={f.principal} onChange={(e) => setF({...f, principal: Number(e.target.value)})} /></F>
          <F label="Interest rate (% p.a.) *"><input required type="number" step="0.01" data-testid="l-rate" className="input-flat w-full font-mono" value={f.interest_rate_pa} onChange={(e) => setF({...f, interest_rate_pa: Number(e.target.value)})} /></F>
          <F label="Tenure (months) *"><input required type="number" min="1" data-testid="l-tenure" className="input-flat w-full font-mono" value={f.tenure_months} onChange={(e) => setF({...f, tenure_months: Number(e.target.value)})} /></F>
          <F label="Start date *"><input required type="date" className="input-flat w-full" value={f.start_date} onChange={(e) => setF({...f, start_date: e.target.value})} /></F>
          <F label="EMI day of month"><input type="number" min="1" max="31" className="input-flat w-full" value={f.emi_day} onChange={(e) => setF({...f, emi_day: Number(e.target.value)})} /></F>
          <F label="Disburse into (Bank) *">
            <select required data-testid="l-bank" className="input-flat w-full" value={f.disbursement_account_id} onChange={(e) => setF({...f, disbursement_account_id: e.target.value})}>
              <option value="">— Select —</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </F>
          <F label="Loan account #"><input className="input-flat w-full font-mono" value={f.account_number} onChange={(e) => setF({...f, account_number: e.target.value})} /></F>
        </div>
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-[#E5E5E5]">
          <div className="p-3 bg-[#F5F5F5]">
            <div className="overline text-[10px] mb-1">CALCULATED EMI</div>
            <div className="font-mono font-bold text-2xl accent-blue" data-testid="l-emi-preview">{fmtMoney(emiPreview.toFixed(2))}</div>
          </div>
          <div className="p-3 bg-[#F5F5F5]">
            <div className="overline text-[10px] mb-1">TOTAL PAYABLE</div>
            <div className="font-mono font-bold text-2xl">{fmtMoney((emiPreview * f.tenure_months).toFixed(2))}</div>
          </div>
        </div>
        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy || !f.lender_name || !f.disbursement_account_id} className="btn-primary" data-testid="l-submit">
            {busy ? "Recording…" : "Record loan"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function LoanDetailModal({ loanId, accounts, onClose, onChange }) {
  const [loan, setLoan] = useState(null);
  const [payFrom, setPayFrom] = useState(accounts[0]?.id || "");
  const [busyIdx, setBusyIdx] = useState(-1);
  const [err, setErr] = useState("");
  const [prepayAmt, setPrepayAmt] = useState("");

  const load = async () => {
    try { const { data } = await api.get(`/loans/${loanId}`); setLoan(data); }
    catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
  };
  useEffect(() => { load(); }, [loanId]);

  const payEMI = async (idx, extra = 0) => {
    setBusyIdx(idx); setErr("");
    try {
      await api.post(`/loans/${loanId}/pay-emi`, {
        schedule_index: idx, paid_from_account_id: payFrom, extra_principal: extra,
      });
      await load();
      onChange && onChange();
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Pay failed"));
    } finally { setBusyIdx(-1); }
  };

  const prepay = async () => {
    if (!prepayAmt || Number(prepayAmt) <= 0) return;
    try {
      await api.post(`/loans/${loanId}/prepay`, {
        amount: Number(prepayAmt), paid_from_account_id: payFrom,
      });
      setPrepayAmt("");
      await load();
      onChange && onChange();
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Prepay failed"));
    }
  };

  if (!loan) return <Modal onClose={onClose} title="Loading…" wide><div className="skeleton h-64"></div></Modal>;

  const t = loan.totals || {};
  return (
    <Modal onClose={onClose} title={loan.lender_name}
           eyebrow={`LOAN · ${loan.loan_type?.toUpperCase()} · ${loan.status?.toUpperCase()}`} wide>
      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 mb-3">{err}</div>}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <MiniStat label="Principal" value={fmtMoney(loan.principal)} />
        <MiniStat label="Rate" value={`${loan.interest_rate_pa}% p.a.`} />
        <MiniStat label="Tenure" value={`${loan.tenure_months}mo`} />
        <MiniStat label="EMI" value={fmtMoney(loan.emi_amount)} tone="#8B7F6A"/>
        <MiniStat label="Outstanding" value={fmtMoney(loan.outstanding)} tone="#B22B22"/>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6 text-xs">
        <div className="border border-[#E5E5E5] p-2">Principal paid: <b className="font-mono">{fmtMoney(t.principal_paid)}</b></div>
        <div className="border border-[#E5E5E5] p-2">Interest paid: <b className="font-mono">{fmtMoney(t.interest_paid)}</b></div>
        <div className="border border-[#E5E5E5] p-2">Principal pending: <b className="font-mono">{fmtMoney(t.principal_pending)}</b></div>
        <div className="border border-[#E5E5E5] p-2">Interest pending: <b className="font-mono">{fmtMoney(t.interest_pending)}</b></div>
      </div>

      {/* Pay controls */}
      <div className="flex flex-wrap items-end gap-3 mb-6 p-3 bg-[#FAFAFA] border border-[#E5E5E5]">
        <div className="flex-1 min-w-[220px]">
          <label className="overline text-[10px] mb-1 block">Pay from</label>
          <select className="input-flat w-full" value={payFrom} onChange={(e) => setPayFrom(e.target.value)}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div className="flex-1 min-w-[220px]">
          <label className="overline text-[10px] mb-1 block">Prepay amount</label>
          <div className="flex gap-2">
            <input type="number" className="input-flat flex-1 font-mono" value={prepayAmt}
                   placeholder="Lump-sum principal reduction"
                   onChange={(e) => setPrepayAmt(e.target.value)} data-testid="prepay-input" />
            <button onClick={prepay} disabled={!prepayAmt} className="btn-primary text-xs" data-testid="prepay-btn">
              <TrendUp size={12}/> Prepay
            </button>
          </div>
        </div>
      </div>

      {/* Schedule */}
      <div className="overline mb-2">AMORTIZATION SCHEDULE</div>
      <div className="max-h-[420px] overflow-y-auto border border-[#E5E5E5]">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] sticky top-0 border-b border-[#E5E5E5]">
            <tr className="text-left">
              <Th>#</Th><Th>Due date</Th><Th>Principal</Th><Th>Interest</Th>
              <Th>EMI</Th><Th>Balance</Th><Th>Status</Th><Th className="text-right">Action</Th>
            </tr>
          </thead>
          <tbody>
            {(loan.schedule || []).map((row) => (
              <tr key={row.index} className={`border-b border-[#F0F0F0] ${row.paid ? "opacity-60" : ""}`}
                  data-testid={`schedule-row-${row.index}`}>
                <Td className="font-mono text-xs">{row.index + 1}</Td>
                <Td className="font-mono text-xs">{row.due_date}</Td>
                <Td className="font-mono">{fmtMoney(row.principal)}</Td>
                <Td className="font-mono text-[#B22B22]">{fmtMoney(row.interest)}</Td>
                <Td className="font-mono font-semibold">{fmtMoney(row.emi)}</Td>
                <Td className="font-mono text-xs">{fmtMoney(row.balance_after)}</Td>
                <Td>
                  {row.paid ? (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#EFF7EF] text-[#1D633E]">
                      <Check size={9} className="inline"/> paid {fmtDate(row.paid_on)}
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 bg-[#FFF4E5] text-[#7A4E1A]">due</span>
                  )}
                </Td>
                <Td className="text-right">
                  {!row.paid && (
                    <button
                      disabled={busyIdx === row.index || !payFrom}
                      onClick={() => payEMI(row.index)}
                      className="btn-primary text-xs"
                      data-testid={`pay-emi-${row.index}`}
                    >
                      {busyIdx === row.index ? "…" : "Pay"}
                    </button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </Modal>
  );
}

function F({ label, children }) {
  return <label className="block"><div className="text-xs text-[#5C5C5C] mb-1">{label}</div>{children}</label>;
}
function MiniStat({ label, value, tone = "#0A0A0A" }) {
  return (
    <div className="border border-[#E5E5E5] p-3">
      <div className="overline text-[10px] mb-1">{label}</div>
      <div className="font-mono font-bold text-base" style={{ color: tone }}>{value}</div>
    </div>
  );
}
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className={`bg-white p-6 w-full border border-[#E5E5E5] max-h-[92vh] overflow-y-auto ${wide ? "max-w-6xl" : "max-w-2xl"}`}>
        <div className="flex items-start justify-between mb-4">
          <div>
            {eyebrow && <div className="overline mb-1">{eyebrow}</div>}
            <div className="font-display font-bold tracking-tighter text-3xl">{title}</div>
          </div>
          <button onClick={onClose} className="btn-ghost"><X size={13}/></button>
        </div>
        {children}
      </div>
    </div>
  );
}
const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm align-middle ${className}`}>{children}</td>;
