import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { API } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { dateForInput, formatDate, roundPaise, statusLabel } from "../lib/format";
import { Plus, FilePdf, Trash, Eye, PencilSimple, Money, X, ArrowCounterClockwise } from "@phosphor-icons/react";
import { compatibleAccount, methodForAccount } from "../lib/cashbank";
import SearchSelect from "../components/SearchSelect";
import { askForm, confirmAction } from "../lib/confirm";
import PdfPreviewModal from "../components/PdfPreview";
import RowActions from "../components/RowActions";
import { usePaged } from "../components/Pager";
import { Receipt } from "@phosphor-icons/react";
import { SkeletonRows, EmptyRow } from "../components/TableState";
import PageHero from "../components/PageHero";
import { MoneyInTabs, useReminderFlow } from "../components/MoneyIn";
import { BellRinging } from "@phosphor-icons/react";

export default function Invoices({ docType = "invoice" }) {
  const { hasPerm } = useAuth();
  const canCreate = hasPerm("invoices.create");
  const canUpdate = hasPerm("invoices.update");
  const canDelete = hasPerm("invoices.delete");
  const canRecordPayment = hasPerm("finance.create");
  const canCorrectPayment = hasPerm("finance.delete");
  const canRemind = hasPerm("finance.read") && (hasPerm("finance.create") || canUpdate);
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const due = (r) => roundPaise(Math.max(0, Number(r.total || 0) - Number(r.paid_amount || 0)));
  // Invoices are documents. Only invoices that already carry money from the old
  // flow are still collected on the invoice; the rest go through Collections Due.
  const legacyMoney = (r) => Number(r.paid_amount || 0) > 0 || Boolean(r.accrual_journal_id) || ["paid", "partially_paid"].includes(r.status);
  const [incomeAccounts, setIncomeAccounts] = useState([]);
  const [planned, setPlanned] = useState({});   // invoice_id -> {planned, received}
  const visibleRows = useMemo(() => rows.filter((r) => {
    if (statusFilter === "unpaid" && !["sent", "overdue", "partially_paid"].includes(r.status)) return false;
    if (statusFilter !== "all" && statusFilter !== "unpaid" && r.status !== statusFilter) return false;
    const t = search.trim().toLowerCase();
    return !t || `${r.number} ${r.client_name || ""} ${r.project_name || ""}`.toLowerCase().includes(t);
  }), [rows, search, statusFilter]);
  const { pageRows: rowsPage, pager: rowsPager } = usePaged(visibleRows, { key: "invoices" });
  const [startReminder, reminderModal] = useReminderFlow();
  const [milestones, setMilestones] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(initialForm(docType));
  const [editingId, setEditingId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [paying, setPaying] = useState(null);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [payment, setPayment] = useState({
    amount: "", date: dateForInput(new Date()), bank_account_id: "",
    payment_method: "bank_transfer", reference: "", notes: "",
  });

  function initialForm(dt) {
    return {
      client_id: "", project_id: "",
      items: [{ description: "", quantity: 1, rate: "", amount: 0 }],
      tax_rate: 18, notes: "Payment due within 15 days.",
      due_date: "", status: "draft", doc_type: dt, milestone_id: "",
    };
  }

  // Bill a project milestone: the invoice then carries that money in Collections (counted once).
  useEffect(() => {
    if (docType !== "invoice" || !form.project_id) { setMilestones([]); return; }
    api.get(`/projects/${form.project_id}/milestones`)
      .then(({ data }) => setMilestones((data || []).filter((m) => m.status !== "paid")))
      .catch(() => setMilestones([]));
  }, [form.project_id, docType]);

  const pickMilestone = (id) => {
    const ms = milestones.find((m) => m.id === id);
    const blank = form.items.length === 1 && !form.items[0].description && !Number(form.items[0].rate);
    const left = ms ? roundPaise(Number(ms.amount || 0) - Number(ms.paid_amount || 0)) : 0;
    setForm({
      ...form, milestone_id: id,
      due_date: form.due_date || ms?.due_date || "",
      items: ms && blank ? [{ description: ms.name, quantity: 1, rate: left, amount: left }] : form.items,
    });
  };

  const load = async () => {
    const [inv, cl, pr, acc] = await Promise.all([
      api.get(`/invoices?doc_type=${docType}`),
      api.get("/clients"),
      api.get("/projects"),
      canRecordPayment ? api.get("/accounts").catch(() => ({ data: [] })) : Promise.resolve({ data: [] }),
    ]);
    if (docType === "invoice" && hasPerm("finance.read")) {
      api.get("/accounting/receivables").then(({ data }) => {
        const m = {};
        for (const row of data.rows || []) {
          if (!row.invoice_id) continue;
          const x = m[row.invoice_id] || { planned: 0, received: 0 };
          x.planned += Number(row.amount || 0); x.received += Number(row.received_amount || 0);
          m[row.invoice_id] = x;
        }
        setPlanned(m);
      }).catch(() => {});
    }
    setRows(inv.data);
    setLoaded(true);
    setClients(cl.data);
    setProjects(pr.data);
    setAccounts((acc.data || []).filter((row) => row.is_bank || ["Cash", "Petty Cash"].includes(row.name)));
    setIncomeAccounts((acc.data || []).filter((row) => row.type === "income" && row.active !== false));
  };

  // "From this bill I expect this much": a separate expected collection, with its
  // own due date and reminder. The invoice itself never touches the accounts.
  const addToCollections = async (r) => {
    const already = planned[r.id]?.planned || 0;
    const left = roundPaise(Math.max(0, Number(r.total || 0) - Number(r.paid_amount || 0) - already));
    if (left <= 0) { toast.info("The whole invoice is already in Collections Due"); return; }
    const consult = incomeAccounts.find((a) => /consult/i.test(a.name)) || incomeAccounts[0];
    const v = await askForm({
      title: `Collect from ${r.number}`,
      body: `${r.client_name || "Client"} · ₹${left.toLocaleString("en-IN")} not yet planned. This adds an expected collection with its reminder; nothing is posted until you record the payment.`,
      fields: [
        { name: "amount", label: "Amount you expect (₹)", type: "number", required: true, defaultValue: String(left) },
        { name: "due_date", label: "Due date", type: "date", defaultValue: r.due_date || "" },
        { name: "income_account_id", label: "Income account on receipt", required: true, defaultValue: consult?.id || "",
          options: incomeAccounts.map((a) => ({ value: a.id, label: a.name })) },
        { name: "reminder_date", label: "Reminder date (optional)", type: "date" },
        { name: "reminder_time", label: "Reminder time", type: "time", defaultValue: "10:00" },
        { name: "remind_before_days", label: "Also remind before", defaultValue: "0",
          options: [{ value: "0", label: "No advance reminder" }, { value: "1", label: "1 day before" }, { value: "2", label: "2 days before" }, { value: "7", label: "1 week before" }] },
        { name: "repeat_every", label: "Repeat until received", defaultValue: "none",
          options: [{ value: "none", label: "Don't repeat" }, { value: "daily", label: "Every day" }, { value: "weekly", label: "Every week" }] },
      ],
      confirmLabel: "Add to Collections Due",
    });
    if (!v) return;
    try {
      await api.post("/accounting/receivables", {
        invoice_id: r.id, amount: Number(v.amount), name: `Invoice ${r.number}`,
        due_date: v.due_date || undefined, income_account_id: v.income_account_id,
        reminder_date: v.reminder_date || undefined,
        reminder_time: v.reminder_date ? (v.reminder_time || "10:00") : undefined,
        remind_before_days: v.reminder_date ? Number(v.remind_before_days || 0) : undefined,
        repeat_every: v.reminder_date ? v.repeat_every : undefined,
      });
      toast.success(v.reminder_date ? "Added to Collections Due with its reminder" : "Added to Collections Due");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not add to Collections Due"); }
  };
  useEffect(() => { load().catch(() => {}).finally(() => setLoaded(true)); setForm(initialForm(docType)); /* eslint-disable-next-line */ }, [docType]);

  const updateItem = (i, key, val) => {
    const items = [...form.items];
    items[i] = { ...items[i], [key]: val };
    items[i].amount = roundPaise((Number(items[i].quantity) || 0) * (Number(items[i].rate) || 0));
    setForm({ ...form, items });
  };

  const addItem = () => setForm({ ...form, items: [...form.items, { description: "", quantity: 1, rate: "", amount: 0 }] });
  const removeItem = (i) => setForm({ ...form, items: form.items.filter((_, idx) => idx !== i) });

  // Mirrors backend compute_invoice_totals: round each line, then tax on the rounded subtotal.
  const subtotal = roundPaise(form.items.reduce((s, it) => s + roundPaise((Number(it.quantity) || 0) * (Number(it.rate) || 0)), 0));
  const tax = roundPaise(subtotal * (Number(form.tax_rate) || 0) / 100);
  const total = roundPaise(subtotal + tax);

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      milestone_id: form.milestone_id || undefined,
      tax_rate: Number(form.tax_rate),
      items: form.items.map((it) => ({
        description: it.description,
        quantity: Number(it.quantity),
        rate: Number(it.rate),
        amount: Number(it.quantity) * Number(it.rate),
      })),
    };
    if (editingId) {
      const { status, doc_type, ...patch } = payload;
      await api.patch(`/invoices/${editingId}`, patch);
    } else {
      await api.post("/invoices", payload);
    }
    setForm(initialForm(docType));
    setEditingId(null);
    setShowForm(false);
    load();
  };

  const startEdit = (r) => {
    setEditingId(r.id);
    setForm({
      client_id: r.client_id || "", project_id: r.project_id || "",
      items: (r.items || []).map((it) => ({ ...it })),
      tax_rate: r.tax_rate ?? 18, notes: r.notes || "",
      due_date: r.due_date || "", status: r.status, doc_type: r.doc_type, milestone_id: r.milestone_id || "",
    });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const changeStatus = async (id, status) => {
    try {
      await api.patch(`/invoices/${id}/status`, { status });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update status");
    }
    load();
  };

  const openPayment = (row) => {
    const account = accounts[0];
    setPaying(row);
    setPayment({
      amount: roundPaise(Math.max(0, Number(row.total || 0) - Number(row.paid_amount || 0))),
      date: dateForInput(new Date()), bank_account_id: account?.id || "",
      payment_method: methodForAccount(account),
      reference: row.number || "", notes: `Payment received for ${row.number || "invoice"}`,
    });
  };

  const recordPayment = async (event) => {
    event.preventDefault();
    if (!paying || paymentBusy) return;
    setPaymentBusy(true);
    try {
      await api.post("/accounting/collections/receive", {
        ...payment, amount: Number(payment.amount), source_type: "invoice", source_id: paying.id,
      }, { headers: { "Idempotency-Key": crypto.randomUUID() } });
      toast.success("Invoice payment recorded in Accounting");
      setPaying(null); await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not record invoice payment");
    } finally { setPaymentBusy(false); }
  };

  const reverseLatestPayment = async (row) => {
    if (!row.journal_id) return toast.error("No linked payment journal was found");
    if (!await confirmAction(`Delete the latest payment for ${row.number}?\n\nA balanced reversal will preserve the audit history and restore the invoice balance.`)) return;
    try {
      await api.delete(`/journal-entries/${row.journal_id}`);
      toast.success("Latest invoice payment reversed"); await load();
    } catch (error) { toast.error(error?.response?.data?.detail || "Could not reverse invoice payment"); }
  };

  const del = async (id, isPaid) => {
    const msg = isPaid
      ? "Paid invoices cannot be deleted. Change the status to Sent first so Accounting records a reversal."
      : "Delete this invoice?";
    if (isPaid) { toast.error(msg); return; }
    if (!await confirmAction(msg)) return;
    try {
      await api.delete(`/invoices/${id}`);
      toast.success("Invoice deleted");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not delete");
    }
    load();
  };

  // Admin correction for invoices booked under the old "income when sent" rule.
  const restateCashBasis = async (row) => {
    const paid = Number(row.paid_amount || 0);
    if (!await confirmAction(
      `Restate ${row.number} on cash basis?

It was booked as ₹${Number(row.total || 0).toLocaleString("en-IN")} of income when it was sent. ` +
      `After this, income shows only the ₹${paid.toLocaleString("en-IN")} actually received, on the dates it came in. ` +
      "Nothing is deleted: the old entries stay in the audit log. This can be done once.")) return;
    try {
      await api.post(`/accounting/invoices/${row.id}/restate-cash-basis`);
      toast.success(`${row.number} restated: income now equals the money received`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not restate this invoice"); }
  };

  const download = (id) => {
    window.open(`${API}/invoices/${id}/pdf`, "_blank");
  };

  return (
    <div className="space-y-6" data-testid={`${docType}s-page`}>
      <PageHero title={docType === "quotation" ? "Quotations" : "Invoices"} count={loaded ? rows.length : undefined}
        kicker={docType === "quotation" ? undefined : "Invoices are documents for your client; the status is just for you. To follow up on money, use ⋮ › Add to Collections Due — reminders and payments live there."}>
        {canCreate && <button onClick={() => { setShowForm(!showForm); setEditingId(null); setForm(initialForm(docType)); }} className="btn-primary" data-testid={`new-${docType}-btn`}>
          <Plus size={14} /> {showForm ? "Cancel" : `New ${docType}`}
        </button>}
      </PageHero>
      {docType === "invoice" && <MoneyInTabs />}

      {showForm && (
        <form onSubmit={submit} className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="invoice-form">
          <div className="card-flat space-y-4">
            <div className="overline">DETAILS</div>
            <div className="grid grid-cols-2 gap-3">
              <SearchSelect className="input-flat" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
                <option value="">Select client</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">Select project</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </SearchSelect>
              {docType === "invoice" && form.project_id && milestones.length > 0 && (
                <select aria-label="Bill a milestone" className="input-flat col-span-2" value={form.milestone_id}
                  onChange={(e) => pickMilestone(e.target.value)} data-testid="invoice-milestone">
                  <option value="">Not for a specific milestone</option>
                  {milestones.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} · ₹{Number(m.amount || 0).toLocaleString("en-IN")}{m.percent ? ` (${m.percent}% of project value)` : ""}
                    </option>
                  ))}
                </select>
              )}
              <input type="date" aria-label="Due date" className="input-flat" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
              <input type="number" min="0" className="input-flat" placeholder="Tax %" value={form.tax_rate} onChange={(e) => setForm({ ...form, tax_rate: e.target.value })} />
            </div>

            <div className="overline">LINE ITEMS</div>
            <div className="space-y-2">
              {form.items.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-center">
                  <input className="input-flat col-span-6" placeholder="Description" value={it.description} onChange={(e) => updateItem(i, "description", e.target.value)} />
                  <input type="number" min="0" className="input-flat col-span-2" placeholder="Qty" value={it.quantity} onChange={(e) => updateItem(i, "quantity", e.target.value)} />
                  <input type="number" min="0" className="input-flat col-span-3" placeholder="Rate" value={it.rate} onChange={(e) => updateItem(i, "rate", e.target.value)} />
                  <button type="button" onClick={() => removeItem(i)} className="text-[var(--danger)]"><Trash size={14} /></button>
                </div>
              ))}
            </div>
            <button type="button" onClick={addItem} className="btn-ghost text-xs">+ Add line</button>
            <textarea className="input-flat" rows={3} placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>

          {/* Live preview */}
          <div className="card-flat bg-white">
            <div className="flex items-start justify-between mb-6">
              <div>
                <div className="font-display font-bold text-3xl tracking-tight accent-blue">{docType === "quotation" ? "QUOTATION" : "INVOICE"}</div>
                <div className="text-xs font-mono mt-1">DESIGN SAGA · Studio OS</div>
              </div>
              <div className="text-right text-xs font-mono">
                <div>DATE · {formatDate(new Date())}</div>
                <div>DUE · {formatDate(form.due_date)}</div>
              </div>
            </div>
            <div className="border-t border-b border-[var(--ink)] py-2 grid grid-cols-12 text-[10px] font-mono tracking-widest uppercase font-semibold">
              <div className="col-span-6">Description</div>
              <div className="col-span-2 text-right">Qty</div>
              <div className="col-span-2 text-right">Rate</div>
              <div className="col-span-2 text-right">Amount</div>
            </div>
            {form.items.map((it, i) => (
              <div key={i} className="grid grid-cols-12 py-2 border-b border-[var(--line-soft)] text-sm">
                <div className="col-span-6">{it.description || "—"}</div>
                <div className="col-span-2 text-right font-mono">{it.quantity}</div>
                <div className="col-span-2 text-right font-mono">{Number(it.rate || 0).toLocaleString("en-IN")}</div>
                <div className="col-span-2 text-right font-mono">{((Number(it.quantity) || 0) * (Number(it.rate) || 0)).toLocaleString("en-IN")}</div>
              </div>
            ))}
            <div className="pt-4 space-y-1 text-sm">
              <Row label="Subtotal" val={subtotal} />
              <Row label={`Tax (${form.tax_rate}%)`} val={tax} />
              <div className="border-t border-[var(--ink)] pt-2 mt-2">
                <Row label="Total" val={total} bold />
              </div>
            </div>
            <button type="submit" className="btn-primary w-full justify-center mt-6" data-testid="invoice-submit">
              {editingId ? `Save changes` : `Save ${docType}`}
            </button>
          </div>
        </form>
      )}

      {docType === "invoice" && (
        <div className="flex flex-wrap items-center gap-2">
          {[["all", "All"], ["unpaid", "To collect"], ["partially_paid", "Part paid"], ["paid", "Paid"], ["draft", "Draft"], ["cancelled", "Cancelled"]].map(([id, label]) => (
            <button key={id} type="button" onClick={() => setStatusFilter(id)} data-testid={`invoice-filter-${id}`}
              className={`px-3 py-1.5 text-xs border rounded-full ${statusFilter === id ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--line)]"}`}>
              {label}
            </button>
          ))}
          <input className="input-flat ml-auto min-w-[240px]" placeholder="Search number, client or project" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      )}
      <div className="border border-[var(--line)] overflow-x-auto">
        <table className="w-full min-w-[640px]">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
            <tr className="text-left">
              <Th>Number</Th><Th>Client</Th><Th>Project</Th><Th>Due</Th><Th>Total</Th>
              {docType === "invoice" && <><Th>In collections</Th><Th>Received</Th></>}
              <Th>Status</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rowsPage.map((r) => (
              <tr key={r.id} className="border-b border-[var(--line-soft)] hover:bg-[var(--surface-2)]" data-testid={`${docType}-row-${r.id}`}>
                <Td className="font-mono font-semibold">{r.number}</Td>
                <Td>{r.client_name || "—"}</Td>
                <Td>{r.project_name || "—"}</Td>
                <Td className="font-mono text-xs">{formatDate(r.due_date)}</Td>
                <Td className="font-mono font-semibold">₹{(r.total || 0).toLocaleString("en-IN")}</Td>
                {docType === "invoice" && <>
                  <Td className="font-mono">{planned[r.id]?.planned ? `₹${planned[r.id].planned.toLocaleString("en-IN")}` : "—"}</Td>
                  <Td className="font-mono text-[var(--success)]">{(Number(r.paid_amount || 0) + (planned[r.id]?.received || 0)) > 0
                    ? `₹${(Number(r.paid_amount || 0) + (planned[r.id]?.received || 0)).toLocaleString("en-IN")}` : "—"}</Td>
                </>}
                <Td>
                  {canUpdate && !["paid", "partially_paid"].includes(r.status) ? <select aria-label="Status" className={`status-chip chip-${r.status}`} value={r.status} onChange={(e) => changeStatus(r.id, e.target.value)}>
                    <option value="draft">Draft</option>
                    <option value="sent">Sent to client</option>
                    {r.status === "overdue" && <option value="overdue">Overdue</option>}
                    <option value="cancelled">Cancelled</option>
                  </select> : <span className={`status-chip chip-${r.status}`}>{statusLabel(r.status)}</span>}
                </Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setPreview(r)} className="text-[var(--accent-strong)]" title="Preview"><Eye size={16} /></button>
                    {docType === "invoice" && canRecordPayment && legacyMoney(r) && ["sent", "overdue", "partially_paid"].includes(r.status) && accounts.length > 0 && (
                      <button onClick={() => openPayment(r)} className="text-[var(--success)]" title="Record payment" data-testid={`invoice-pay-${r.id}`}><Money size={16} /></button>
                    )}
                    <RowActions label={`${docType} ${r.number}`} testid={`${docType}-actions-${r.id}`} actions={[
                      { label: "Download PDF", icon: FilePdf, onSelect: () => download(r.id) },
                      { label: "Restate on cash basis", icon: ArrowCounterClockwise, testid: `invoice-restate-${r.id}`,
                        hidden: !(docType === "invoice" && hasPerm("*.*") && r.accrual_journal_id && r.accounting_basis !== "cash"
                                  && !["draft", "cancelled"].includes(r.status)),
                        onSelect: () => restateCashBasis(r) },
                      { label: "Add to Collections Due", icon: Money, testid: `invoice-collect-${r.id}`,
                        hidden: !(docType === "invoice" && canRemind && hasPerm("finance.create") && !legacyMoney(r) && r.status !== "draft" && r.status !== "cancelled"),
                        onSelect: () => addToCollections(r) },
                      { label: "Send payment reminder", icon: BellRinging, testid: `invoice-remind-${r.id}`,
                        hidden: !(docType === "invoice" && canRemind && legacyMoney(r) && ["sent", "overdue", "partially_paid"].includes(r.status) && due(r) > 0),
                        onSelect: () => startReminder({ source_type: "invoice", source_id: r.id, party: r.client_name, outstanding: due(r),
                                                        due_by: r.due_date && r.due_date > dateForInput(new Date()) ? r.due_date : undefined }) },
                      { label: "Edit", icon: PencilSimple, onSelect: () => startEdit(r), testid: `${docType}-edit-${r.id}`,
                        hidden: !(canUpdate && (docType === "quotation" ? r.status !== "paid" : r.status === "draft")) },
                      { divider: true },
                      { label: "Undo latest payment", icon: ArrowCounterClockwise, danger: true, onSelect: () => reverseLatestPayment(r),
                        hidden: !(docType === "invoice" && canCorrectPayment && ["paid", "partially_paid"].includes(r.status) && r.journal_id) },
                      { label: "Delete", icon: Trash, danger: true, onSelect: () => del(r.id, ["paid", "partially_paid"].includes(r.status)),
                        hidden: !canDelete },
                    ]} />
                  </div>
                </Td>
              </tr>
            ))}
            {!loaded && <SkeletonRows cols={docType === "invoice" ? 9 : 7} />}
            {loaded && rows.length === 0 && (
              <EmptyRow cols={docType === "invoice" ? 9 : 7} icon={Receipt} title={`No ${docType}s yet`}
                hint={docType === "invoice" ? "Use New invoice above to bill a client for a project milestone or fee. Money is booked only when you record a collection." : "Use New quotation above to create one for a client."} />
            )}
          </tbody>
        </table>{rowsPager}
      </div>

      {reminderModal}
      {loaded && rows.length > 0 && visibleRows.length === 0 && (
        <p className="text-sm text-[var(--ink-3)] text-center">No invoices match this view.</p>
      )}
      {preview && (
        <PdfPreviewModal path={`/invoices/${preview.id}/pdf`} title={`Invoice ${preview.number || ""}`.trim()}
                         filename={`${preview.number || "invoice"}.pdf`} onClose={() => setPreview(null)} />
      )}
      {paying && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <form onSubmit={recordPayment} className="bg-white border border-[var(--line)] w-full max-w-xl p-5 space-y-4">
            <div className="flex items-start justify-between gap-3"><div><div className="overline">RECORD PAYMENT</div><h2 className="font-display font-bold text-2xl">{paying.number}</h2><div className="text-xs text-[var(--ink-2)]">Outstanding ₹{roundPaise(Math.max(0, Number(paying.total || 0) - Number(paying.paid_amount || 0))).toLocaleString("en-IN")}</div></div><button type="button" className="btn-ghost" onClick={() => setPaying(null)}><X size={16}/></button></div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-xs">Amount<input required min="0.01" max={roundPaise(Math.max(0, Number(paying.total || 0) - Number(paying.paid_amount || 0)))} step="0.01" type="number" className="input-flat mt-1 w-full" value={payment.amount} onChange={(e) => setPayment({ ...payment, amount: e.target.value })}/></label>
              <label className="text-xs">Payment date<input required type="date" className="input-flat mt-1 w-full" value={payment.date} onChange={(e) => setPayment({ ...payment, date: e.target.value })}/></label>
              <label className="text-xs">Method<select className="input-flat mt-1 w-full" value={payment.payment_method} onChange={(e) => { const method = e.target.value; const compatible = compatibleAccount(accounts, method); setPayment({ ...payment, payment_method: method, bank_account_id: compatible?.id || payment.bank_account_id }); }}><option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="credit_card">Credit card</option><option value="online">Online</option><option value="cash">Cash</option><option value="other">Other</option></select></label>
              <label className="text-xs">Received into<SearchSelect required className="input-flat mt-1 w-full" value={payment.bank_account_id} onChange={(e) => { const account = accounts.find((a) => a.id === e.target.value); setPayment({ ...payment, bank_account_id: e.target.value, payment_method: methodForAccount(account) }); }}><option value="">Select Cash / Bank</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</SearchSelect></label>
              <label className="text-xs sm:col-span-2">Reference<input className="input-flat mt-1 w-full" value={payment.reference} onChange={(e) => setPayment({ ...payment, reference: e.target.value })}/></label>
            </div>
            <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={() => setPaying(null)}>Cancel</button><button className="btn-primary" disabled={paymentBusy}>{paymentBusy ? "Recording…" : "Record payment"}</button></div>
          </form>
        </div>
      )}
    </div>
  );
}

const Th = ({ children }) => <th className="px-4 py-3 overline">{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
const Row = ({ label, val, bold }) => (
  <div className="flex items-center justify-between">
    <div className={`${bold ? "font-display font-bold text-lg" : "text-[var(--ink-2)]"}`}>{label}</div>
    <div className={`font-mono ${bold ? "font-display font-bold text-lg" : ""}`}>₹{Number(val || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
  </div>
);
