import { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import {
  Receipt, Plus, Warning, Check, X, ArrowsClockwise, CurrencyInr, ThumbsUp, ThumbsDown, Wallet,
} from "@phosphor-icons/react";

const fmtMoney = (n) => "₹" + (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}

const STATUS_TONE = {
  draft: "bg-[#F0F0F0] text-[#5C5C5C]",
  pending_l1: "bg-[#FFF4E5] text-[#7A4E1A]",
  pending_l2: "bg-[#FFF4E5] text-[#7A4E1A]",
  receipt_required: "bg-[#FFF4E5] text-[#B87500]",
  approved: "bg-[#F5F4F0] text-[#8B7F6A]",
  rejected: "bg-[#FCEEEC] text-[#B22B22]",
  reimbursed: "bg-[#EFF7EF] text-[#1D633E]",
};

export default function Expenses() {
  const { user, hasPerm } = useAuth();
  const [tab, setTab] = useState("all");
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const isAdmin = hasPerm("*.*");
  const isFinance = hasPerm("finance.create");

  const load = async () => {
    setLoading(true);
    try {
      const params = tab === "mine" ? { mine: true } : (tab === "approvals" ? { status: "pending_l1,pending_l2" } : {});
      const [e, s, a] = await Promise.all([
        api.get("/expenses", { params }),
        api.get("/expenses/summary/dashboard"),
        api.get("/accounts?type=asset"),
      ]);
      let rows = e.data;
      if (tab === "approvals") {
        // filter to expenses awaiting my role's decision (or any if admin)
        rows = rows.filter((x) => ["pending_l1", "pending_l2"].includes(x.status) &&
          (isAdmin || x.pending_approver_role === user?.role));
      }
      setExpenses(rows); setSummary(s.data);
      setAccounts(a.data.filter((x) => x.is_bank || ["Cash", "Bank - Primary", "Petty Cash"].includes(x.name)));
    } catch (ex) { setErr(fmtErr(ex?.response?.data?.detail)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tab]);

  if (loading) return <div className="skeleton h-96"></div>;

  return (
    <div className="space-y-6" data-testid="expenses-page">
      <PageHero eyebrow="FINANCE / EXPENSES"
        title="From claim to reimbursement, in minutes."
        kicker="Policy-based routing, multi-level approval, auto-JE on payout."
        count={expenses.length}>
        <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="new-expense-btn">
          <Plus size={13}/> New expense
        </button>
      </PageHero>

      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] p-3 text-sm text-[#B22B22]"><Warning size={13} className="inline mr-1"/>{err}</div>}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI label="PENDING APPROVAL" value={summary.pending} tone="#B87500" />
          <KPI label="APPROVED · TO PAY" value={summary.approved} tone="#8B7F6A" />
          <KPI label="REIMBURSED · MONTH" value={summary.reimbursed_this_month} tone="#1D633E" />
          <KPI label="MY PENDING" value={summary.my_pending} tone="#7A4E1A" />
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[#E5E5E5]">
        {[["all","All"],["mine","My Expenses"],["approvals","Awaiting My Approval"]].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm border-b-2 ${tab === k ? "border-[#8B7F6A] text-[#8B7F6A] font-semibold" : "border-transparent text-[#5C5C5C]"}`}
            data-testid={`tab-${k}`}>
            {l}
          </button>
        ))}
      </div>

      <div className="card-flat p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px]" data-testid="expenses-table">
            <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]"><tr className="text-left">
              <Th>Title</Th><Th>Claimant</Th><Th>Total</Th><Th>Status</Th><Th>Next Approver</Th><Th>Date</Th>
            </tr></thead>
            <tbody>
              {expenses.map((e) => (
                <tr key={e.id} onClick={() => setDetail(e.id)} className="row-hover border-b border-[#F0F0F0] cursor-pointer" data-testid={`exp-row-${e.id}`}>
                  <Td className="font-semibold text-sm">{e.title}</Td>
                  <Td className="text-xs">{e.claimant_name}</Td>
                  <Td className="font-mono">{fmtMoney(e.total)}</Td>
                  <Td><span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${STATUS_TONE[e.status]}`}>{e.status}</span></Td>
                  <Td className="text-xs">{e.pending_approver_role || "—"}</Td>
                  <Td className="font-mono text-xs">{(e.created_at || "").slice(0,10)}</Td>
                </tr>
              ))}
              {expenses.length === 0 && <tr><td colSpan={6} className="p-12 text-center text-[#5C5C5C]">No expenses yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && <CreateExpense accounts={accounts} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {detail && <ExpenseDetail expId={detail} accounts={accounts} isAdmin={isAdmin} isFinance={isFinance} userRole={user?.role} onClose={() => setDetail(null)} onChange={load} />}
    </div>
  );
}

function KPI({ label, value, tone }) {
  return (
    <div className="card-flat p-4 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: tone }} />
      <div className="overline text-[10px] text-[#5C5C5C] mb-1">{label}</div>
      <div className="font-display font-bold tracking-tighter text-3xl tabular-nums">{value ?? "—"}</div>
    </div>
  );
}

const CATEGORIES = ["travel","meals","materials","utilities","site","office","other"];

function CreateExpense({ accounts, onClose, onCreated }) {
  const [f, setF] = useState({
    title: "", payment_mode: "personal", notes: "",
    lines: [{ category: "travel", amount: 0, description: "", receipt_url: "", tax_rate: 0 }],
  });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const total = f.lines.reduce((s, l) => s + Number(l.amount || 0) + Number(l.amount || 0) * Number(l.tax_rate || 0)/100, 0);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api.post("/expenses", f);
      onCreated();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Submit failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title="Submit Expense Claim" eyebrow="NEW CLAIM" wide>
      <form onSubmit={submit} className="space-y-4" data-testid="exp-create-form">
        <F label="Title *"><input required data-testid="exp-title" className="input-flat w-full" value={f.title} onChange={(e) => setF({...f, title: e.target.value})} /></F>
        <F label="Payment mode">
          <select className="input-flat w-full" value={f.payment_mode} onChange={(e) => setF({...f, payment_mode: e.target.value})}>
            <option value="personal">Paid personally (reimburse me)</option>
            <option value="cash">Company cash</option>
            <option value="corporate_card">Corporate card</option>
            <option value="bank_transfer">Bank transfer</option>
          </select>
        </F>

        <div className="overline">LINE ITEMS</div>
        {f.lines.map((l, i) => (
          <div key={i} className="grid grid-cols-12 gap-2 items-center" data-testid={`exp-line-${i}`}>
            <select className="input-flat col-span-2" value={l.category} onChange={(e) => setF((s) => ({...s, lines: s.lines.map((x,j) => j === i ? {...x, category: e.target.value} : x)}))}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input placeholder="Description" className="input-flat col-span-4" value={l.description} onChange={(e) => setF((s) => ({...s, lines: s.lines.map((x,j) => j === i ? {...x, description: e.target.value} : x)}))} />
            <input type="number" step="0.01" placeholder="Amount" className="input-flat col-span-2 font-mono" value={l.amount} onChange={(e) => setF((s) => ({...s, lines: s.lines.map((x,j) => j === i ? {...x, amount: Number(e.target.value)} : x)}))} />
            <input placeholder="Receipt URL" className="input-flat col-span-3" value={l.receipt_url} onChange={(e) => setF((s) => ({...s, lines: s.lines.map((x,j) => j === i ? {...x, receipt_url: e.target.value} : x)}))} />
            <button type="button" onClick={() => setF((s) => ({...s, lines: s.lines.filter((_,j) => j !== i)}))} className="btn-ghost col-span-1 text-[#B22B22]"><X size={12}/></button>
          </div>
        ))}
        <button type="button" onClick={() => setF((s) => ({...s, lines: [...s.lines, { category: "travel", amount: 0, description: "", receipt_url: "", tax_rate: 0 }]}))} className="btn-ghost text-xs"><Plus size={11}/> Add line</button>

        <F label="Notes"><textarea className="input-flat w-full h-16" value={f.notes} onChange={(e) => setF({...f, notes: e.target.value})} /></F>
        <div className="text-right font-mono font-bold text-lg accent-blue" data-testid="exp-total">Total: {fmtMoney(total)}</div>

        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy || !f.title} className="btn-primary" data-testid="exp-submit">{busy ? "Submitting…" : "Submit claim"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ExpenseDetail({ expId, accounts, isAdmin, isFinance, userRole, onClose, onChange }) {
  const [exp, setExp] = useState(null);
  const [comment, setComment] = useState("");
  const [payFrom, setPayFrom] = useState(accounts[0]?.id || "");
  const [busy, setBusy] = useState(""); const [err, setErr] = useState("");

  const load = async () => { try { const { data } = await api.get(`/expenses/${expId}`); setExp(data); } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); } };
  useEffect(() => { load(); }, [expId]);

  const decide = async (decision) => {
    setBusy(decision); setErr("");
    try {
      await api.post(`/expenses/${expId}/decision`, { decision, comment });
      setComment("");
      await load(); onChange && onChange();
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
    finally { setBusy(""); }
  };
  const reimburse = async () => {
    if (!payFrom) return;
    setBusy("reimburse"); setErr("");
    try {
      await api.post(`/expenses/${expId}/reimburse`, { paid_from_account_id: payFrom });
      await load(); onChange && onChange();
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
    finally { setBusy(""); }
  };

  if (!exp) return <Modal onClose={onClose} title="Loading…" wide><div className="skeleton h-64"/></Modal>;
  const canDecide = ["pending_l1","pending_l2"].includes(exp.status) && (isAdmin || exp.pending_approver_role === userRole);
  const canReimburse = exp.status === "approved" && isFinance;

  return (
    <Modal onClose={onClose} title={exp.title} eyebrow={`EXPENSE · ${exp.claimant_name}`} wide>
      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 mb-3">{err}</div>}

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <span className={`text-[10px] font-mono uppercase px-3 py-1 ${STATUS_TONE[exp.status]}`}>{exp.status}</span>
        {exp.pending_approver_role && <span className="text-xs text-[#5C5C5C]">Awaiting: <b>{exp.pending_approver_role}</b></span>}
        <span className="font-mono font-bold text-lg ml-auto accent-blue">{fmtMoney(exp.total)}</span>
      </div>

      <div className="overline mb-2">LINE ITEMS</div>
      <div className="border border-[#E5E5E5] mb-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]"><tr className="text-left">
            <Th>Category</Th><Th>Description</Th><Th>Amount</Th><Th>Receipt</Th>
          </tr></thead>
          <tbody>
            {exp.lines.map((l) => (
              <tr key={l.id} className="border-b border-[#F0F0F0]">
                <Td className="text-xs uppercase font-mono">{l.category}</Td>
                <Td>{l.description || "—"}</Td>
                <Td className="font-mono">{fmtMoney(l.amount)}</Td>
                <Td>{l.receipt_url ? <a href={l.receipt_url} target="_blank" rel="noreferrer" className="accent-blue text-xs">View</a> : <span className="text-[#9A9A9A]">—</span>}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {exp.approval_trail?.length > 0 && (
        <div className="mb-6">
          <div className="overline mb-2">APPROVAL TRAIL</div>
          <div className="space-y-2">
            {exp.approval_trail.map((t, i) => (
              <div key={i} className="border border-[#E5E5E5] p-2 text-xs">
                <div className="font-mono">{(t.at || "").slice(0,16)} · {t.actor_name || t.actor} ({t.actor_role || "system"})</div>
                <div><b>{t.decision}</b> {t.comment && `— ${t.comment}`}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {canDecide && (
        <div className="border border-[#E5E5E5] p-3 mb-4 bg-[#FAFAFA]">
          <div className="overline mb-2">MY DECISION</div>
          <textarea className="input-flat w-full h-16 mb-2" placeholder="Optional comment" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="dec-comment" />
          <div className="flex gap-2">
            <button disabled={busy === "approve"} onClick={() => decide("approve")} className="btn-primary text-xs" data-testid="approve-btn"><ThumbsUp size={12}/> Approve</button>
            <button disabled={busy === "reject"} onClick={() => decide("reject")} className="btn-ghost text-xs text-[#B22B22]" data-testid="reject-btn"><ThumbsDown size={12}/> Reject</button>
          </div>
        </div>
      )}

      {canReimburse && (
        <div className="border border-[#E5E5E5] p-3 bg-[#F5F4F0]">
          <div className="overline mb-2">REIMBURSE</div>
          <div className="flex flex-wrap gap-2 items-center">
            <select className="input-flat" value={payFrom} onChange={(e) => setPayFrom(e.target.value)} data-testid="pay-from">
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <button disabled={busy === "reimburse" || !payFrom} onClick={reimburse} className="btn-primary text-xs" data-testid="reimburse-btn">
              <Wallet size={12}/> {busy === "reimburse" ? "Posting…" : `Reimburse ${fmtMoney(exp.total)}`}
            </button>
          </div>
        </div>
      )}

      {exp.status === "reimbursed" && (
        <div className="border border-[#1D633E] bg-[#EFF7EF] p-3 text-sm text-[#1D633E]">
          <Check size={13} className="inline mr-1"/> Reimbursed on {(exp.reimbursed_at || "").slice(0,10)} · JE {exp.reimbursement_journal_id}
        </div>
      )}
    </Modal>
  );
}

function F({ label, children }) { return <label className="block"><div className="text-xs text-[#5C5C5C] mb-1">{label}</div>{children}</label>; }
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className={`bg-white p-6 w-full border border-[#E5E5E5] max-h-[92vh] overflow-y-auto ${wide ? "max-w-5xl" : "max-w-2xl"}`}>
        <div className="flex items-start justify-between mb-4">
          <div>{eyebrow && <div className="overline mb-1">{eyebrow}</div>}<div className="font-display font-bold tracking-tighter text-3xl">{title}</div></div>
          <button onClick={onClose} className="btn-ghost"><X size={13}/></button>
        </div>
        {children}
      </div>
    </div>
  );
}
const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm align-middle ${className}`}>{children}</td>;
