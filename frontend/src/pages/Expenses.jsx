import { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import { safeExternalUrl } from "../lib/url";
import { formatDate } from "../lib/format";
import {
  Receipt, Plus, Warning, Check, X, ArrowsClockwise, CurrencyInr, ThumbsUp, ThumbsDown, Wallet,
  PencilSimple, Trash,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import { SkeletonRows, EmptyRow } from "../components/TableState";

const fmtMoney = (n) => "₹" + (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}

const STATUS_TONE = {
  draft: "bg-[var(--line-soft)] text-[var(--ink-2)]",
  pending_l1: "bg-[var(--warning-soft)] text-[var(--warning)]",
  pending_l2: "bg-[var(--warning-soft)] text-[var(--warning)]",
  receipt_required: "bg-[var(--warning-soft)] text-[var(--warning)]",
  approved: "bg-[var(--hover)] text-[#5F5A4B]",
  rejected: "bg-[var(--danger-soft)] text-[var(--danger)]",
  reimbursed: "bg-[var(--success-soft)] text-[var(--success)]",
  cancelled: "bg-[var(--line-soft)] text-[var(--ink-2)]",
};

export default function Expenses() {
  const { user, hasPerm } = useAuth();
  const [tab, setTab] = useState("all");
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editExpense, setEditExpense] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const isAdmin = hasPerm("*.*");
  const isFinance = hasPerm("finance.create");
  const canCreate = hasPerm("expenses.create");
  const canManage = hasPerm("expenses.update");
  const canDeletePosted = hasPerm("finance.delete");

  const load = async () => {
    setLoading(true);
    try {
      const params = tab === "mine" ? { mine: true } : (tab === "approvals" ? { status: "pending_l1,pending_l2" } : {});
      const [e, s, a] = await Promise.all([
        api.get("/expenses", { params }),
        api.get("/expenses/summary/dashboard"),
        isFinance ? api.get("/accounts?type=asset") : Promise.resolve({ data: [] }),
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
      <PageHero eyebrow="FINANCE / STAFF EXPENSE CLAIMS"
        title="Expense claims"
        kicker="For staff reimbursement claims that need approval. For direct company expenses (rent, tea, salary etc.), use Accounting → Expense."
        count={expenses.length}>
        {canCreate && <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="new-expense-btn">
          <Plus size={13}/> New claim
        </button>}
      </PageHero>

      {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]"><Warning size={13} className="inline mr-1"/>{err}</div>}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI label="PENDING APPROVAL" value={summary.pending} tone="#7A4E1A" />
          <KPI label="APPROVED · TO PAY" value={summary.approved} tone="#8B7F6A" />
          <KPI label="REIMBURSED · MONTH" value={summary.reimbursed_this_month} tone="#1D633E" />
          <KPI label="MY PENDING" value={summary.my_pending} tone="#7A4E1A" />
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[var(--line)]">
        {[["all","All"],["mine","My Expenses"],["approvals","Awaiting My Approval"]].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm border-b-2 ${tab === k ? "border-[var(--accent)] text-[var(--accent-strong)] font-semibold" : "border-transparent text-[var(--ink-2)]"}`}
            data-testid={`tab-${k}`}>
            {l}
          </button>
        ))}
      </div>

      <div className="card-flat p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px]" data-testid="expenses-table">
            <thead className="bg-[var(--surface-2)] border-y border-[var(--line)]"><tr className="text-left">
              <Th>Title</Th><Th>Claimant</Th><Th>Total</Th><Th>Status</Th><Th>Next Approver</Th><Th>Date</Th>
            </tr></thead>
            <tbody>
              {expenses.map((e) => (
                <tr key={e.id} onClick={() => setDetail(e.id)} className="row-hover border-b border-[var(--line-soft)] cursor-pointer" data-testid={`exp-row-${e.id}`}>
                  <Td className="font-semibold text-sm">{e.title}</Td>
                  <Td className="text-xs">{e.claimant_name}</Td>
                  <Td className="font-mono">{fmtMoney(e.total)}</Td>
                  <Td><span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${STATUS_TONE[e.status]}`}>{e.status}</span></Td>
                  <Td className="text-xs">{e.pending_approver_role || "—"}</Td>
                  <Td className="font-mono text-xs">{formatDate(e.created_at)}</Td>
                </tr>
              ))}
              {loading && expenses.length === 0 && <SkeletonRows cols={6} />}
              {!loading && expenses.length === 0 && (
                <EmptyRow cols={6} icon={Receipt} title="No claims here"
                  hint="Staff claims for travel, site purchases and other spends appear here for approval."
                  actionLabel={canCreate ? "New claim" : undefined} onAction={() => setShowCreate(true)} />
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && <CreateExpense onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {editExpense && <CreateExpense initial={editExpense} expenseId={editExpense.id}
        onClose={() => setEditExpense(null)} onCreated={() => { setEditExpense(null); load(); }} />}
      {detail && <ExpenseDetail expId={detail} accounts={accounts} isAdmin={isAdmin}
        isFinance={isFinance} canCreate={canCreate} canManage={canManage} canDeletePosted={canDeletePosted}
        userId={user?.user_id} userRole={user?.role} onClose={() => setDetail(null)}
        onEdit={(expense) => { setDetail(null); setEditExpense(expense); }} onChange={load} />}
    </div>
  );
}

function KPI({ label, value, tone }) {
  return (
    <div className="card-flat p-4 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: tone }} />
      <div className="overline text-[10px] text-[var(--ink-2)] mb-1">{label}</div>
      <div className="font-display font-bold tracking-tighter text-3xl tabular-nums">{value ?? "—"}</div>
    </div>
  );
}

const CATEGORIES = ["travel","meals","materials","utilities","site","office","other"];
const CATEGORY_LABEL = {
  travel: "Travel", meals: "Meals", materials: "Materials", utilities: "Utilities",
  site: "Site spend", office: "Office", other: "Other",
};
const blankLine = () => ({ category: "travel", amount: "", description: "", receipt_url: "", tax_rate: 0 });

function CreateExpense({ onClose, onCreated, initial = null, expenseId = null }) {
  const [f, setF] = useState({
    title: initial?.title || "", payment_mode: initial?.payment_mode || "personal",
    notes: initial?.notes || "", project_id: initial?.project_id || null,
    vendor_id: initial?.vendor_id || null,
    reimburse_to_account_id: initial?.reimburse_to_account_id || null,
    lines: initial?.lines?.map((line) => ({
      category: line.category, amount: Number(line.amount || 0),
      description: line.description || "", receipt_url: line.receipt_url || "",
      tax_rate: Number(line.tax_rate || 0), date: line.date || null,
    })) || [blankLine()],
  });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const total = f.lines.reduce((s, l) => s + Number(l.amount || 0) + Number(l.amount || 0) * Number(l.tax_rate || 0)/100, 0);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const body = {
        ...f,
        lines: f.lines.map((line) => ({ ...line, amount: Number(line.amount) || 0, receipt_url: line.receipt_url || null })),
      };
      if (expenseId) await api.put(`/expenses/${expenseId}`, body);
      else await api.post("/expenses", body);
      onCreated();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Submit failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title={expenseId ? "Correct Expense Claim" : "Submit Expense Claim"} eyebrow={expenseId ? "EDIT CLAIM" : "NEW CLAIM"} wide>
      <form onSubmit={submit} className="space-y-4" data-testid="exp-create-form">
        <F label="Title *"><input required data-testid="exp-title" className="input-flat w-full" value={f.title} onChange={(e) => setF({...f, title: e.target.value})} /></F>
        <F label="Payment mode">
          <select aria-label="Payment mode" className="input-flat w-full" value={f.payment_mode} onChange={(e) => setF({...f, payment_mode: e.target.value})}>
            <option value="personal">Paid personally (reimburse me)</option>
            <option value="cash">Company cash</option>
            <option value="corporate_card">Corporate card</option>
            <option value="bank_transfer">Bank transfer</option>
          </select>
        </F>

        <div>
          <div className="overline mb-2">WHAT WAS SPENT</div>
          <div className="hidden md:grid grid-cols-12 gap-2 px-1 pb-1 text-[11px] font-semibold text-[var(--ink-3)]">
            <span className="col-span-2">Category</span>
            <span className="col-span-4">What it was for</span>
            <span className="col-span-2 text-right">Amount (₹)</span>
            <span className="col-span-3">Receipt link</span>
          </div>
          <div className="space-y-2">
            {f.lines.map((l, i) => {
              const setLine = (patch) => setF((s) => ({ ...s, lines: s.lines.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));
              return (
                <div key={i} className="grid grid-cols-2 md:grid-cols-12 gap-2 items-center rounded-lg md:rounded-none border md:border-0 border-[var(--line)] p-2 md:p-0" data-testid={`exp-line-${i}`}>
                  <select aria-label="Category" className="input-flat col-span-1 md:col-span-2" value={l.category} onChange={(e) => setLine({ category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] || c}</option>)}
                  </select>
                  <input type="number" step="0.01" min="0" inputMode="decimal" aria-label="Amount" placeholder="0.00"
                    className="input-flat col-span-1 md:col-span-2 md:order-3 text-right tabular-nums" value={l.amount}
                    onChange={(e) => setLine({ amount: e.target.value })} />
                  <input aria-label="What it was for" placeholder="e.g. Auto to site, Andheri" className="input-flat col-span-2 md:col-span-4 md:order-2" value={l.description}
                    onChange={(e) => setLine({ description: e.target.value })} />
                  <input aria-label="Receipt link" type="url" placeholder="Paste a photo or Drive link" className="input-flat col-span-2 md:col-span-3 md:order-4" value={l.receipt_url}
                    onChange={(e) => setLine({ receipt_url: e.target.value })} />
                  <div className="col-span-2 md:col-span-1 md:order-5 flex justify-end">
                    {f.lines.length > 1 && (
                      <button type="button" aria-label={`Remove line ${i + 1}`} title="Remove line"
                        onClick={() => setF((s) => ({ ...s, lines: s.lines.filter((_, j) => j !== i) }))}
                        className="p-2 rounded-md text-[var(--ink-3)] hover:text-[var(--danger)] hover:bg-[var(--danger-soft)]"><X size={14} /></button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <button type="button" onClick={() => setF((s) => ({ ...s, lines: [...s.lines, blankLine()] }))} className="btn-ghost text-xs mt-2"><Plus size={11}/> Add another item</button>
          <p className="text-[11px] text-[var(--ink-3)] mt-2">Bigger claims need a receipt link before they go for approval.</p>
        </div>

        <F label="Notes"><textarea className="input-flat w-full h-16" value={f.notes} onChange={(e) => setF({...f, notes: e.target.value})} /></F>
        <div className="flex items-baseline justify-end gap-3 border-t border-[var(--line)] pt-3">
          <span className="text-sm text-[var(--ink-2)]">Total claim</span>
          <span className="font-display font-bold text-2xl tabular-nums" data-testid="exp-total">{fmtMoney(total)}</span>
        </div>

        {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy || !f.title || f.lines.length === 0 || f.lines.some((line) => !(Number(line.amount) > 0))} className="btn-primary" data-testid="exp-submit">{busy ? "Saving…" : expenseId ? "Save and restart approval" : "Submit claim"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ExpenseDetail({ expId, accounts, isAdmin, isFinance, canCreate, canManage, canDeletePosted, userId, userRole, onClose, onEdit, onChange }) {
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
  const cancelExpense = async () => {
    const posted = exp.status === "reimbursed";
    const message = posted
      ? "Delete this reimbursed expense? A balanced accounting reversal will be retained in the audit trail."
      : "Delete this expense claim? It will remain in the audit trail as cancelled.";
    if (!await confirmAction(message)) return;
    setBusy("delete"); setErr("");
    try {
      await api.delete(`/expenses/${expId}`);
      await load(); onChange && onChange();
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
    finally { setBusy(""); }
  };

  if (!exp) return <Modal onClose={onClose} title="Loading…" wide><div className="skeleton h-64"/></Modal>;
  const canDecide = ["pending_l1","pending_l2"].includes(exp.status) && (isAdmin || exp.pending_approver_role === userRole);
  const canReimburse = exp.status === "approved" && isFinance;
  const isOwner = exp.claimant_id === userId;
  const canEdit = !["reimbursed", "cancelled"].includes(exp.status) &&
    ((isOwner && canCreate) || isAdmin || canManage);
  const canCancel = exp.status !== "cancelled" && (exp.status === "reimbursed"
    ? (isAdmin || canDeletePosted)
    : ((isOwner && canCreate) || isAdmin || canManage));

  return (
    <Modal onClose={onClose} title={exp.title} eyebrow={`EXPENSE · ${exp.claimant_name}`} wide>
      {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 mb-3">{err}</div>}

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <span className={`text-[10px] font-mono uppercase px-3 py-1 ${STATUS_TONE[exp.status]}`}>{exp.status}</span>
        {exp.pending_approver_role && <span className="text-xs text-[var(--ink-2)]">Awaiting: <b>{exp.pending_approver_role}</b></span>}
        <span className="font-mono font-bold text-lg ml-auto accent-blue">{fmtMoney(exp.total)}</span>
      </div>

      {(canEdit || canCancel) && (
        <div className="flex gap-2 mb-4">
          {canEdit && <button type="button" className="btn-ghost text-xs" onClick={() => onEdit(exp)}><PencilSimple size={12}/> Edit claim</button>}
          {canCancel && <button type="button" disabled={busy === "delete"} className="btn-ghost text-xs text-[var(--danger)]" onClick={cancelExpense}><Trash size={12}/> {exp.status === "reimbursed" ? "Delete with reversal" : "Delete"}</button>}
        </div>
      )}

      <div className="overline mb-2">LINE ITEMS</div>
      <div className="border border-[var(--line)] mb-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]"><tr className="text-left">
            <Th>Category</Th><Th>Description</Th><Th>Amount</Th><Th>Receipt</Th>
          </tr></thead>
          <tbody>
            {exp.lines.map((l) => (
              <tr key={l.id} className="border-b border-[var(--line-soft)]">
                <Td className="text-xs uppercase font-mono">{l.category}</Td>
                <Td>{l.description || "—"}</Td>
                <Td className="font-mono">{fmtMoney(l.amount)}</Td>
                <Td>{safeExternalUrl(l.receipt_url) ? <a href={safeExternalUrl(l.receipt_url)} target="_blank" rel="noreferrer" className="accent-blue text-xs">View</a> : <span className="text-[var(--ink-3)]">—</span>}</Td>
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
              <div key={i} className="border border-[var(--line)] p-2 text-xs">
                <div className="font-mono">{(t.at || "").slice(0,16)} · {t.actor_name || t.actor} ({t.actor_role || "system"})</div>
                <div><b>{t.decision}</b> {t.comment && `— ${t.comment}`}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {canDecide && (
        <div className="border border-[var(--line)] p-3 mb-4 bg-[var(--surface-2)]">
          <div className="overline mb-2">MY DECISION</div>
          <textarea className="input-flat w-full h-16 mb-2" placeholder="Optional comment" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="dec-comment" />
          <div className="flex gap-2">
            <button disabled={busy === "approve"} onClick={() => decide("approve")} className="btn-primary text-xs" data-testid="approve-btn"><ThumbsUp size={12}/> Approve</button>
            <button disabled={busy === "reject"} onClick={() => decide("reject")} className="btn-ghost text-xs text-[var(--danger)]" data-testid="reject-btn"><ThumbsDown size={12}/> Reject</button>
          </div>
        </div>
      )}

      {canReimburse && (
        <div className="border border-[var(--line)] p-3 bg-[var(--hover)]">
          <div className="overline mb-2">REIMBURSE</div>
          <div className="flex flex-wrap gap-2 items-center">
            <select aria-label="Pay from" className="input-flat" value={payFrom} onChange={(e) => setPayFrom(e.target.value)} data-testid="pay-from">
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <button disabled={busy === "reimburse" || !payFrom} onClick={reimburse} className="btn-primary text-xs" data-testid="reimburse-btn">
              <Wallet size={12}/> {busy === "reimburse" ? "Posting…" : `Reimburse ${fmtMoney(exp.total)}`}
            </button>
          </div>
        </div>
      )}

      {exp.status === "reimbursed" && (
        <div className="border border-[var(--success)] bg-[var(--success-soft)] p-3 text-sm text-[var(--success)]">
          <Check size={13} className="inline mr-1"/> Reimbursed on {formatDate(exp.reimbursed_at)} · JE {exp.reimbursement_journal_id}
        </div>
      )}
    </Modal>
  );
}

function F({ label, children }) { return <label className="block"><div className="text-xs text-[var(--ink-2)] mb-1">{label}</div>{children}</label>; }
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className={`bg-white p-6 w-full border border-[var(--line)] max-h-[92vh] overflow-y-auto ${wide ? "max-w-5xl" : "max-w-2xl"}`}>
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
