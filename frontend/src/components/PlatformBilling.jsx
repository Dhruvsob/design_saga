import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FilePdf, Plus, Receipt, Gear, X } from "@phosphor-icons/react";
import api, { API } from "../lib/api";
import { confirmAction } from "../lib/confirm";
import { dateForInput, formatDate } from "../lib/format";

const inr = (n) => `Rs. ${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const STATUS = {
  draft: ["Draft", "bg-[var(--surface-2)] text-[var(--ink-2)]"],
  issued: ["Issued", "bg-[var(--hover)] text-[#5F5A4B]"],
  partially_paid: ["Part paid", "bg-[var(--warning-soft)] text-[var(--warning)]"],
  overdue: ["Overdue", "bg-[var(--danger-soft)] text-[var(--danger)]"],
  paid: ["Paid", "bg-[var(--success-soft)] text-[var(--success)]"],
  void: ["Void", "bg-[var(--surface-2)] text-[var(--ink-3)] line-through"],
};
const METHODS = [["bank_transfer", "Bank transfer"], ["upi", "UPI"], ["cheque", "Cheque"],
  ["cash", "Cash"], ["card", "Card"], ["other", "Other"]];

function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || String(x)).join(" · ");
  return fallback;
}

function Dialog({ title, eyebrow, onClose, children, testid }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()} data-testid={testid}
           className="bg-[var(--surface)] w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-[var(--line)] rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="overline">{eyebrow}</div>
            <h2 className="font-display font-bold tracking-tight text-xl">{title}</h2>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost text-xs" aria-label="Close"><X size={14} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

const Field = ({ label, children, className = "" }) => (
  <label className={`text-xs space-y-1 block ${className}`}>
    <span className="font-mono uppercase text-[var(--ink-3)]">{label}</span>
    {children}
  </label>
);

function SettingsDialog({ onClose }) {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.get("/platform/billing/settings").then(({ data }) => setF(data)).catch(() => setErr("Could not load settings")); }, []);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const setBank = (k, v) => setF((s) => ({ ...s, bank: { ...s.bank, [k]: v } }));
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api.put("/platform/billing/settings", { ...f, tax_rate: Number(f.tax_rate || 0),
        payment_terms_days: Number(f.payment_terms_days || 0) });
      toast.success("Billing settings saved");
      onClose();
    } catch (ex) { setErr(errText(ex, "Could not save")); } finally { setBusy(false); }
  };
  return (
    <Dialog title="Billing settings" eyebrow="GAMAA AS SELLER" onClose={onClose} testid="billing-settings">
      {!f ? <div className="skeleton h-40 w-full" /> : (
        <form onSubmit={save} className="space-y-4">
          <p className="text-xs text-[var(--ink-2)]">
            These details print on every Gamaa invoice. GST is added only when a GSTIN and a rate are set; it is split
            CGST + SGST for studios in your state and IGST otherwise. Have the first invoices checked by your accountant.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Business name"><input required minLength={2} className="input-flat w-full" value={f.seller_name} onChange={(e) => set("seller_name", e.target.value)} /></Field>
            <Field label="State"><input className="input-flat w-full" value={f.state} placeholder="e.g. Gujarat" onChange={(e) => set("state", e.target.value)} /></Field>
            <Field label="Address" className="sm:col-span-2"><input className="input-flat w-full" value={f.address} onChange={(e) => set("address", e.target.value)} /></Field>
            <Field label="GSTIN"><input className="input-flat w-full font-mono uppercase" maxLength={15} value={f.gstin} onChange={(e) => set("gstin", e.target.value.toUpperCase())} /></Field>
            <Field label="PAN"><input className="input-flat w-full font-mono uppercase" maxLength={10} value={f.pan} onChange={(e) => set("pan", e.target.value.toUpperCase())} /></Field>
            <Field label="GST rate %"><input type="number" min="0" max="28" step="0.01" className="input-flat w-full" value={f.tax_rate} onChange={(e) => set("tax_rate", e.target.value)} /></Field>
            <Field label="SAC code"><input className="input-flat w-full font-mono" maxLength={8} value={f.sac} onChange={(e) => set("sac", e.target.value)} /></Field>
            <Field label="Email"><input type="email" className="input-flat w-full" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
            <Field label="Phone"><input className="input-flat w-full" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
            <Field label="Invoice prefix"><input required maxLength={12} className="input-flat w-full font-mono" value={f.invoice_prefix} onChange={(e) => set("invoice_prefix", e.target.value)} /></Field>
            <Field label="Payment terms (days)"><input type="number" min="0" max="90" className="input-flat w-full" value={f.payment_terms_days} onChange={(e) => set("payment_terms_days", e.target.value)} /></Field>
          </div>
          <div className="overline">PAYMENT DETAILS ON INVOICES</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Account name"><input className="input-flat w-full" value={f.bank.account_name} onChange={(e) => setBank("account_name", e.target.value)} /></Field>
            <Field label="Bank"><input className="input-flat w-full" value={f.bank.bank} onChange={(e) => setBank("bank", e.target.value)} /></Field>
            <Field label="Account number"><input className="input-flat w-full font-mono" value={f.bank.account} onChange={(e) => setBank("account", e.target.value)} /></Field>
            <Field label="IFSC"><input className="input-flat w-full font-mono uppercase" value={f.bank.ifsc} onChange={(e) => setBank("ifsc", e.target.value.toUpperCase())} /></Field>
            <Field label="UPI ID" className="sm:col-span-2"><input className="input-flat w-full font-mono" value={f.bank.upi} onChange={(e) => setBank("upi", e.target.value)} /></Field>
            <Field label="Note on every invoice" className="sm:col-span-2"><textarea rows={2} maxLength={600} className="input-flat w-full" value={f.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
          </div>
          {err && <div className="text-xs text-[var(--danger)]">{err}</div>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
            <button disabled={busy} className="btn-primary" data-testid="billing-settings-save">{busy ? "Saving…" : "Save settings"}</button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

function NewInvoiceDialog({ orgs, onClose, onDone }) {
  const choices = orgs.filter((o) => o.is_active !== false);
  const [orgId, setOrgId] = useState("");
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!orgId) { setF(null); return; }
    api.get(`/platform/billing/suggest/${orgId}`).then(({ data }) => setF({
      period_start: data.period_start, period_end: data.period_end, notes: "",
      lines: data.lines.map((l) => ({ description: l.description, amount: l.amount ? String(l.amount) : "" })),
    })).catch((e) => setErr(errText(e, "Could not prepare the invoice")));
  }, [orgId]);
  const setLine = (i, k, v) => setF((s) => ({ ...s, lines: s.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)) }));
  const total = (f?.lines || []).reduce((a, l) => a + (Number(l.amount) || 0), 0);
  const submit = async (issue) => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/platform/billing/invoices", {
        org_id: orgId, period_start: f.period_start, period_end: f.period_end, notes: f.notes, issue,
        lines: f.lines.filter((l) => l.description.trim()).map((l) => ({ description: l.description, amount: Number(l.amount) })),
      });
      toast.success(issue ? `Invoice ${data.number} issued` : "Draft saved");
      onDone();
    } catch (ex) { setErr(errText(ex, "Could not create the invoice")); } finally { setBusy(false); }
  };
  return (
    <Dialog title="New invoice" eyebrow="GAMAA BILLING" onClose={onClose} testid="new-platform-invoice">
      <Field label="Workspace">
        <select className="input-flat w-full" value={orgId} onChange={(e) => setOrgId(e.target.value)} data-testid="invoice-org">
          <option value="">Choose a workspace…</option>
          {choices.map((o) => <option key={o.org_id} value={o.org_id}>{o.name}</option>)}
        </select>
      </Field>
      {f && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Service from"><input type="date" className="input-flat w-full" value={f.period_start} onChange={(e) => setF({ ...f, period_start: e.target.value })} /></Field>
            <Field label="Service to"><input type="date" className="input-flat w-full" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} /></Field>
          </div>
          <div className="space-y-2">
            {f.lines.map((l, i) => (
              <div key={i} className="flex gap-2 items-end">
                <Field label={i === 0 ? "Description" : ""} className="flex-1">
                  <input className="input-flat w-full" maxLength={200} value={l.description} aria-label={`Line ${i + 1} description`}
                         onChange={(e) => setLine(i, "description", e.target.value)} />
                </Field>
                <Field label={i === 0 ? "Amount (Rs.)" : ""} className="w-36">
                  <input type="number" min="0" step="0.01" className="input-flat w-full" value={l.amount} aria-label={`Line ${i + 1} amount`}
                         onChange={(e) => setLine(i, "amount", e.target.value)} data-testid={`invoice-amount-${i}`} />
                </Field>
                {f.lines.length > 1 && (
                  <button type="button" className="btn-ghost text-xs mb-0.5" aria-label={`Remove line ${i + 1}`}
                          onClick={() => setF({ ...f, lines: f.lines.filter((_, j) => j !== i) })}><X size={12} /></button>
                )}
              </div>
            ))}
            <button type="button" className="btn-ghost text-xs" onClick={() => setF({ ...f, lines: [...f.lines, { description: "", amount: "" }] })}>
              <Plus size={12} /> Add line
            </button>
          </div>
          <Field label="Note (optional)"><input className="input-flat w-full" maxLength={600} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
          <div className="text-sm text-right">Before GST: <b className="font-mono">{inr(total)}</b></div>
        </div>
      )}
      {err && <div className="text-xs text-[var(--danger)]">{err}</div>}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
        <button type="button" disabled={!f || busy || total <= 0} onClick={() => submit(false)} className="btn-ghost">Save draft</button>
        <button type="button" disabled={!f || busy || total <= 0} onClick={() => submit(true)} className="btn-primary" data-testid="invoice-issue">
          {busy ? "Saving…" : "Issue invoice"}
        </button>
      </div>
    </Dialog>
  );
}

function PaymentDialog({ invoice, onClose, onDone }) {
  const [f, setF] = useState({ amount: String(invoice.balance), method: "bank_transfer", reference: "",
    received_on: dateForInput(new Date()) });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/platform/billing/invoices/${invoice.id}/payments`, { ...f, amount: Number(f.amount) });
      toast.success(data.paid_through ? `Paid in full · workspace paid up to ${formatDate(data.paid_through)}` : "Payment recorded");
      onDone();
    } catch (ex) { setErr(errText(ex, "Could not record the payment")); } finally { setBusy(false); }
  };
  return (
    <Dialog title={`Record payment · ${invoice.number}`} eyebrow={invoice.buyer?.name || "GAMAA BILLING"} onClose={onClose} testid="platform-payment">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-[var(--ink-2)]">
          Balance due {inr(invoice.balance)}. Paying in full extends the workspace to {formatDate(invoice.period_end)} and lifts any
          grace or read-only state at once.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Amount (Rs.)"><input required type="number" min="0.01" step="0.01" max={invoice.balance} className="input-flat w-full" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} data-testid="payment-amount" /></Field>
          <Field label="Received on"><input required type="date" max={dateForInput(new Date())} className="input-flat w-full" value={f.received_on} onChange={(e) => setF({ ...f, received_on: e.target.value })} /></Field>
          <Field label="Method">
            <select className="input-flat w-full" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
              {METHODS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </Field>
          <Field label="Reference (UTR / cheque no.)"><input className="input-flat w-full font-mono" maxLength={120} value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
        </div>
        {err && <div className="text-xs text-[var(--danger)]">{err}</div>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} className="btn-primary" data-testid="payment-save">{busy ? "Saving…" : "Record payment"}</button>
        </div>
      </form>
    </Dialog>
  );
}

function VoidDialog({ invoice, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api.post(`/platform/billing/invoices/${invoice.id}/void`, { reason });
      toast.success(`${invoice.number} voided`);
      onDone();
    } catch (ex) { setErr(errText(ex, "Could not void")); } finally { setBusy(false); }
  };
  return (
    <Dialog title={`Void ${invoice.number}?`} eyebrow="GAMAA BILLING" onClose={onClose} testid="platform-void">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-[var(--ink-2)]">The invoice keeps its number and is marked VOID with this reason. Issue a new one if needed.</p>
        <Field label="Reason (printed on the invoice)">
          <input required minLength={3} maxLength={200} className="input-flat w-full" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {err && <div className="text-xs text-[var(--danger)]">{err}</div>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} className="btn-primary">{busy ? "Voiding…" : "Void invoice"}</button>
        </div>
      </form>
    </Dialog>
  );
}

/** GAMAA's own invoices to studios, payments and revenue (P1.3). */
export default function PlatformBilling({ orgs, onChanged }) {
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState(null);
  const [filter, setFilter] = useState("");
  const [dialog, setDialog] = useState(null);
  const load = async () => {
    const [s, r] = await Promise.all([api.get("/platform/billing/summary"), api.get("/platform/billing/invoices")]);
    setSummary(s.data); setRows(r.data);
  };
  useEffect(() => { load().catch(() => setRows([])); }, []);
  const refresh = () => { setDialog(null); load(); onChanged?.(); };

  const issue = async (inv) => {
    if (!await confirmAction({ title: "Issue this invoice?", body: "It gets a number and the studio's admins are notified. Issued invoices can't be edited, only voided.", confirmLabel: "Issue" })) return;
    try { await api.post(`/platform/billing/invoices/${inv.id}/issue`); toast.success("Invoice issued"); refresh(); }
    catch (e) { toast.error(errText(e, "Could not issue")); }
  };
  const voidInv = (inv) => setDialog({ kind: "void", invoice: inv });
  const removeDraft = async (inv) => {
    if (!await confirmAction({ title: "Delete this draft?", confirmLabel: "Delete", danger: true })) return;
    try { await api.delete(`/platform/billing/invoices/${inv.id}`); refresh(); }
    catch (e) { toast.error(errText(e, "Could not delete")); }
  };

  const shown = (rows || []).filter((r) => !filter || r.status === filter);
  return (
    <div className="card-flat" data-testid="platform-billing">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <div className="overline"><Receipt size={11} className="inline mr-1" /> GAMAA BILLING</div>
          <div className="text-xs text-[var(--ink-2)] mt-1">Your invoices to studios and the payments received. Platform revenue comes only from here.</div>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-ghost text-xs" onClick={() => setDialog({ kind: "settings" })} data-testid="billing-settings-btn"><Gear size={12} /> Settings</button>
          <button type="button" className="btn-primary text-xs" onClick={() => setDialog({ kind: "new" })} data-testid="new-invoice-btn"><Plus size={12} /> New invoice</button>
        </div>
      </div>
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4" data-testid="billing-summary">
          {[["Received this month", inr(summary.received_this_month)], ["Invoiced this month", inr(summary.invoiced_this_month)],
            ["Outstanding", inr(summary.outstanding)], ["Overdue invoices", summary.overdue_invoices]].map(([label, value]) => (
            <div key={label} className="border border-[var(--line)] rounded-md p-3">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">{label}</div>
              <div className="font-mono text-lg mt-0.5">{value}</div>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1 mb-3" role="group" aria-label="Filter invoices">
        {[["", "All"], ["draft", "Drafts"], ["overdue", "Overdue"], ["issued", "Issued"], ["partially_paid", "Part paid"], ["paid", "Paid"], ["void", "Void"]].map(([k, label]) => (
          <button key={k} type="button" onClick={() => setFilter(k)} aria-pressed={filter === k}
                  className={`text-xs px-3 py-1 rounded-full border ${filter === k ? "border-[var(--accent)] bg-[var(--hover)]" : "border-[var(--line)]"}`}>{label}</button>
        ))}
      </div>
      {!rows ? <div className="skeleton h-24 w-full" /> : shown.length === 0 ? (
        <div className="text-sm text-[var(--ink-3)] py-6 text-center">
          {rows.length ? "No invoices match this filter." : "No invoices yet. Fill in Settings, then create the first invoice."}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm" data-testid="platform-invoices">
            <thead>
              <tr className="text-left text-[10px] font-mono uppercase text-[var(--ink-3)] border-b border-[var(--line)]">
                <th className="py-2 pr-3">Invoice</th><th className="py-2 pr-3">Workspace</th><th className="py-2 pr-3">Period</th>
                <th className="py-2 pr-3 text-right">Total</th><th className="py-2 pr-3 text-right">Balance</th>
                <th className="py-2 pr-3">Status</th><th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((inv) => {
                const [label, tone] = STATUS[inv.status] || [inv.status, ""];
                return (
                  <tr key={inv.id} className="border-b border-[var(--line-soft)]">
                    <td className="py-2 pr-3">
                      <div className="font-mono text-xs">{inv.number || "Draft"}</div>
                      {inv.due_on && <div className="text-[10px] text-[var(--ink-3)]">due {formatDate(inv.due_on)}</div>}
                    </td>
                    <td className="py-2 pr-3">{inv.buyer?.name}</td>
                    <td className="py-2 pr-3 text-xs">{formatDate(inv.period_start)} – {formatDate(inv.period_end)}</td>
                    <td className="py-2 pr-3 text-right font-mono">{inr(inv.total)}</td>
                    <td className="py-2 pr-3 text-right font-mono">{inv.status === "void" ? "—" : inr(inv.balance)}</td>
                    <td className="py-2 pr-3"><span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded ${tone}`}>{label}</span></td>
                    <td className="py-2 text-right whitespace-nowrap">
                      <a href={`${API}/platform/billing/invoices/${inv.id}/pdf`} target="_blank" rel="noreferrer"
                         className="btn-ghost text-xs inline-flex" aria-label={`PDF of ${inv.number || "draft"}`}><FilePdf size={12} /></a>
                      {inv.status === "draft" && <>
                        <button type="button" className="btn-ghost text-xs" onClick={() => issue(inv)}>Issue</button>
                        <button type="button" className="btn-ghost text-xs" onClick={() => removeDraft(inv)}>Delete</button>
                      </>}
                      {["issued", "overdue", "partially_paid"].includes(inv.status) && (
                        <button type="button" className="btn-ghost text-xs" onClick={() => setDialog({ kind: "pay", invoice: inv })}
                                data-testid={`pay-${inv.id}`}>Record payment</button>
                      )}
                      {["issued", "overdue"].includes(inv.status) && (
                        <button type="button" className="btn-ghost text-xs" onClick={() => voidInv(inv)}>Void</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {dialog?.kind === "settings" && <SettingsDialog onClose={() => setDialog(null)} />}
      {dialog?.kind === "new" && <NewInvoiceDialog orgs={orgs} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "pay" && <PaymentDialog invoice={dialog.invoice} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === "void" && <VoidDialog invoice={dialog.invoice} onClose={() => setDialog(null)} onDone={refresh} />}
    </div>
  );
}
