import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  ArrowLeft, Star, Buildings, Phone, Envelope, MapPin, Bank as BankIcon,
  IdentificationCard, CurrencyInr, Plus, Trash, FileText, Gauge, Receipt,
  PaperPlaneTilt, ShieldCheck, Notepad, Certificate, Wrench,
  Handshake, Percent, TrendUp,
} from "@phosphor-icons/react";

const INR = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(n || 0));
const INR_D = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(n || 0));

const TABS = ["overview", "commercial", "ledger", "bills", "payments", "commissions", "projects", "documents", "performance"];

export default function VendorDetail() {
  const { id } = useParams();
  const { hasPerm } = useAuth();
  const [v, setV] = useState(null);
  const [tab, setTab] = useState("overview");
  const [ledger, setLedger] = useState(null);
  const [perf, setPerf] = useState(null);
  const [commissionLedger, setCommissionLedger] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [{ data }, { data: acc }] = await Promise.all([
      api.get(`/vendors/${id}`),
      hasPerm("finance.read") ? api.get("/accounts") : Promise.resolve({ data: [] }),
    ]);
    setV(data);
    setAccounts(acc);
  }, [id, hasPerm]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (tab === "ledger") api.get(`/vendors/${id}/ledger`).then(({ data }) => setLedger(data));
    if (tab === "performance") api.get(`/vendors/${id}/performance`).then(({ data }) => setPerf(data));
    if (tab === "commissions" || tab === "commercial") {
      api.get(`/vendors/${id}/commission-ledger`).then(({ data }) => setCommissionLedger(data));
    }
  }, [tab, id]);

  const saveCommercial = async (cfg) => {
    setBusy(true);
    try {
      await api.patch(`/vendors/${id}/commercial`, cfg);
      const { data } = await api.get(`/vendors/${id}/commission-ledger`);
      setCommissionLedger(data);
      await load();
    } finally { setBusy(false); }
  };
  const receiveCommission = async (form) => {
    setBusy(true);
    try {
      await api.post(`/vendors/${id}/commissions/receive`, form);
      const { data } = await api.get(`/vendors/${id}/commission-ledger`);
      setCommissionLedger(data);
    } finally { setBusy(false); }
  };

  const canBill = hasPerm("finance.create");

  const submitBill = async (form) => {
    setBusy(true);
    try { await api.post("/vendor-bills", { ...form, vendor_id: id }); await load(); }
    finally { setBusy(false); }
  };
  const submitPayment = async (form) => {
    setBusy(true);
    try { await api.post("/vendor-payments", { ...form, vendor_id: id }); await load(); }
    finally { setBusy(false); }
  };
  const submitRating = async (form) => {
    setBusy(true);
    try { await api.post(`/vendors/${id}/rate`, form); await load(); }
    finally { setBusy(false); }
  };
  const addDoc = async (form) => {
    setBusy(true);
    try { await api.post(`/vendors/${id}/documents`, form); await load(); }
    finally { setBusy(false); }
  };
  const delDoc = async (docId) => {
    if (!window.confirm("Remove this document?")) return;
    await api.delete(`/vendors/${id}/documents/${docId}`); await load();
  };

  if (!v) {
    return <div className="overline">LOADING VENDOR…</div>;
  }

  const s = v.summary || {};

  return (
    <div className="space-y-6" data-testid="vendor-detail-page">
      {/* HEADER */}
      <div>
        <Link to="/vendors" className="text-xs text-[#5C5C5C] hover:text-[#002FA7] flex items-center gap-1">
          <ArrowLeft size={12} /> All vendors
        </Link>
        <div className="mt-3 flex items-start justify-between gap-6 flex-wrap">
          <div>
            <div className="overline mb-1">
              {v.agency_type?.toUpperCase().replace("_", " ") || "VENDOR"} · {v.category || "UNCATEGORISED"}
            </div>
            <h1 className="font-display font-bold tracking-tight text-4xl">{v.name}</h1>
            {v.company && <div className="text-[#5C5C5C] mt-1">{v.company}</div>}
          </div>
          <div className="flex items-center gap-2">
            <div className="px-3 py-2 border border-[#E5E5E5]">
              <div className="overline text-[9px]">RATING</div>
              <div className="flex items-center gap-1">
                <Star size={14} weight="fill" className="text-[#F5B800]" />
                <span className="font-display font-bold text-lg">{Number(v.rating || 0).toFixed(1)}</span>
                <span className="text-xs text-[#9A9A9A]">/ 5 · {v.rating_count || 0} ratings</span>
              </div>
            </div>
            <div className="px-3 py-2 border border-[#E5E5E5]">
              <div className="overline text-[9px]">OUTSTANDING</div>
              <div className={`font-display font-bold text-lg ${s.outstanding > 0 ? "text-[#B22B22]" : ""}`}>
                {INR(s.outstanding || 0)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* KPI ROW */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Total billed" value={INR(s.total_billed || 0)} />
        <Kpi label="Total paid" value={INR(s.total_paid || 0)} />
        <Kpi label="Open bills" value={s.open_bills || 0} />
        <Kpi label="Assigned tasks" value={s.task_count || 0} />
        <Kpi label="Projects touched" value={s.project_count || 0} />
      </div>

      {/* TABS */}
      <div className="flex items-center gap-1 border-b border-[#E5E5E5] overflow-x-auto no-scrollbar">
        {TABS.map((t) => (
          <button
            key={t}
            data-testid={`vendor-tab-${t}`}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-xs font-mono uppercase tracking-wider transition ${
              tab === t
                ? "text-[#002FA7] border-b-2 border-[#002FA7] -mb-px"
                : "text-[#5C5C5C] hover:text-[#0A0A0A]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* TAB PANELS */}
      {tab === "overview" && <Overview v={v} onRate={submitRating} busy={busy} canRate={hasPerm("vendors.update")} />}
      {tab === "commercial" && (
        <Commercial ledger={commissionLedger} vendor={v}
          canEdit={hasPerm("vendors.update")}
          onSave={saveCommercial} busy={busy} />
      )}
      {tab === "ledger" && <Ledger data={ledger} />}
      {tab === "bills" && (
        <Bills v={v} accounts={accounts} canBill={canBill} onCreate={submitBill} busy={busy} />
      )}
      {tab === "payments" && (
        <Payments v={v} accounts={accounts} canBill={canBill} onCreate={submitPayment} busy={busy} />
      )}
      {tab === "commissions" && (
        <Commissions ledger={commissionLedger} accounts={accounts}
          canReceive={hasPerm("finance.create")}
          onReceive={receiveCommission} busy={busy} />
      )}
      {tab === "projects" && <ProjectsTasks v={v} />}
      {tab === "documents" && (
        <Documents v={v} canEdit={hasPerm("vendors.update")} onAdd={addDoc} onDelete={delDoc} busy={busy} />
      )}
      {tab === "performance" && <Performance perf={perf} />}
    </div>
  );
}

/* -------------------- OVERVIEW -------------------- */
function Overview({ v, onRate, busy, canRate }) {
  const [r, setR] = useState({ quality: 4, timeliness: 4, cost: 4, communication: 4, comment: "" });
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="md:col-span-2 space-y-4">
        <Card title="Identity">
          <Field icon={<IdentificationCard size={13} />} label="Contact person" value={v.contact_person} />
          <Field icon={<Phone size={13} />} label="Phone" value={v.phone} mono />
          <Field icon={<Envelope size={13} />} label="Email" value={v.email} />
          <Field icon={<MapPin size={13} />} label="Address"
            value={[v.address, v.city, v.state, v.pincode].filter(Boolean).join(", ")} />
        </Card>

        <Card title="Compliance">
          <Field icon={<ShieldCheck size={13} />} label="GSTIN" value={v.gstin} mono />
          <Field icon={<ShieldCheck size={13} />} label="PAN" value={v.pan} mono />
          <Field icon={<Certificate size={13} />} label="TDS"
            value={v.tds_applicable ? `Applicable · ${v.tds_rate || 0}%` : "Not applicable"} />
        </Card>

        <Card title="Banking">
          <Field icon={<BankIcon size={13} />} label="Bank" value={v.bank_name} />
          <Field icon={<BankIcon size={13} />} label="A/C number" value={v.bank_account_number} mono />
          <Field icon={<BankIcon size={13} />} label="IFSC" value={v.bank_ifsc} mono />
          <Field icon={<BankIcon size={13} />} label="Branch" value={v.bank_branch} />
          <Field icon={<CurrencyInr size={13} />} label="UPI" value={v.upi_id} mono />
        </Card>

        {v.notes && (
          <Card title="Notes">
            <p className="text-sm whitespace-pre-wrap">{v.notes}</p>
          </Card>
        )}
      </div>

      {canRate && (
        <Card title="Rate this vendor">
          <div className="space-y-3">
            {["quality", "timeliness", "cost", "communication"].map((k) => (
              <div key={k}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="capitalize">{k}</span>
                  <span className="font-mono">{r[k]}</span>
                </div>
                <input type="range" min={0} max={5} step={0.5}
                  value={r[k]} onChange={(e) => setR({ ...r, [k]: parseFloat(e.target.value) })}
                  className="w-full accent-[#002FA7]" data-testid={`rate-${k}`} />
              </div>
            ))}
            <textarea className="input-flat w-full min-h-[60px]" placeholder="Optional comment"
              value={r.comment} onChange={(e) => setR({ ...r, comment: e.target.value })} />
            <button disabled={busy} onClick={() => onRate(r)} className="btn-primary w-full" data-testid="submit-rating-btn">
              <Star size={13} /> {busy ? "Saving…" : "Save rating"}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}

/* -------------------- LEDGER -------------------- */
function Ledger({ data }) {
  if (!data) return <div className="overline">LOADING…</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Kpi label="Total billed" value={INR(data.total_billed)} />
        <Kpi label="Total paid" value={INR(data.total_paid)} />
        <Kpi label="Closing balance" value={INR(data.outstanding)} accent={data.outstanding > 0} />
      </div>
      <div className="border border-[#E5E5E5]">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5] text-left">
            <tr>
              <Th>Date</Th><Th>Type</Th><Th>Reference</Th><Th>Narration</Th>
              <Th className="text-right">Debit</Th><Th className="text-right">Credit</Th>
              <Th className="text-right">Balance</Th>
            </tr>
          </thead>
          <tbody>
            {data.entries.length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-[#9A9A9A]">No transactions yet.</td></tr>
            )}
            {data.entries.map((e, i) => (
              <tr key={i} className="border-b border-[#F0F0F0]" data-testid={`ledger-row-${i}`}>
                <Td className="font-mono text-xs">{e.date}</Td>
                <Td>
                  <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 ${
                    e.type === "bill" ? "bg-[#FCEEEC] text-[#B22B22]" : "bg-[#EFF7EF] text-[#1D633E]"
                  }`}>{e.type}</span>
                </Td>
                <Td className="font-mono text-xs">{e.ref}</Td>
                <Td>{e.narration}</Td>
                <Td className="text-right font-mono">{e.debit ? INR_D(e.debit) : "—"}</Td>
                <Td className="text-right font-mono">{e.credit ? INR_D(e.credit) : "—"}</Td>
                <Td className="text-right font-mono font-semibold">{INR(e.balance)}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* -------------------- BILLS -------------------- */
function Bills({ v, canBill, onCreate, busy }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ bill_date: today(), due_date: "", items: [emptyItem()], tax_rate: 18, tds_rate: 0, notes: "", project_id: "" });
  const total = useMemo(() => {
    const sub = f.items.reduce((s, it) => s + Number(it.quantity || 0) * Number(it.rate || 0), 0);
    return sub + sub * f.tax_rate / 100 - sub * f.tds_rate / 100;
  }, [f]);

  return (
    <div className="space-y-4">
      {canBill && (
        <div>
          <button onClick={() => setOpen(!open)} className="btn-primary" data-testid="new-bill-btn">
            <Plus size={14} /> {open ? "Cancel" : "Record bill"}
          </button>
        </div>
      )}
      {open && (
        <form
          className="card-flat space-y-3"
          onSubmit={(e) => { e.preventDefault(); onCreate(f); setOpen(false); setF({ ...f, items: [emptyItem()] }); }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <input required type="date" className="input-flat" value={f.bill_date}
              onChange={(e) => setF({ ...f, bill_date: e.target.value })} data-testid="bf-date" />
            <input type="date" className="input-flat" placeholder="Due date" value={f.due_date}
              onChange={(e) => setF({ ...f, due_date: e.target.value })} />
            <input type="number" step="0.01" className="input-flat" placeholder="GST %" value={f.tax_rate}
              onChange={(e) => setF({ ...f, tax_rate: parseFloat(e.target.value) || 0 })} />
            <input type="number" step="0.01" className="input-flat" placeholder="TDS %" value={f.tds_rate}
              onChange={(e) => setF({ ...f, tds_rate: parseFloat(e.target.value) || 0 })} />
          </div>
          <div className="space-y-2">
            {f.items.map((it, i) => (
              <div key={i} className="grid grid-cols-12 gap-2">
                <input required className="input-flat col-span-6" placeholder="Item description"
                  value={it.description} onChange={(e) => updateItem(f, setF, i, "description", e.target.value)} />
                <input required type="number" step="0.01" className="input-flat col-span-2" placeholder="Qty"
                  value={it.quantity} onChange={(e) => updateItem(f, setF, i, "quantity", parseFloat(e.target.value) || 0)} />
                <input required type="number" step="0.01" className="input-flat col-span-3" placeholder="Rate"
                  value={it.rate} onChange={(e) => updateItem(f, setF, i, "rate", parseFloat(e.target.value) || 0)} />
                <button type="button" onClick={() => removeItem(f, setF, i)} className="btn-ghost col-span-1" aria-label="remove">
                  <Trash size={12} />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => setF({ ...f, items: [...f.items, emptyItem()] })} className="btn-ghost text-xs">
              <Plus size={12} /> Add line
            </button>
          </div>
          <textarea className="input-flat w-full min-h-[50px]" placeholder="Notes"
            value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          <div className="flex items-center justify-between pt-2 border-t border-[#E5E5E5]">
            <div className="overline">TOTAL</div>
            <div className="font-display font-bold text-2xl text-[#002FA7]">{INR(total)}</div>
          </div>
          <button disabled={busy} className="btn-primary" data-testid="save-bill-btn">
            <Receipt size={13} /> {busy ? "Saving…" : "Save bill"}
          </button>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5] text-left">
            <tr>
              <Th>Number</Th><Th>Bill date</Th><Th>Due</Th><Th>Status</Th>
              <Th className="text-right">Total</Th><Th className="text-right">Paid</Th><Th className="text-right">Outstanding</Th>
            </tr>
          </thead>
          <tbody>
            {(v.bills || []).length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-[#9A9A9A]">No bills yet.</td></tr>
            )}
            {(v.bills || []).map((b) => (
              <tr key={b.id} className="border-b border-[#F0F0F0]" data-testid={`bill-row-${b.id}`}>
                <Td className="font-mono text-xs">{b.bill_number}</Td>
                <Td>{b.bill_date}</Td>
                <Td>{b.due_date || "—"}</Td>
                <Td><BillStatus s={b.status} /></Td>
                <Td className="text-right font-mono">{INR_D(b.total)}</Td>
                <Td className="text-right font-mono text-[#1D633E]">{INR_D(b.paid_amount || 0)}</Td>
                <Td className="text-right font-mono text-[#B22B22]">{INR_D(b.outstanding || 0)}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BillStatus({ s }) {
  const map = {
    draft: "bg-[#F2F2F2] text-[#5C5C5C]",
    received: "bg-[#EEF2FF] text-[#002FA7]",
    partially_paid: "bg-[#FFF4E5] text-[#7A4E1A]",
    paid: "bg-[#EFF7EF] text-[#1D633E]",
    overdue: "bg-[#FCEEEC] text-[#B22B22]",
    cancelled: "bg-[#F2F2F2] text-[#9A9A9A]",
  };
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 ${map[s] || map.draft}`}>
      {(s || "draft").replace("_", " ")}
    </span>
  );
}

/* -------------------- PAYMENTS -------------------- */
function Payments({ v, accounts, canBill, onCreate, busy }) {
  const [open, setOpen] = useState(false);
  const bankAccounts = accounts.filter((a) => a.is_bank || a.name?.toLowerCase().includes("cash"));
  const [f, setF] = useState({
    amount: 0, payment_date: today(), paid_from_account_id: "",
    payment_method: "bank_transfer", reference: "", notes: "", bill_ids: [],
  });

  useEffect(() => {
    if (!f.paid_from_account_id && bankAccounts[0]) {
      setF((s) => ({ ...s, paid_from_account_id: bankAccounts[0].id }));
    }
    // eslint-disable-next-line
  }, [accounts.length]);

  const openBills = (v.bills || []).filter((b) => ["received", "partially_paid", "overdue"].includes(b.status));

  return (
    <div className="space-y-4">
      {canBill && (
        <div>
          <button onClick={() => setOpen(!open)} className="btn-primary" data-testid="new-payment-btn">
            <Plus size={14} /> {open ? "Cancel" : "Record payment"}
          </button>
          {!canBill && (
            <span className="text-xs text-[#9A9A9A] ml-2">Only finance roles can record payments.</span>
          )}
        </div>
      )}
      {open && (
        <form
          className="card-flat space-y-3"
          onSubmit={(e) => { e.preventDefault(); onCreate(f); setOpen(false); setF({ ...f, amount: 0, reference: "", notes: "", bill_ids: [] }); }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <input required type="number" step="0.01" className="input-flat" placeholder="Amount *"
              value={f.amount} onChange={(e) => setF({ ...f, amount: parseFloat(e.target.value) || 0 })} data-testid="pf-amount" />
            <input required type="date" className="input-flat" value={f.payment_date}
              onChange={(e) => setF({ ...f, payment_date: e.target.value })} />
            <select required className="input-flat" value={f.paid_from_account_id}
              onChange={(e) => setF({ ...f, paid_from_account_id: e.target.value })} data-testid="pf-bank">
              <option value="">Paid from…</option>
              {bankAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <select className="input-flat" value={f.payment_method}
              onChange={(e) => setF({ ...f, payment_method: e.target.value })}>
              {["bank_transfer","upi","cash","cheque","credit_card","online","other"].map((m) => (
                <option key={m} value={m}>{m.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <input className="input-flat w-full" placeholder="Reference (UTR / cheque # / txn id)"
            value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} />
          {openBills.length > 0 && (
            <div className="border border-[#E5E5E5] p-3 space-y-1">
              <div className="overline">Settle bills (optional — FIFO if empty)</div>
              {openBills.map((b) => (
                <label key={b.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.bill_ids.includes(b.id)}
                    onChange={(e) => {
                      setF({ ...f, bill_ids: e.target.checked
                        ? [...f.bill_ids, b.id]
                        : f.bill_ids.filter((x) => x !== b.id) });
                    }} />
                  <span className="font-mono text-xs">{b.bill_number}</span>
                  <span className="text-[#9A9A9A]">·</span>
                  <span>{b.bill_date}</span>
                  <span className="ml-auto font-mono">{INR_D(b.outstanding || b.total)}</span>
                </label>
              ))}
            </div>
          )}
          <button disabled={busy} className="btn-primary" data-testid="save-payment-btn">
            <PaperPlaneTilt size={13} /> {busy ? "Saving…" : "Record payment"}
          </button>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5] text-left">
            <tr>
              <Th>Date</Th><Th>Method</Th><Th>Reference</Th>
              <Th className="text-right">Amount</Th><Th>Settled bills</Th>
            </tr>
          </thead>
          <tbody>
            {(v.payments || []).length === 0 && (
              <tr><td colSpan={5} className="p-8 text-center text-[#9A9A9A]">No payments recorded.</td></tr>
            )}
            {(v.payments || []).map((p) => (
              <tr key={p.id} className="border-b border-[#F0F0F0]" data-testid={`payment-row-${p.id}`}>
                <Td className="font-mono text-xs">{p.payment_date}</Td>
                <Td>{(p.payment_method || "").replace("_", " ")}</Td>
                <Td className="font-mono text-xs">{p.reference || "—"}</Td>
                <Td className="text-right font-mono font-semibold text-[#1D633E]">{INR_D(p.amount)}</Td>
                <Td className="text-xs font-mono">
                  {(p.bill_ids || []).length ? p.bill_ids.length + " bill(s)" : "on-account"}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* -------------------- PROJECTS & TASKS -------------------- */
function ProjectsTasks({ v }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card title={`Projects (${(v.projects || []).length})`}>
        <div className="space-y-2">
          {(v.projects || []).length === 0 && <div className="text-sm text-[#9A9A9A]">No projects linked yet.</div>}
          {(v.projects || []).map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="flex justify-between items-center border-b border-[#F0F0F0] pb-2 hover:text-[#002FA7]">
              <div>
                <div className="text-sm font-semibold">{p.name}</div>
                <div className="text-xs text-[#9A9A9A]">{p.client_name || "—"}</div>
              </div>
              <span className="text-[10px] font-mono uppercase text-[#5C5C5C]">{p.stage}</span>
            </Link>
          ))}
        </div>
      </Card>
      <Card title={`Assigned tasks (${(v.tasks || []).length})`}>
        <div className="space-y-2">
          {(v.tasks || []).length === 0 && <div className="text-sm text-[#9A9A9A]">No tasks assigned.</div>}
          {(v.tasks || []).slice(0, 20).map((t) => (
            <Link key={t.id} to={`/tasks/${t.id}`} className="flex items-start justify-between gap-3 border-b border-[#F0F0F0] pb-2 hover:text-[#002FA7]">
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">{t.title}</div>
                <div className="text-xs text-[#9A9A9A]">
                  {t.category || "—"} · due {t.due_date || "—"}
                </div>
              </div>
              <span className="text-[10px] font-mono uppercase text-[#5C5C5C] shrink-0">
                {t.status_detail || t.status}
              </span>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* -------------------- DOCUMENTS -------------------- */
function Documents({ v, canEdit, onAdd, onDelete, busy }) {
  const [f, setF] = useState({ label: "", url: "", kind: "gst_certificate", expires_on: "" });
  return (
    <div className="space-y-4">
      {canEdit && (
        <form className="card-flat grid grid-cols-1 md:grid-cols-5 gap-2"
          onSubmit={(e) => { e.preventDefault(); onAdd(f); setF({ label: "", url: "", kind: "gst_certificate", expires_on: "" }); }}
        >
          <input required className="input-flat md:col-span-2" placeholder="Label"
            value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
          <input required className="input-flat md:col-span-2" placeholder="File URL"
            value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
          <select className="input-flat" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            {["gst_certificate", "pan", "agreement", "insurance", "cheque_leaf", "other"].map((k) => (
              <option key={k} value={k}>{k.replace("_", " ")}</option>
            ))}
          </select>
          <button disabled={busy} className="btn-primary md:col-span-5" data-testid="add-doc-btn">
            <Plus size={13} /> Attach document
          </button>
        </form>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {(v.documents || []).length === 0 && (
          <div className="text-sm text-[#9A9A9A] col-span-2">No documents on file.</div>
        )}
        {(v.documents || []).map((d) => (
          <div key={d.id} className="border border-[#E5E5E5] p-4 flex items-start gap-3">
            <FileText size={22} className="text-[#002FA7]" />
            <div className="flex-1 min-w-0">
              <a href={d.url} target="_blank" rel="noreferrer" className="font-semibold text-sm hover:text-[#002FA7] break-all">
                {d.label}
              </a>
              <div className="text-xs text-[#9A9A9A] font-mono">
                {d.kind?.replace("_", " ")} {d.expires_on ? `· expires ${d.expires_on}` : ""}
              </div>
            </div>
            {canEdit && (
              <button onClick={() => onDelete(d.id)} className="btn-ghost" aria-label="remove">
                <Trash size={13} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* -------------------- PERFORMANCE -------------------- */
function Performance({ perf }) {
  if (!perf) return <div className="overline">CALCULATING…</div>;
  const score = perf.performance_score;
  const scoreColor = score >= 75 ? "text-[#1D633E]" : score >= 50 ? "text-[#7A4E1A]" : "text-[#B22B22]";
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card title="Overall performance">
        <div className="flex items-center gap-3">
          <Gauge size={48} className={scoreColor} weight="duotone" />
          <div>
            <div className={`font-display font-bold text-5xl ${scoreColor}`}>{score}</div>
            <div className="text-xs font-mono uppercase tracking-wider text-[#5C5C5C]">out of 100</div>
          </div>
        </div>
        <p className="text-xs text-[#5C5C5C] mt-3">
          Weighted from task completion (30%), on-time delivery (25%), quality ratings (35%) and payment reliability (10%).
        </p>
      </Card>
      <Card title="Task execution">
        <Row label="Total tasks" value={perf.tasks.total} />
        <Row label="Completed" value={perf.tasks.done} />
        <Row label="Open" value={perf.tasks.open} />
        <Row label="Delayed" value={perf.tasks.delayed} accent={perf.tasks.delayed > 0} />
        <Row label="Completion rate" value={perf.tasks.completion_rate + "%"} />
        <Row label="Delay rate" value={perf.tasks.delay_rate + "%"} accent={perf.tasks.delay_rate > 15} />
      </Card>
      <Card title="Client-facing ratings">
        <Row label="Quality" value={perf.ratings.quality ?? "—"} />
        <Row label="Timeliness" value={perf.ratings.timeliness ?? "—"} />
        <Row label="Cost" value={perf.ratings.cost ?? "—"} />
        <Row label="Communication" value={perf.ratings.communication ?? "—"} />
        <Row label="Overall (avg)" value={perf.ratings.overall} />
        <Row label="Ratings" value={perf.ratings.count} />
      </Card>
      <Card title="Payment reliability">
        <Row label="Total billed" value={INR(perf.financial.total_billed)} />
        <Row label="Outstanding" value={INR(perf.financial.outstanding)} accent={perf.financial.outstanding > 0} />
        <Row label="Reliability" value={perf.financial.payment_reliability + "%"} />
      </Card>
    </div>
  );
}

/* -------------------- COMMERCIAL (commission config) -------------------- */
function Commercial({ ledger, vendor, canEdit, onSave, busy }) {
  const cfg = (vendor && vendor.commission) || { applicable: false, type: "percentage", percentage: 0 };
  const [f, setF] = useState({
    applicable: !!cfg.applicable,
    type: cfg.type || "percentage",
    percentage: cfg.percentage || 0,
    fixed_amount: cfg.fixed_amount || 0,
    slabs: cfg.slabs || [{ min_purchase: 0, max_purchase: null, percentage: 0 }],
    min_purchase: cfg.min_purchase || 0,
    effective_from: cfg.effective_from || "",
    effective_to: cfg.effective_to || "",
    notes: cfg.notes || "",
    income_label: cfg.income_label || "Vendor Commission Income",
  });

  const setSlab = (i, k, v) => {
    const slabs = [...f.slabs];
    slabs[i] = { ...slabs[i], [k]: v };
    setF({ ...f, slabs });
  };
  const addSlab = () => setF({ ...f, slabs: [...f.slabs,
    { min_purchase: 0, max_purchase: null, percentage: 0 }] });
  const rmSlab = (i) => setF({ ...f, slabs: f.slabs.filter((_, x) => x !== i) });

  const t = f.type;
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="commercial-tab">
      <div className="md:col-span-2 space-y-4">
        <Card title="Commission agreement">
          <label className="flex items-center gap-2 text-sm mb-3">
            <input
              data-testid="cm-applicable"
              type="checkbox" checked={f.applicable}
              onChange={(e) => setF({ ...f, applicable: e.target.checked })}
            />
            This vendor pays us a commission / incentive
          </label>

          <div className={f.applicable ? "" : "opacity-50 pointer-events-none"}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <select data-testid="cm-type" className="input-flat" value={t}
                onChange={(e) => setF({ ...f, type: e.target.value })}>
                <option value="percentage">Percentage of purchase</option>
                <option value="fixed">Fixed amount per bill</option>
                <option value="slab">Purchase-slab based</option>
                <option value="category">Product-category based</option>
                <option value="project">Project-specific override</option>
                <option value="none">Disabled</option>
              </select>
              {t === "percentage" && (
                <input type="number" step="0.01" min="0" data-testid="cm-pct"
                  className="input-flat" placeholder="Percentage %"
                  value={f.percentage}
                  onChange={(e) => setF({ ...f, percentage: parseFloat(e.target.value) || 0 })} />
              )}
              {t === "fixed" && (
                <input type="number" step="0.01" min="0" data-testid="cm-fixed"
                  className="input-flat" placeholder="Fixed ₹ per bill"
                  value={f.fixed_amount}
                  onChange={(e) => setF({ ...f, fixed_amount: parseFloat(e.target.value) || 0 })} />
              )}
              <input type="number" step="0.01" min="0" className="input-flat"
                placeholder="Min purchase to earn (₹)"
                value={f.min_purchase}
                onChange={(e) => setF({ ...f, min_purchase: parseFloat(e.target.value) || 0 })} />
              <input type="date" className="input-flat" placeholder="Effective from"
                value={f.effective_from}
                onChange={(e) => setF({ ...f, effective_from: e.target.value })} />
              <input type="date" className="input-flat" placeholder="Effective to"
                value={f.effective_to}
                onChange={(e) => setF({ ...f, effective_to: e.target.value })} />
              <input className="input-flat" placeholder="Income category label"
                value={f.income_label}
                onChange={(e) => setF({ ...f, income_label: e.target.value })} />
            </div>

            {t === "slab" && (
              <div className="mt-4 border border-[#E5E5E5] p-3">
                <div className="overline mb-2">SLABS</div>
                {f.slabs.map((s, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                    <input type="number" step="0.01" className="input-flat col-span-4"
                      placeholder="From (₹)" value={s.min_purchase}
                      onChange={(e) => setSlab(i, "min_purchase", parseFloat(e.target.value) || 0)} />
                    <input type="number" step="0.01" className="input-flat col-span-4"
                      placeholder="To (₹) — blank = ∞" value={s.max_purchase ?? ""}
                      onChange={(e) => setSlab(i, "max_purchase", e.target.value === "" ? null : parseFloat(e.target.value))} />
                    <input type="number" step="0.01" className="input-flat col-span-3"
                      placeholder="Rate %" value={s.percentage}
                      onChange={(e) => setSlab(i, "percentage", parseFloat(e.target.value) || 0)} />
                    <button type="button" onClick={() => rmSlab(i)} className="btn-ghost col-span-1"><Trash size={12} /></button>
                  </div>
                ))}
                <button type="button" onClick={addSlab} className="btn-ghost text-xs">
                  <Plus size={12} /> Add slab
                </button>
              </div>
            )}

            <textarea className="input-flat w-full min-h-[60px] mt-3" placeholder="Notes"
              value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </div>

          {canEdit && (
            <button
              disabled={busy}
              onClick={() => onSave(f)}
              className="btn-primary mt-4" data-testid="cm-save"
            >
              <Handshake size={13} /> {busy ? "Saving…" : "Save & recompute commissions"}
            </button>
          )}
        </Card>
      </div>

      <div className="space-y-3">
        <Card title="Commission summary">
          {ledger?.totals ? (
            <>
              <Row label="Total purchase" value={INR(ledger.totals.total_purchase)} />
              <Row label="Total earned" value={INR(ledger.totals.total_earned)} />
              <Row label="Received" value={INR(ledger.totals.total_received)} />
              <Row label="Pending" value={INR(ledger.totals.pending)} accent={ledger.totals.pending > 0} />
            </>
          ) : (
            <div className="text-sm text-[#5C5C5C]">Save the config to see numbers.</div>
          )}
        </Card>
        <Card title="How it works">
          <p className="text-xs text-[#5C5C5C]">
            Whenever a bill is recorded against this vendor, we auto-book the earned commission.
            Mark it received in the <b>Commissions</b> tab and we'll post an Income journal entry
            (DR Bank · CR Commission Income) — it flows straight into P&amp;L, Cash Flow and the Dashboard.
          </p>
        </Card>
      </div>
    </div>
  );
}

/* -------------------- COMMISSIONS (list + receive) -------------------- */
function Commissions({ ledger, accounts, canReceive, onReceive, busy }) {
  const bankAccounts = accounts.filter((a) => a.is_bank || a.name?.toLowerCase().includes("cash"));
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({
    amount: 0, received_date: today(), bank_account_id: "",
    payment_method: "bank_transfer", reference: "", notes: "", commission_ids: [],
  });
  useEffect(() => {
    if (!f.bank_account_id && bankAccounts[0]) {
      setF((s) => ({ ...s, bank_account_id: bankAccounts[0].id }));
    }
    // eslint-disable-next-line
  }, [accounts.length]);

  if (!ledger) return <div className="overline">LOADING…</div>;
  const openRows = (ledger.entries || []).filter((r) => ["pending", "invoiced"].includes(r.status));

  return (
    <div className="space-y-4" data-testid="commissions-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Total purchase" value={INR(ledger.totals.total_purchase)} />
        <Kpi label="Earned" value={INR(ledger.totals.total_earned)} accent />
        <Kpi label="Received" value={INR(ledger.totals.total_received)} />
        <Kpi label="Pending" value={INR(ledger.totals.pending)} accent={ledger.totals.pending > 0} />
      </div>

      {canReceive && (
        <div>
          <button onClick={() => setOpen(!open)} className="btn-primary" data-testid="receive-cm-btn">
            <Plus size={14} /> {open ? "Cancel" : "Record commission received"}
          </button>
        </div>
      )}
      {open && (
        <form
          className="card-flat space-y-3"
          onSubmit={(e) => { e.preventDefault(); onReceive(f); setOpen(false); setF({ ...f, amount: 0, reference: "", notes: "", commission_ids: [] }); }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <input required type="number" step="0.01" className="input-flat" placeholder="Amount *"
              data-testid="rcm-amount"
              value={f.amount} onChange={(e) => setF({ ...f, amount: parseFloat(e.target.value) || 0 })} />
            <input required type="date" className="input-flat" value={f.received_date}
              onChange={(e) => setF({ ...f, received_date: e.target.value })} />
            <select required className="input-flat" value={f.bank_account_id}
              data-testid="rcm-bank"
              onChange={(e) => setF({ ...f, bank_account_id: e.target.value })}>
              <option value="">Deposited to…</option>
              {bankAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <select className="input-flat" value={f.payment_method}
              onChange={(e) => setF({ ...f, payment_method: e.target.value })}>
              {["bank_transfer","upi","cash","cheque","credit_card","online","other"].map((m) => (
                <option key={m} value={m}>{m.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <input className="input-flat w-full" placeholder="Reference (UTR / cheque #)"
            value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} />

          {openRows.length > 0 && (
            <div className="border border-[#E5E5E5] p-3 space-y-1">
              <div className="overline">Settle specific commissions (optional — FIFO if empty)</div>
              {openRows.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.commission_ids.includes(r.id)}
                    onChange={(e) => {
                      setF({ ...f, commission_ids: e.target.checked
                        ? [...f.commission_ids, r.id]
                        : f.commission_ids.filter((x) => x !== r.id) });
                    }} />
                  <span className="font-mono text-xs">{r.bill_number}</span>
                  <span className="text-[#9A9A9A]">·</span>
                  <span>{r.bill_date}</span>
                  <span className="ml-auto font-mono">{INR_D(r.amount - (r.received_amount || 0))} due</span>
                </label>
              ))}
            </div>
          )}
          <button disabled={busy} className="btn-primary" data-testid="rcm-submit">
            <TrendUp size={13} /> {busy ? "Posting…" : "Book as Income"}
          </button>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5] text-left">
            <tr>
              <Th>Bill date</Th><Th>Bill</Th><Th className="text-right">Purchase</Th>
              <Th>Type</Th><Th className="text-right">Earned</Th>
              <Th className="text-right">Received</Th><Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {(ledger.entries || []).length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-[#9A9A9A]">
                No commissions yet. Post a bill and it'll auto-compute.
              </td></tr>
            )}
            {(ledger.entries || []).map((r) => (
              <tr key={r.id} className="border-b border-[#F0F0F0]" data-testid={`cm-row-${r.id}`}>
                <Td className="font-mono text-xs">{r.bill_date}</Td>
                <Td className="font-mono text-xs">{r.bill_number}</Td>
                <Td className="text-right font-mono">{INR_D(r.purchase_amount)}</Td>
                <Td>
                  <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 bg-[#F2F2F2]">
                    {r.commission_type}
                  </span>
                </Td>
                <Td className="text-right font-mono">{INR_D(r.amount)}</Td>
                <Td className="text-right font-mono text-[#1D633E]">{INR_D(r.received_amount || 0)}</Td>
                <Td><CommissionStatus s={r.status} /></Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CommissionStatus({ s }) {
  const map = {
    pending:   "bg-[#EEF2FF] text-[#002FA7]",
    invoiced:  "bg-[#FFF4E5] text-[#7A4E1A]",
    received:  "bg-[#EFF7EF] text-[#1D633E]",
    cancelled: "bg-[#F2F2F2] text-[#9A9A9A]",
  };
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 ${map[s] || map.pending}`}>
      {s || "pending"}
    </span>
  );
}

/* -------------------- REUSABLE PRIMITIVES -------------------- */
function Card({ title, children }) {
  return (
    <div className="card-flat">
      <div className="overline mb-3">{title}</div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}
function Field({ icon, label, value, mono }) {
  return (
    <div className="flex items-start gap-2 py-1 border-b last:border-b-0 border-[#F5F5F5]">
      <div className="text-[#5C5C5C] mt-0.5">{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-mono uppercase tracking-wider text-[#9A9A9A]">{label}</div>
        <div className={`text-sm ${mono ? "font-mono" : ""} ${!value ? "text-[#9A9A9A]" : ""}`}>
          {value || "—"}
        </div>
      </div>
    </div>
  );
}
function Row({ label, value, accent }) {
  return (
    <div className="flex justify-between py-1.5 border-b last:border-b-0 border-[#F5F5F5] text-sm">
      <span className="text-[#5C5C5C]">{label}</span>
      <span className={`font-mono font-semibold ${accent ? "text-[#B22B22]" : ""}`}>{value}</span>
    </div>
  );
}
function Kpi({ label, value, accent }) {
  return (
    <div className={`card-flat ${accent ? "ring-1 ring-[#002FA7]/20" : ""}`}>
      <div className="overline">{label}</div>
      <div className={`font-display font-bold text-xl mt-1 ${accent ? "text-[#B22B22]" : ""}`}>{value}</div>
    </div>
  );
}
const Th = ({ children, className = "" }) => (
  <th className={`px-4 py-3 overline ${className}`}>{children}</th>
);
const Td = ({ children, className = "" }) => (
  <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>
);

/* -------------------- helpers -------------------- */
function today() { return new Date().toISOString().slice(0, 10); }
function emptyItem() { return { description: "", quantity: 1, rate: 0 }; }
function updateItem(f, setF, i, k, v) {
  const items = [...f.items]; items[i] = { ...items[i], [k]: v }; setF({ ...f, items });
}
function removeItem(f, setF, i) {
  if (f.items.length === 1) return;
  setF({ ...f, items: f.items.filter((_, idx) => idx !== i) });
}
