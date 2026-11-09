import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { dateForInput, formatDate, roundPaise, formatINR } from "../lib/format";
import { safeFileUrl } from "../lib/url";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { compatibleAccount, methodForAccount } from "../lib/cashbank";
import {
  ArrowLeft, Star, Buildings, Phone, Envelope, MapPin, Bank as BankIcon,
  IdentificationCard, CurrencyInr, Plus, Trash, FileText, Gauge, Receipt,
  PaperPlaneTilt, ShieldCheck, Notepad, Certificate, Wrench,
  Handshake, Percent, TrendUp, DownloadSimple, PencilSimple, ArrowCounterClockwise,
  Archive,
} from "@phosphor-icons/react";
import SearchSelect from "../components/SearchSelect";
import { askForm, confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";

const INR = (n) =>
  formatINR(n, { decimals: 0 });
const INR_D = (n) =>
  formatINR(n);

// Tabs available per business mode. Consultancy stays commission-focused;
// Turnkey unlocks the procurement side (bills + payments + full A/P ledger).
const TAB_LABELS = { commissions: "incentives", commercial: "incentive terms" };
// Vendor 360: what a studio checks about a vendor, in four places.
const VENDOR_GROUPS = [
  { id: "overview", label: "Overview", tabs: ["overview", "performance"] },
  { id: "money", label: "Money", tabs: ["ledger", "bills", "payments", "commissions", "commercial"] },
  { id: "projects", label: "Projects", tabs: ["projects"] },
  { id: "documents", label: "Documents", tabs: ["documents"] },
];
const SUB_LABELS = { overview: "Details", performance: "Performance", ledger: "Ledger", bills: "Bills",
  payments: "Payments", commissions: "Vendor incentives", commercial: "Incentive terms" };
const CONSULTANCY_TABS = ["overview", "commercial", "commissions", "projects", "documents", "performance"];
const TURNKEY_TABS     = ["overview", "commercial", "ledger", "bills", "payments", "commissions", "projects", "documents", "performance"];

export default function VendorDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { hasPerm, currentOrg } = useAuth();
  const businessMode = (currentOrg?.business_mode || "hybrid").toLowerCase();
  // Hybrid gets everything so all workflows stay reachable during transitions.
  const canFinanceRead = hasPerm("finance.read");
  const financeTabs = new Set(["commercial", "ledger", "bills", "payments", "commissions"]);
  // Contact details (the Overview) are for people who manage vendors, not staff lookups.
  const canSeeContacts = canFinanceRead || hasPerm("vendors.update");
  const TABS = (businessMode === "consultancy" ? CONSULTANCY_TABS : TURNKEY_TABS)
    .filter((name) => canFinanceRead || !financeTabs.has(name))
    .filter((name) => canSeeContacts || name !== "overview");
  const [v, setV] = useState(null);
  const [tab, setTab] = useState(() => {
    const wanted = searchParams.get("tab");
    return wanted && TABS.includes(wanted) ? wanted : (canSeeContacts ? "overview" : "projects");
  });
  const billForPo = searchParams.get("po") || "";
  const groups = VENDOR_GROUPS
    .map((g) => ({ ...g, tabs: g.tabs.filter((t) => TABS.includes(t)) }))
    .filter((g) => g.tabs.length);
  const activeGroup = groups.find((g) => g.tabs.includes(tab)) || groups[0];
  const [ledger, setLedger] = useState(null);
  const [perf, setPerf] = useState(null);
  const [commissionLedger, setCommissionLedger] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [projects, setProjects] = useState([]);
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [vendorForm, setVendorForm] = useState(null);
  const commissionRequestKey = useRef(crypto.randomUUID());
  const billRequestKey = useRef(crypto.randomUUID());
  const paymentRequestKey = useRef(crypto.randomUUID());

  const load = useCallback(async () => {
    const [{ data }, { data: acc }, { data: projectRows }] = await Promise.all([
      api.get(`/vendors/${id}`),
      hasPerm("finance.read") ? api.get("/accounts") : Promise.resolve({ data: [] }),
      hasPerm("projects.read") ? api.get("/projects") : Promise.resolve({ data: [] }),
    ]);
    setV(data);
    setAccounts(acc);
    setProjects(projectRows || []);
    if (hasPerm("purchase_orders.read")) {
      const poResult = await api.get(`/purchase-orders?vendor_id=${id}`).catch(() => ({ data: [] }));
      setPurchaseOrders(poResult.data || []);
    }
  }, [id, hasPerm]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (tab === "ledger" && canFinanceRead) api.get(`/vendors/${id}/ledger`).then(({ data }) => setLedger(data));
    if (tab === "performance") api.get(`/vendors/${id}/performance`).then(({ data }) => setPerf(data));
    if (canFinanceRead && (tab === "commissions" || tab === "commercial")) {
      api.get(`/vendors/${id}/commission-ledger`).then(({ data }) => setCommissionLedger(data));
    }
  }, [tab, id, canFinanceRead]);

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
      await api.post(`/vendors/${id}/commissions/receive`, form,
        { headers: { "Idempotency-Key": commissionRequestKey.current } });
      commissionRequestKey.current = crypto.randomUUID();
      const { data } = await api.get(`/vendors/${id}/commission-ledger`);
      setCommissionLedger(data);
    } finally { setBusy(false); }
  };
  const refreshCommissions = async () => {
    const { data } = await api.get(`/vendors/${id}/commission-ledger`);
    setCommissionLedger(data);
  };
  const updateBill = async (billId, patch) => {
    setBusy(true);
    try {
      await api.patch(`/vendor-bills/${billId}`, patch);
      await Promise.all([load(), refreshCommissions()]);
      toast.success("Bill details updated");
    } finally { setBusy(false); }
  };
  const deleteBill = async (bill) => {
    const action = bill.status === "draft" ? "delete" : "cancel and reverse";
    if (!await confirmAction(`${action[0].toUpperCase()}${action.slice(1)} ${bill.bill_number}?\n\nPosted accounting remains in the audit log and is corrected with a balanced reversal.`)) return;
    setBusy(true);
    try {
      await api.delete(`/vendor-bills/${bill.id}`);
      await Promise.all([load(), refreshCommissions()]);
      toast.success(bill.status === "draft" ? "Draft bill deleted" : "Bill cancelled and reversed");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not cancel bill");
    } finally { setBusy(false); }
  };
  const reversePayment = async (payment) => {
    if (!await confirmAction(`Reverse this ${INR_D(payment.amount)} vendor payment?\n\nThe linked bills and accounting balances will be restored automatically.`)) return;
    setBusy(true);
    try {
      await api.delete(`/vendor-payments/${payment.id}`);
      await load();
      toast.success("Vendor payment reversed");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not reverse payment");
    } finally { setBusy(false); }
  };
  const updatePaymentMetadata = async (paymentId, patch) => {
    setBusy(true);
    try {
      await api.patch(`/vendor-payments/${paymentId}`, patch);
      await load();
      toast.success("Payment reference and notes updated");
    } finally { setBusy(false); }
  };
  const reverseCommissionReceipt = async (receipt) => {
    if (!await confirmAction(`Delete this ${INR_D(receipt.amount)} vendor incentive receipt?\n\nA balanced reversal will preserve the audit trail and correct all vendor incentive totals.`)) return;
    setBusy(true);
    try {
      await api.delete(`/commission-settlements/${receipt.id}`);
      await refreshCommissions();
      toast.success("Vendor incentive receipt deleted with accounting reversal");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not delete vendor incentive receipt");
    } finally { setBusy(false); }
  };
  const updateCommissionReceiptMetadata = async (receiptId, patch) => {
    setBusy(true);
    try {
      await api.patch(`/commission-settlements/${receiptId}`, patch);
      await refreshCommissions();
      toast.success("Vendor incentive receipt reference and notes updated");
    } finally { setBusy(false); }
  };
  const cancelExpectedCommission = async (row) => {
    if (!await confirmAction("Cancel this expected vendor incentive? No posted accounting will be deleted.")) return;
    setBusy(true);
    try {
      await api.delete(`/vendors/${id}/commissions/${row.id}`);
      await refreshCommissions();
      toast.success("Expected vendor incentive cancelled");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not cancel expected vendor incentive");
    } finally { setBusy(false); }
  };
  const saveExpectedCommission = async (form, commissionId) => {
    setBusy(true);
    try {
      const payload = {
        amount: Number(form.amount), due_date: form.due_date || undefined,
        project_id: form.project_id || undefined, recognition: form.recognition,
        reference: form.reference || undefined, reminder_date: form.reminder_date || undefined,
        notes: form.notes || undefined,
      };
      if (commissionId) await api.patch(`/vendors/${id}/commissions/${commissionId}`, payload);
      else await api.post(`/vendors/${id}/commissions`, payload);
      await refreshCommissions();
      toast.success(commissionId ? "Expected vendor incentive updated" : "Expected vendor incentive added without posting accounting");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not save expected vendor incentive");
      throw error;
    } finally { setBusy(false); }
  };

  const canBill = hasPerm("finance.create");
  const canEditVendor = hasPerm("vendors.update");
  const canDeleteVendor = hasPerm("vendors.delete");

  useEffect(() => {
    if (!v || !canEditVendor || searchParams.get("edit") !== "1") return;
    const fields = ["name", "company", "agency_type", "contact_person", "phone", "email",
      "address", "city", "state", "pincode", "gstin", "pan", "tds_applicable", "tds_rate",
      "bank_name", "bank_account_number", "bank_ifsc", "bank_branch", "upi_id", "category", "notes"];
    setVendorForm(Object.fromEntries(fields.map((field) => [field, v[field] ?? (field === "tds_applicable" ? false : "")])))
    setEditOpen(true);
    navigate(`/vendors/${id}`, { replace: true });
  }, [v, canEditVendor, searchParams, navigate, id]);

  const openVendorEdit = () => {
    const fields = ["name", "company", "agency_type", "contact_person", "phone", "email",
      "address", "city", "state", "pincode", "gstin", "pan", "tds_applicable", "tds_rate",
      "bank_name", "bank_account_number", "bank_ifsc", "bank_branch", "upi_id", "category", "notes"];
    setVendorForm(Object.fromEntries(fields.map((field) => [field, v[field] ?? (field === "tds_applicable" ? false : "")])));
    setEditOpen(true);
  };
  const saveVendor = async (event) => {
    event.preventDefault(); setBusy(true);
    try {
      await api.patch(`/vendors/${id}`, vendorForm);
      await load(); setEditOpen(false); toast.success("Vendor updated");
    } catch (error) { toast.error(error?.response?.data?.detail || "Could not update vendor"); }
    finally { setBusy(false); }
  };
  const archiveVendor = async () => {
    if (!await confirmAction(`Archive ${v.name}? Existing bills, payments and accounting history will be preserved.`)) return;
    setBusy(true);
    try {
      await api.delete(`/vendors/${id}`);
      toast.success("Vendor archived"); navigate("/vendors");
    } catch (error) { toast.error(error?.response?.data?.detail || "Could not archive vendor"); }
    finally { setBusy(false); }
  };

  const submitBill = async (form) => {
    setBusy(true);
    try {
      await api.post("/vendor-bills", { ...form, vendor_id: id },
        { headers: { "Idempotency-Key": billRequestKey.current } });
      billRequestKey.current = crypto.randomUUID();
      await load();
    }
    finally { setBusy(false); }
  };
  const submitPayment = async (form) => {
    setBusy(true);
    try {
      await api.post("/vendor-payments", { ...form, vendor_id: id },
        { headers: { "Idempotency-Key": paymentRequestKey.current } });
      paymentRequestKey.current = crypto.randomUUID();
      await load();
    }
    finally { setBusy(false); }
  };
  const submitRating = async (form) => {
    setBusy(true);
    try { await api.post(`/vendors/${id}/rate`, form); await load(); }
    finally { setBusy(false); }
  };
  const addDoc = async (form) => {
    setBusy(true);
    try {
      if (form.file) {
        const body = new FormData();
        body.append("label", form.label || form.file.name);
        body.append("kind", form.kind);
        body.append("expires_on", form.expires_on || "");
        body.append("upload", form.file);
        await api.post(`/vendors/${id}/documents/upload`, body);
      } else {
        await api.post(`/vendors/${id}/documents`, { ...form, file: undefined });
      }
      await load();
    }
    finally { setBusy(false); }
  };
  const delDoc = async (docId) => {
    if (!await confirmAction("Remove this document?")) return;
    await api.delete(`/vendors/${id}/documents/${docId}`); await load();
  };
  const editDoc = async (doc) => {
    const v = await askForm({ title: "Edit document", fields: [
      { name: "label", label: "Label", required: true, defaultValue: doc.label || "" },
      { name: "kind", label: "Type", required: true, defaultValue: doc.kind || "other" },
      { name: "expires_on", label: "Expiry date (optional)", type: "date", defaultValue: doc.expires_on || "" },
    ] });
    if (!v) return;
    await api.patch(`/vendors/${id}/documents/${doc.id}`, v);
    await load();
  };

  if (!v) {
    return <div className="overline">LOADING VENDOR…</div>;
  }

  const s = v.summary || {};

  return (
    <div className="space-y-6" data-testid="vendor-detail-page">
      {/* HEADER */}
      <div>
        <Link to="/vendors" className="text-xs text-[var(--ink-2)] hover:text-[var(--accent-strong)] flex items-center gap-1">
          <ArrowLeft size={12} /> All vendors
        </Link>
        <div className="mt-3 flex items-start justify-between gap-6 flex-wrap">
          <div>
            <div className="overline mb-1">
              {v.agency_type?.toUpperCase().replace("_", " ") || "VENDOR"} · {v.category || "UNCATEGORISED"}
            </div>
            <h1 className="font-display font-bold tracking-tight text-4xl">{v.name}</h1>
            {v.company && <div className="text-[var(--ink-2)] mt-1">{v.company}</div>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {canEditVendor && <button type="button" className="btn-ghost" onClick={openVendorEdit}><PencilSimple size={13}/> Edit</button>}
            {canDeleteVendor && <button type="button" className="btn-ghost text-[var(--danger)]" onClick={archiveVendor}><Archive size={13}/> Archive</button>}
            <div className="px-3 py-2 border border-[var(--line)]">
              <div className="overline text-[9px]">RATING</div>
              <div className="flex items-center gap-1">
                <Star size={14} weight="fill" className="text-[#F5B800]" />
                <span className="font-display font-bold text-lg">{Number(v.rating || 0).toFixed(1)}</span>
                <span className="text-xs text-[var(--ink-3)]">/ 5 · {v.rating_count || 0} ratings</span>
              </div>
            </div>
            <div className="px-3 py-2 border border-[var(--line)]">
              <div className="overline text-[9px]">OUTSTANDING</div>
              <div className={`font-display font-bold text-lg ${s.outstanding > 0 ? "text-[var(--danger)]" : ""}`}>
                {INR(s.outstanding || 0)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* KPI ROW */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {canFinanceRead && <Kpi label="Total billed" value={INR(s.total_billed || 0)} />}
        {canFinanceRead && <Kpi label="Total paid" value={INR(s.total_paid || 0)} />}
        {canFinanceRead && <Kpi label="Open bills" value={s.open_bills || 0} />}
        <Kpi label="Assigned tasks" value={s.task_count || 0} />
        <Kpi label="Projects touched" value={s.project_count || 0} />
      </div>

      {/* TABS: four groups (Overview · Money · Projects · Documents); Money has its own row. */}
      <div className="border-b border-[var(--line)]">
        <div className="flex items-center gap-1 overflow-x-auto no-scrollbar" role="tablist" aria-label="Vendor sections">
          {groups.map((g) => (
            <button key={g.id} type="button" role="tab" aria-selected={activeGroup?.id === g.id}
              data-testid={g.tabs.length === 1 ? `vendor-tab-${g.tabs[0]}` : `vendor-group-${g.id}`}
              onClick={() => { if (!g.tabs.includes(tab)) setTab(g.tabs[0]); }}
              className={`px-4 py-2.5 text-xs font-mono uppercase tracking-wider transition ${
                activeGroup?.id === g.id
                  ? "text-[var(--accent-strong)] border-b-2 border-[var(--accent)] -mb-px"
                  : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
              {g.label}
            </button>
          ))}
        </div>
      </div>
      {activeGroup && activeGroup.tabs.length > 1 && (
        <div className="flex flex-wrap gap-1.5 -mt-2" role="tablist" aria-label={`${activeGroup.label} sections`}>
          {activeGroup.tabs.map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} data-testid={`vendor-tab-${t}`}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-xs border rounded-full transition ${tab === t
                ? "bg-[var(--ink)] text-white border-[var(--ink)]"
                : "bg-white text-[var(--ink-2)] border-[var(--line)] hover:border-[var(--accent-strong)]"}`}>
              {SUB_LABELS[t] || TAB_LABELS[t] || t}
            </button>
          ))}
        </div>
      )}

      {/* TAB PANELS */}
      {tab === "overview" && <Overview v={v} onRate={submitRating} busy={busy} canRate={hasPerm("vendors.update")} />}
      {tab === "commercial" && (
        <Commercial ledger={commissionLedger} vendor={v}
          canEdit={hasPerm("finance.update")}
          onSave={saveCommercial} busy={busy} />
      )}
      {tab === "ledger" && <Ledger data={ledger} />}
      {tab === "bills" && (
        <Bills v={v} accounts={accounts} purchaseOrders={purchaseOrders} initialPoId={billForPo}
          canBill={canBill} canEdit={hasPerm("finance.update")}
          canDelete={hasPerm("finance.delete")} onCreate={submitBill}
          onUpdate={updateBill} onDelete={deleteBill} busy={busy} />
      )}
      {tab === "payments" && (
        <Payments v={v} accounts={accounts} canBill={canBill}
          canEdit={hasPerm("finance.update")}
          canDelete={hasPerm("finance.delete")} onCreate={submitPayment}
          onUpdate={updatePaymentMetadata} onDelete={reversePayment} busy={busy} />
      )}
      {tab === "commissions" && (
        <Commissions ledger={commissionLedger} accounts={accounts} projects={projects}
          canReceive={hasPerm("finance.create")}
          canPlan={hasPerm("finance.create")} canEdit={hasPerm("finance.update")}
          canDelete={hasPerm("finance.delete")}
          onReceive={receiveCommission} onUpdateReceipt={updateCommissionReceiptMetadata}
          onDeleteReceipt={reverseCommissionReceipt}
          onSavePlan={saveExpectedCommission} onDeletePlan={cancelExpectedCommission} busy={busy} />
      )}
      {tab === "projects" && <ProjectsTasks v={v} />}
      {tab === "documents" && (
        <Documents v={v} canEdit={hasPerm("vendors.update")} onAdd={addDoc} onEdit={editDoc} onDelete={delDoc} busy={busy} />
      )}
      {tab === "performance" && <Performance perf={perf} />}
      {editOpen && vendorForm && <VendorEditModal form={vendorForm} setForm={setVendorForm}
        onSave={saveVendor} onClose={() => setEditOpen(false)} busy={busy} />}
    </div>
  );
}

function VendorEditModal({ form, setForm, onSave, onClose, busy }) {
  const field = (name, placeholder, type = "text") => (
    <input type={type} className="input-flat" placeholder={placeholder} value={form[name] ?? ""}
      onChange={(e) => setForm({ ...form, [name]: type === "number" ? Number(e.target.value) : e.target.value })} />
  );
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <form onSubmit={onSave} onClick={(e) => e.stopPropagation()} className="bg-white border border-[var(--line)] p-6 w-full max-w-4xl max-h-[92vh] overflow-y-auto space-y-4">
        <div className="flex justify-between items-start"><div><div className="overline">VENDOR MASTER</div><h2 className="font-display font-bold text-3xl">Edit vendor</h2></div><button type="button" className="btn-ghost" onClick={onClose}>×</button></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {field("name", "Vendor name")}{field("company", "Company")}
          <select aria-label="Agency type" className="input-flat" value={form.agency_type || "vendor"} onChange={(e) => setForm({ ...form, agency_type: e.target.value })}>
            {["vendor", "agency", "contractor", "sub_contractor", "supplier", "consultant", "freelancer", "other"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}
          </select>
          {field("contact_person", "Contact person")}{field("phone", "Phone")}{field("email", "Email", "email")}
          {field("category", "Category")}{field("city", "City")}{field("state", "State")}
          {field("pincode", "Pincode")}{field("gstin", "GSTIN")}{field("pan", "PAN")}
          {field("address", "Address")}
        </div>
        <div className="overline">BANKING &amp; TAX</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {field("bank_name", "Bank name")}{field("bank_account_number", "Account number")}{field("bank_ifsc", "IFSC")}
          {field("bank_branch", "Branch")}{field("upi_id", "UPI ID")}{field("tds_rate", "TDS %", "number")}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.tds_applicable)} onChange={(e) => setForm({ ...form, tds_applicable: e.target.checked })}/> TDS applicable</label>
        </div>
        <textarea className="input-flat w-full min-h-20" placeholder="Notes" value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })}/>
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Cancel</button><button disabled={busy || !form.name?.trim()} className="btn-primary">{busy ? "Saving…" : "Save changes"}</button></div>
      </form>
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
                  className="w-full accent-[var(--accent)]" data-testid={`rate-${k}`} />
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
      <div className="border border-[var(--line)]">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)] text-left">
            <tr>
              <Th>Date</Th><Th>Type</Th><Th>Reference</Th><Th>Narration</Th>
              <Th className="text-right">Debit</Th><Th className="text-right">Credit</Th>
              <Th className="text-right">Balance</Th>
            </tr>
          </thead>
          <tbody>
            {data.entries.length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-[var(--ink-3)]">No transactions yet.</td></tr>
            )}
            {data.entries.map((e, i) => (
              <tr key={i} className="border-b border-[var(--line-soft)]" data-testid={`ledger-row-${i}`}>
                <Td className="font-mono text-xs">{formatDate(e.date)}</Td>
                <Td>
                  <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 ${
                    e.type === "bill" ? "bg-[var(--danger-soft)] text-[var(--danger)]" : "bg-[var(--success-soft)] text-[var(--success)]"
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
        </table></div>
      </div>
    </div>
  );
}

/* -------------------- BILLS -------------------- */
function Bills({ v, accounts, purchaseOrders, initialPoId, canBill, canEdit, canDelete, onCreate, onUpdate, onDelete, busy }) {
  const [open, setOpen] = useState(false);
  const [poApplied, setPoApplied] = useState(false);
  const [editing, setEditing] = useState(null);
  const expenseAccounts = accounts.filter((a) => a.type === "expense" && a.active !== false);
  const [f, setF] = useState({ bill_date: today(), due_date: "", items: [emptyItem()], tax_rate: 18, tds_rate: 0, notes: "", project_id: "", po_id: "", expense_account_id: "" });
  const total = useMemo(() => {
    // Mirrors backend _bill_total: round lines, tax and TDS to the paisa.
    const sub = roundPaise(f.items.reduce((s, it) => s + roundPaise(Number(it.quantity || 0) * Number(it.rate || 0)), 0));
    return roundPaise(sub + roundPaise(sub * Number(f.tax_rate || 0) / 100) - roundPaise(sub * Number(f.tds_rate || 0) / 100));
  }, [f]);

  const linesFromPo = (po) => (po.lines || []).map((line) => ({
    po_line_id: line.id,
    description: line.item_name || line.description || "PO item",
    quantity: line.received_qty_total ?? line.quantity,   // bill what was received (three-way match)
    rate: line.unit_price,
  }));
  // Opened from a purchase order ("Record bill" there): same bill form, PO filled in.
  useEffect(() => {
    if (poApplied || !initialPoId || !canBill) return;
    const po = purchaseOrders.find((row) => row.id === initialPoId);
    if (!po) return;
    setF((cur) => ({ ...cur, po_id: po.id, project_id: po.project_id || cur.project_id, expense_account_id: "", items: linesFromPo(po) }));
    setOpen(true);
    setPoApplied(true);
  }, [initialPoId, purchaseOrders, canBill, poApplied]);   // eslint-disable-line react-hooks/exhaustive-deps

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
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await onCreate(f);
              setOpen(false);
              setF({ ...f, items: [emptyItem()] });
              toast.success("Vendor bill posted");
            } catch (error) {
              toast.error(error?.response?.data?.detail || "Could not record vendor bill");
            }
          }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <label className="text-xs text-[var(--ink-2)]">Bill date
              <input required type="date" className="input-flat w-full mt-1" value={f.bill_date}
                onChange={(e) => setF({ ...f, bill_date: e.target.value })} data-testid="bf-date" /></label>
            <label className="text-xs text-[var(--ink-2)]">Pay by (optional)
              <input type="date" className="input-flat w-full mt-1" value={f.due_date}
                onChange={(e) => setF({ ...f, due_date: e.target.value })} /></label>
            <label className="text-xs text-[var(--ink-2)]">GST %
              <input type="number" min="0" step="0.01" className="input-flat w-full mt-1" value={f.tax_rate}
                onChange={(e) => setF({ ...f, tax_rate: parseFloat(e.target.value) || 0 })} /></label>
            <label className="text-xs text-[var(--ink-2)]">TDS % (deducted)
              <input type="number" min="0" step="0.01" className="input-flat w-full mt-1" value={f.tds_rate}
                onChange={(e) => setF({ ...f, tds_rate: parseFloat(e.target.value) || 0 })} /></label>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <select aria-label="Purchase order" className="input-flat" value={f.po_id}
              onChange={(e) => {
                const po = purchaseOrders.find((row) => row.id === e.target.value);
                setF({
                  ...f,
                  po_id: e.target.value,
                  project_id: po?.project_id || f.project_id,
                  expense_account_id: e.target.value ? "" : f.expense_account_id,
                  items: po ? linesFromPo(po) : [emptyItem()],
                });
              }}>
              <option value="">Not linked to a purchase order</option>
              {purchaseOrders.filter((po) => !["draft", "cancelled", "closed"].includes(po.status)).map((po) => (
                <option key={po.id} value={po.id}>{po.po_number} · {INR_D(po.grand_total)}</option>
              ))}
            </select>
            {!f.po_id && (
              <SearchSelect required className="input-flat" value={f.expense_account_id}
                onChange={(e) => setF({ ...f, expense_account_id: e.target.value })}>
                <option value="">Expense account *</option>
                {expenseAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </SearchSelect>
            )}
          </div>
          <div className="space-y-2">
            {f.items.map((it, i) => (
              <div key={i} className="grid grid-cols-12 gap-2">
                <input required className="input-flat col-span-6" placeholder="Item description"
                  value={it.description} onChange={(e) => updateItem(f, setF, i, "description", e.target.value)} />
                <input required type="number" min="0" step="0.01" className="input-flat col-span-2" placeholder="Qty"
                  value={it.quantity} onChange={(e) => updateItem(f, setF, i, "quantity", parseFloat(e.target.value) || 0)} />
                <input required type="number" min="0" step="0.01" className="input-flat col-span-3" placeholder="Rate"
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
          <div className="flex items-center justify-between pt-2 border-t border-[var(--line)]">
            <div className="overline">TOTAL</div>
            <div className="font-display font-bold text-2xl text-[var(--accent-strong)]">{INR(total)}</div>
          </div>
          <button disabled={busy} className="btn-primary" data-testid="save-bill-btn">
            <Receipt size={13} /> {busy ? "Saving…" : "Save bill"}
          </button>
        </form>
      )}

      {editing && (
        <form className="card-flat space-y-3" onSubmit={async (e) => {
          e.preventDefault();
          await onUpdate(editing.id, { due_date: editing.due_date || null, notes: editing.notes || "" });
          setEditing(null);
        }}>
          <div className="overline">EDIT BILL DETAILS · {editing.bill_number}</div>
          <div className="text-xs text-[var(--ink-2)]">For amount, GST, TDS, account or line-item mistakes, cancel the posted bill and record the corrected bill. This preserves double-entry history.</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs">Due date<input type="date" className="input-flat mt-1 w-full" value={editing.due_date || ""} onChange={(e) => setEditing({ ...editing, due_date: e.target.value })} /></label>
            <label className="text-xs">Notes<input className="input-flat mt-1 w-full" value={editing.notes || ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} /></label>
          </div>
          <div className="flex gap-2"><button disabled={busy} className="btn-primary">Save details</button><button type="button" className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button></div>
        </form>
      )}

      <div className="border border-[var(--line)]">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)] text-left">
            <tr>
              <Th>Number</Th><Th>Bill date</Th><Th>Due</Th><Th>Status</Th>
              <Th className="text-right">Total</Th><Th className="text-right">Paid</Th><Th className="text-right">Outstanding</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {(v.bills || []).length === 0 && (
              <tr><td colSpan={8} className="p-8 text-center text-[var(--ink-3)]">No bills yet.</td></tr>
            )}
            {(v.bills || []).map((b) => (
              <tr key={b.id} className="border-b border-[var(--line-soft)]" data-testid={`bill-row-${b.id}`}>
                <Td className="font-mono text-xs">{b.bill_number}</Td>
                <Td>{formatDate(b.bill_date)}</Td>
                <Td>{formatDate(b.due_date)}</Td>
                <Td><BillStatus s={b.status} /></Td>
                <Td className="text-right font-mono">{INR_D(b.total)}</Td>
                <Td className="text-right font-mono text-[var(--success)]">{INR_D(b.paid_amount || 0)}</Td>
                <Td className="text-right font-mono text-[var(--danger)]">{INR_D(b.outstanding || 0)}</Td>
                <Td className="text-right">
                  <RowActions label={`bill ${b.bill_number || ""}`} testid={`bill-actions-${b.id}`} actions={[
                    { label: "Edit bill", icon: PencilSimple, onSelect: () => setEditing({ ...b }), hidden: !(canEdit && b.status !== "cancelled") },
                    { divider: true },
                    { label: b.status === "draft" ? "Delete bill" : "Cancel bill", icon: Trash, danger: true, onSelect: () => onDelete(b),
                      hidden: !(canDelete && b.status !== "cancelled"), testid: `bill-delete-${b.id}` },
                  ]} />
                </Td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

function BillStatus({ s }) {
  const map = {
    draft: "bg-[var(--line-soft)] text-[var(--ink-2)]",
    received: "bg-[var(--info-soft)] text-[var(--accent-strong)]",
    partially_paid: "bg-[var(--warning-soft)] text-[var(--warning)]",
    paid: "bg-[var(--success-soft)] text-[var(--success)]",
    overdue: "bg-[var(--danger-soft)] text-[var(--danger)]",
    cancelled: "bg-[var(--line-soft)] text-[var(--ink-3)]",
  };
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 ${map[s] || map.draft}`}>
      {(s || "draft").replace("_", " ")}
    </span>
  );
}

/* -------------------- PAYMENTS -------------------- */
function Payments({ v, accounts, canBill, canEdit, canDelete, onCreate, onUpdate, onDelete, busy }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({ reference: "", notes: "" });
  const bankAccounts = accounts.filter((a) => a.is_bank || a.name?.toLowerCase().includes("cash"));
  const [f, setF] = useState({
    amount: 0, payment_date: today(), paid_from_account_id: "",
    payment_method: "bank_transfer", reference: "", notes: "", bill_ids: [],
  });

  useEffect(() => {
    if (!f.paid_from_account_id && bankAccounts[0]) {
      // Keep the recorded method and the credited ledger in agreement.
      setF((s) => ({ ...s, paid_from_account_id: bankAccounts[0].id,
                     payment_method: methodForAccount(bankAccounts[0]) }));
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
            <span className="text-xs text-[var(--ink-3)] ml-2">Only finance roles can record payments.</span>
          )}
        </div>
      )}
      {open && (
        <form
          className="card-flat space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await onCreate(f);
              setOpen(false);
              setF({ ...f, amount: 0, reference: "", notes: "", bill_ids: [] });
              toast.success("Vendor payment recorded");
            } catch (error) {
              toast.error(error?.response?.data?.detail || "Could not record vendor payment");
            }
          }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <input required type="number" min="0" step="0.01" className="input-flat" placeholder="Amount *"
              value={f.amount} onChange={(e) => setF({ ...f, amount: parseFloat(e.target.value) || 0 })} data-testid="pf-amount" />
            <input required type="date" className="input-flat" value={f.payment_date}
              onChange={(e) => setF({ ...f, payment_date: e.target.value })} />
            <SearchSelect required className="input-flat" value={f.paid_from_account_id}
              onChange={(e) => {
                const account = bankAccounts.find((a) => a.id === e.target.value);
                setF({ ...f, paid_from_account_id: e.target.value,
                       payment_method: account ? methodForAccount(account) : f.payment_method });
              }} data-testid="pf-bank">
              <option value="">Paid from…</option>
              {bankAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </SearchSelect>
            <select aria-label="Payment method" className="input-flat" value={f.payment_method}
              onChange={(e) => {
                const method = e.target.value;
                const compatible = compatibleAccount(bankAccounts, method);
                setF({ ...f, payment_method: method,
                       paid_from_account_id: compatible?.id || f.paid_from_account_id });
              }} data-testid="pf-method">
              {["bank_transfer","upi","cash","cheque","credit_card","online","other"].map((m) => (
                <option key={m} value={m}>{m.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <input className="input-flat w-full" placeholder="Reference (UTR / cheque # / txn id)"
            value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} />
          {openBills.length > 0 && (
            <div className="border border-[var(--line)] p-3 space-y-1">
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
                  <span className="text-[var(--ink-3)]">·</span>
                  <span>{formatDate(b.bill_date)}</span>
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

      {editing && (
        <form className="card-flat space-y-3" onSubmit={async (event) => {
          event.preventDefault();
          await onUpdate(editing.id, editForm);
          setEditing(null);
        }} data-testid="edit-payment-metadata-form">
          <div className="overline">EDIT PAYMENT DETAILS</div>
          <div className="text-xs text-[var(--ink-2)]">Amount, date and account are financial facts. Reverse and record again to correct them safely.</div>
          <input className="input-flat w-full" maxLength={120} placeholder="Reference"
            value={editForm.reference} onChange={(e) => setEditForm({ ...editForm, reference: e.target.value })} />
          <textarea className="input-flat w-full" maxLength={500} placeholder="Notes"
            value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} />
          <div className="flex gap-2"><button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button></div>
        </form>
      )}

      <div className="border border-[var(--line)]">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)] text-left">
            <tr>
              <Th>Date</Th><Th>Method</Th><Th>Reference</Th>
              <Th className="text-right">Amount</Th><Th>Settled bills</Th><Th>Status / actions</Th>
            </tr>
          </thead>
          <tbody>
            {(v.payments || []).length === 0 && (
              <tr><td colSpan={6} className="p-8 text-center text-[var(--ink-3)]">No payments recorded.</td></tr>
            )}
            {(v.payments || []).map((p) => (
              <tr key={p.id} className="border-b border-[var(--line-soft)]" data-testid={`payment-row-${p.id}`}>
                <Td className="font-mono text-xs">{formatDate(p.payment_date)}</Td>
                <Td>{(p.payment_method || "").replace("_", " ")}</Td>
                <Td className="font-mono text-xs">{p.reference || "—"}</Td>
                <Td className="text-right font-mono font-semibold text-[var(--success)]">{INR_D(p.amount)}</Td>
                <Td className="text-xs font-mono">
                  {(p.bill_ids || []).length ? p.bill_ids.length + " bill(s)" : "on-account"}
                </Td>
                <Td className="text-right">{p.status === "reversed" ? <span className="text-[10px] font-mono uppercase text-[var(--ink-3)]">Reversed</span> : (
                  <RowActions label="payment" testid={`payment-actions-${p.id}`} actions={[
                    { label: "Edit reference / notes", icon: PencilSimple, hidden: !canEdit,
                      onSelect: () => { setEditing(p); setEditForm({ reference: p.reference || "", notes: p.notes || "" }); } },
                    { divider: true },
                    { label: "Reverse payment", icon: ArrowCounterClockwise, danger: true, hidden: !canDelete, onSelect: () => onDelete(p),
                      testid: `payment-reverse-${p.id}` },
                  ]} />
                )}</Td>
              </tr>
            ))}
          </tbody>
        </table></div>
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
          {(v.projects || []).length === 0 && <div className="text-sm text-[var(--ink-3)]">No projects linked yet.</div>}
          {(v.projects || []).map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="flex justify-between items-center border-b border-[var(--line-soft)] pb-2 hover:text-[var(--accent-strong)]">
              <div>
                <div className="text-sm font-semibold">{p.name}</div>
                <div className="text-xs text-[var(--ink-3)]">{p.client_name || "—"}</div>
              </div>
              <span className="text-[10px] font-mono uppercase text-[var(--ink-2)]">{p.stage}</span>
            </Link>
          ))}
        </div>
      </Card>
      <Card title={`Assigned tasks (${(v.tasks || []).length})`}>
        <div className="space-y-2">
          {(v.tasks || []).length === 0 && <div className="text-sm text-[var(--ink-3)]">No tasks assigned.</div>}
          {(v.tasks || []).slice(0, 20).map((t) => (
            <Link key={t.id} to={`/tasks/${t.id}`} className="flex items-start justify-between gap-3 border-b border-[var(--line-soft)] pb-2 hover:text-[var(--accent-strong)]">
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">{t.title}</div>
                <div className="text-xs text-[var(--ink-3)]">
                  {t.category || "—"} · due {formatDate(t.due_date)}
                </div>
              </div>
              <span className="text-[10px] font-mono uppercase text-[var(--ink-2)] shrink-0">
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
function Documents({ v, canEdit, onAdd, onEdit, onDelete, busy }) {
  const [f, setF] = useState({ label: "", url: "", kind: "gst_certificate", expires_on: "", file: null });
  return (
    <div className="space-y-4">
      {canEdit && (
        <form className="card-flat grid grid-cols-1 md:grid-cols-5 gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await onAdd(f);
            setF({ label: "", url: "", kind: "gst_certificate", expires_on: "", file: null });
            e.currentTarget.reset();
          }}
        >
          <input required className="input-flat md:col-span-2" placeholder="Label"
            value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="External URL (or upload below)" required={!f.file}
            value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
          <input className="input-flat md:col-span-2" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.docx,.xlsx,.csv,.txt"
            onChange={(e) => setF({ ...f, file: e.target.files?.[0] || null })} />
          <select aria-label="Document type" className="input-flat" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
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
          <div className="text-sm text-[var(--ink-3)] col-span-2">No documents on file.</div>
        )}
        {(v.documents || []).map((d) => (
          <div key={d.id} className="border border-[var(--line)] p-4 flex items-start gap-3">
            <FileText size={22} className="text-[var(--accent-strong)]" />
            <div className="flex-1 min-w-0">
              {safeFileUrl(d.url) ? (
                <a href={safeFileUrl(d.url)} target="_blank" rel="noreferrer" className="font-semibold text-sm hover:text-[var(--accent-strong)] break-all">
                  {d.label}
                </a>
              ) : <span className="font-semibold text-sm">{d.label}</span>}
              <div className="text-xs text-[var(--ink-3)] font-mono">
                {d.kind?.replace("_", " ")} {d.expires_on ? `· expires ${d.expires_on}` : ""}
              </div>
            </div>
            {canEdit && (
              <div className="flex gap-1">
                <button onClick={() => onEdit(d)} className="btn-ghost" aria-label="edit document metadata"><PencilSimple size={13} /></button>
                <button onClick={() => onDelete(d.id)} className="btn-ghost text-[var(--danger)]" aria-label="remove"><Trash size={13} /></button>
              </div>
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
  const scoreColor = score >= 75 ? "text-[var(--success)]" : score >= 50 ? "text-[var(--warning)]" : "text-[var(--danger)]";
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card title="Overall performance">
        <div className="flex items-center gap-3">
          <Gauge size={48} className={scoreColor} weight="duotone" />
          <div>
            <div className={`font-display font-bold text-5xl ${scoreColor}`}>{score}</div>
            <div className="text-xs font-mono uppercase tracking-wider text-[var(--ink-2)]">out of 100</div>
          </div>
        </div>
        <p className="text-xs text-[var(--ink-2)] mt-3">
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
    income_label: cfg.income_label || "Vendor Incentive Income",
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
        <Card title="Incentive agreement">
          <label className="flex items-center gap-2 text-sm mb-3">
            <input
              data-testid="cm-applicable"
              type="checkbox" checked={f.applicable}
              onChange={(e) => setF({ ...f, applicable: e.target.checked })}
            />
            This vendor pays us an incentive
          </label>

          <div className={f.applicable ? "" : "opacity-50 pointer-events-none"}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <select aria-label="Incentive type" data-testid="cm-type" className="input-flat" value={t}
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
              <div className="mt-4 border border-[var(--line)] p-3">
                <div className="overline mb-2">SLABS</div>
                {f.slabs.map((s, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                    <input type="number" min="0" step="0.01" className="input-flat col-span-4"
                      placeholder="From (₹)" value={s.min_purchase}
                      onChange={(e) => setSlab(i, "min_purchase", parseFloat(e.target.value) || 0)} />
                    <input type="number" min="0" step="0.01" className="input-flat col-span-4"
                      placeholder="To (₹) — blank = ∞" value={s.max_purchase ?? ""}
                      onChange={(e) => setSlab(i, "max_purchase", e.target.value === "" ? null : parseFloat(e.target.value))} />
                    <input type="number" min="0" step="0.01" className="input-flat col-span-3"
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
              <Handshake size={13} /> {busy ? "Saving…" : "Save & recompute incentives"}
            </button>
          )}
        </Card>
      </div>

      <div className="space-y-3">
        <Card title="Vendor incentive summary">
          {ledger?.totals ? (
            <>
              <Row label="Total purchase" value={INR(ledger.totals.total_purchase)} />
              <Row label="Total earned" value={INR(ledger.totals.total_earned)} />
              <Row label="Received" value={INR(ledger.totals.total_received)} />
              <Row label="Pending" value={INR(ledger.totals.pending)} accent={ledger.totals.pending > 0} />
              <Row label="Unallocated" value={INR(ledger.totals.unallocated_received)} accent={ledger.totals.unallocated_received > 0} />
            </>
          ) : (
            <div className="text-sm text-[var(--ink-2)]">Save the config to see numbers.</div>
          )}
        </Card>
        <Card title="How it works">
          <p className="text-xs text-[var(--ink-2)]">
            Whenever a bill is recorded against this vendor, we auto-book the earned commission.
            Mark it received in the <b>Vendor incentives</b> tab and we'll post an Income journal entry
            (DR Bank · CR Commission Income) — it flows straight into P&amp;L, Cash Flow and the Dashboard.
          </p>
        </Card>
      </div>
    </div>
  );
}

/* -------------------- COMMISSIONS (list + receive) -------------------- */
function Commissions({ ledger, accounts, projects, canReceive, canPlan, canEdit, canDelete,
  onReceive, onUpdateReceipt, onDeleteReceipt, onSavePlan, onDeletePlan, busy }) {
  const { id } = useParams();
  const bankAccounts = accounts.filter((a) => a.is_bank || a.name?.toLowerCase().includes("cash"));
  const [open, setOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState(null);
  const [editingReceipt, setEditingReceipt] = useState(null);
  const [receiptEdit, setReceiptEdit] = useState({ reference: "", notes: "" });
  const emptyPlan = {
    amount: "", due_date: "", project_id: "", recognition: "planned",
    reference: "", reminder_date: "", notes: "",
  };
  const [plan, setPlan] = useState(emptyPlan);
  const [f, setF] = useState({
    amount: 0, received_date: today(), bank_account_id: "",
    payment_method: "bank_transfer", reference: "", notes: "", commission_ids: [],
  });
  useEffect(() => {
    if (!f.bank_account_id && bankAccounts[0]) {
      setF((s) => ({ ...s, bank_account_id: bankAccounts[0].id,
        payment_method: methodForAccount(bankAccounts[0]) }));
    }
    // eslint-disable-next-line
  }, [accounts.length]);

  const downloadStatementPdf = async () => {
    try {
      const res = await api.get(`/vendors/${id}/commission-statement.pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `commission-statement.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { /* toast handled by axios interceptor */ }
  };
  const openPlan = (row = null) => {
    setEditingPlan(row);
    setPlan(row ? {
      amount: row.amount ?? "", due_date: row.due_date || "",
      project_id: row.project_id || "", recognition: row.recognition || "planned",
      reference: row.reference || "", reminder_date: row.reminder_date || "",
      notes: row.notes || "",
    } : emptyPlan);
    setPlanOpen(true);
  };
  const submitPlan = async (event) => {
    event.preventDefault();
    try {
      await onSavePlan(plan, editingPlan?.id);
      setPlanOpen(false); setEditingPlan(null); setPlan(emptyPlan);
    } catch { /* parent shows the API error and leaves the form open */ }
  };

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
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setOpen(!open)} className="btn-primary" data-testid="receive-cm-btn">
            <Plus size={14} /> {open ? "Cancel" : "Record vendor incentive received"}
          </button>
          <button onClick={downloadStatementPdf} className="btn-ghost" data-testid="cm-statement-pdf-btn">
            <DownloadSimple size={13} /> Statement PDF
          </button>
          {canPlan && <button type="button" onClick={() => openPlan()} className="btn-ghost" data-testid="add-expected-commission">
            <Receipt size={13} /> Add expected commission
          </button>}
        </div>
      )}
      {planOpen && (
        <form className="card-flat space-y-3" onSubmit={submitPlan} data-testid="expected-commission-form">
          <div className="flex items-start justify-between gap-3">
            <div><div className="overline">{editingPlan ? "EDIT EXPECTED COMMISSION" : "EXPECTED COMMISSION"}</div>
              <div className="text-xs text-[var(--ink-2)] mt-1">This creates a collection due only. No journal is posted until money is received.</div></div>
            <button type="button" className="btn-ghost" onClick={() => setPlanOpen(false)}>×</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <label className="text-xs">Expected amount<input required min="0.01" step="0.01" type="number" className="input-flat mt-1 w-full" value={plan.amount} onChange={(e) => setPlan({ ...plan, amount: e.target.value })} /></label>
            <label className="text-xs">Due date<input type="date" className="input-flat mt-1 w-full" value={plan.due_date} onChange={(e) => setPlan({ ...plan, due_date: e.target.value })} /></label>
            <label className="text-xs">Project<SearchSelect className="input-flat mt-1 w-full" value={plan.project_id} onChange={(e) => setPlan({ ...plan, project_id: e.target.value })}><option value="">No project</option>{(projects || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</SearchSelect></label>
            <label className="text-xs">Accounting basis<select className="input-flat mt-1 w-full" value={plan.recognition} onChange={(e) => setPlan({ ...plan, recognition: e.target.value })}><option value="planned">Expected only - not earned</option><option value="earned">Already earned - awaiting receipt</option></select></label>
            <label className="text-xs">Reminder date<input type="date" className="input-flat mt-1 w-full" value={plan.reminder_date} onChange={(e) => setPlan({ ...plan, reminder_date: e.target.value })} /></label>
            <label className="text-xs md:col-span-2">Reference<input className="input-flat mt-1 w-full" value={plan.reference} onChange={(e) => setPlan({ ...plan, reference: e.target.value })} /></label>
            <label className="text-xs md:col-span-4">Notes<textarea className="input-flat mt-1 w-full" value={plan.notes} onChange={(e) => setPlan({ ...plan, notes: e.target.value })} /></label>
          </div>
          <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : editingPlan ? "Save changes" : "Add expected vendor incentive"}</button>
        </form>
      )}
      {open && (
        <form
          className="card-flat space-y-3"
          onSubmit={(e) => { e.preventDefault(); onReceive(f); setOpen(false); setF({ ...f, amount: 0, reference: "", notes: "", commission_ids: [] }); }}
        >
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <input required type="number" min="0" step="0.01" className="input-flat" placeholder="Amount *"
              data-testid="rcm-amount"
              value={f.amount} onChange={(e) => setF({ ...f, amount: parseFloat(e.target.value) || 0 })} />
            <input required type="date" className="input-flat" value={f.received_date}
              onChange={(e) => setF({ ...f, received_date: e.target.value })} />
            <SearchSelect required className="input-flat" value={f.bank_account_id}
              data-testid="rcm-bank"
              onChange={(e) => {
                const account = bankAccounts.find((item) => item.id === e.target.value);
                setF({ ...f, bank_account_id: e.target.value,
                  payment_method: methodForAccount(account) });
              }}>
              <option value="">Deposited to…</option>
              {bankAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </SearchSelect>
            <select aria-label="Payment method" className="input-flat" value={f.payment_method}
              onChange={(e) => {
                const method = e.target.value;
                const compatible = compatibleAccount(bankAccounts, method);
                setF({ ...f, payment_method: method,
                  bank_account_id: compatible?.id || f.bank_account_id });
              }}>
              {["bank_transfer","upi","cash","cheque","credit_card","online","other"].map((m) => (
                <option key={m} value={m}>{m.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <input className="input-flat w-full" placeholder="Reference (UTR / cheque #)"
            value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} />

          {openRows.length > 0 && (
            <div className="border border-[var(--line)] p-3 space-y-1">
              <div className="overline">Settle specific incentives (optional — FIFO if empty)</div>
              {openRows.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.commission_ids.includes(r.id)}
                    onChange={(e) => {
                      setF({ ...f, commission_ids: e.target.checked
                        ? [...f.commission_ids, r.id]
                        : f.commission_ids.filter((x) => x !== r.id) });
                    }} />
                  <span className="font-mono text-xs">{r.bill_number}</span>
                  <span className="text-[var(--ink-3)]">·</span>
                  <span>{formatDate(r.bill_date)}</span>
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

      <div className="border border-[var(--line)]">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)] text-left">
            <tr>
              <Th>Due / bill date</Th><Th>Source / project</Th><Th className="text-right">Purchase</Th>
              <Th>Type</Th><Th className="text-right">Earned</Th>
              <Th className="text-right">Received</Th><Th>Status</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {(ledger.entries || []).length === 0 && (
              <tr><td colSpan={8} className="p-8 text-center text-[var(--ink-3)]">
                No commissions yet. Post a bill and it'll auto-compute.
              </td></tr>
            )}
            {(ledger.entries || []).map((r) => (
              <tr key={r.id} className="border-b border-[var(--line-soft)]" data-testid={`cm-row-${r.id}`}>
                <Td className="font-mono text-xs">{formatDate(r.due_date || r.bill_date)}</Td>
                <Td><div className="font-mono text-xs">{r.bill_number || r.reference || "Expected vendor incentive"}</div><div className="text-[10px] text-[var(--ink-3)]">{r.project_name || (r.project_id ? "Linked project" : "No project")}</div></Td>
                <Td className="text-right font-mono">{INR_D(r.purchase_amount)}</Td>
                <Td>
                  <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 bg-[var(--line-soft)]">
                    {r.origin === "manual_expected" ? r.recognition : r.commission_type}
                  </span>
                </Td>
                <Td className="text-right font-mono">{INR_D(r.amount)}</Td>
                <Td className="text-right font-mono text-[var(--success)]">{INR_D(r.received_amount || 0)}</Td>
                <Td><CommissionStatus s={r.status} /></Td>
                <Td>{r.origin === "manual_expected" && !["cancelled", "reversed", "received"].includes(r.status) ? <RowActions label="expected vendor incentive" testid={`commission-actions-${r.id}`} actions={[
                  { label: "Edit", icon: PencilSimple, hidden: !canEdit, onSelect: () => openPlan(r) },
                  { divider: true },
                  { label: "Cancel expected vendor incentive", icon: Trash, danger: true, hidden: !canDelete, onSelect: () => onDeletePlan(r) },
                ]} /> : r.bill_id ? <span className="text-[10px] text-[var(--ink-3)]">Correct from bill</span> : "—"}</Td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      {(ledger.receipts || []).length > 0 && (
        <div className="border border-[var(--line)]" data-testid="commission-receipts">
          <div className="overline px-3 pt-3">RECEIPT HISTORY</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase text-[var(--ink-3)]">
              <tr>
                <Th>Date</Th><Th>Method / reference</Th>
                <Th className="text-right">Received</Th><Th className="text-right">Unallocated</Th><Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {ledger.receipts.map((receipt) => (
                <tr key={receipt.id} className="border-t border-[var(--line-soft)]">
                  <Td className="font-mono text-xs">{formatDate(receipt.received_date)}</Td>
                  <Td>
                    <div className="capitalize">{(receipt.payment_method || "other").replaceAll("_", " ")}</div>
                    {receipt.reference && <div className="text-xs text-[var(--ink-2)]">{receipt.reference}</div>}
                  </Td>
                  <Td className="text-right font-mono text-[var(--success)]">{INR_D(receipt.amount)}</Td>
                  <Td className="text-right font-mono">{INR_D(receipt.unallocated || 0)}</Td>
                  <Td className="text-right">
                    <RowActions label="receipt" testid={`receipt-actions-${receipt.id}`} actions={[
                      { label: "Edit reference / notes", icon: PencilSimple, hidden: !canEdit,
                        onSelect: () => { setEditingReceipt(receipt); setReceiptEdit({ reference: receipt.reference || "", notes: receipt.notes || "" }); } },
                      { divider: true },
                      { label: "Delete receipt", icon: Trash, danger: true, hidden: !canDelete, onSelect: () => onDeleteReceipt(receipt),
                        testid: `receipt-delete-${receipt.id}` },
                    ]} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table></div>
          {editingReceipt && <form className="border-t border-[var(--line)] p-3 space-y-2" onSubmit={async (event) => {
            event.preventDefault();
            await onUpdateReceipt(editingReceipt.id, receiptEdit);
            setEditingReceipt(null);
          }} data-testid="edit-commission-receipt-form">
            <div className="overline">EDIT RECEIPT DETAILS</div>
            <div className="text-xs text-[var(--ink-2)]">To correct amount, date or bank account, delete this receipt and record it again. The audit trail remains intact.</div>
            <input className="input-flat w-full" maxLength={120} placeholder="Reference" value={receiptEdit.reference}
              onChange={(e) => setReceiptEdit({ ...receiptEdit, reference: e.target.value })} />
            <textarea className="input-flat w-full" maxLength={500} placeholder="Notes" value={receiptEdit.notes}
              onChange={(e) => setReceiptEdit({ ...receiptEdit, notes: e.target.value })} />
            <div className="flex gap-2"><button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              <button type="button" className="btn-ghost" onClick={() => setEditingReceipt(null)}>Cancel</button></div>
          </form>}
        </div>
      )}
    </div>
  );
}

// Stored status keys are kept for compatibility; "invoiced" has always meant
// "some money received, balance still pending" and must not read as an invoice.
const COMMISSION_STATUS_LABELS = {
  pending: "Pending", invoiced: "Partially received", received: "Received",
  cancelled: "Cancelled", reversed: "Reversed",
};

function CommissionStatus({ s }) {
  const map = {
    pending:   "bg-[var(--info-soft)] text-[var(--accent-strong)]",
    invoiced:  "bg-[var(--warning-soft)] text-[var(--warning)]",
    received:  "bg-[var(--success-soft)] text-[var(--success)]",
    cancelled: "bg-[var(--line-soft)] text-[var(--ink-3)]",
  };
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 ${map[s] || map.pending}`}
          data-testid="commission-status">
      {COMMISSION_STATUS_LABELS[s] || s || "Pending"}
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
    <div className="flex items-start gap-2 py-1 border-b last:border-b-0 border-[var(--hover)]">
      <div className="text-[var(--ink-2)] mt-0.5">{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-3)]">{label}</div>
        <div className={`text-sm ${mono ? "font-mono" : ""} ${!value ? "text-[var(--ink-3)]" : ""}`}>
          {value || "—"}
        </div>
      </div>
    </div>
  );
}
function Row({ label, value, accent }) {
  return (
    <div className="flex justify-between py-1.5 border-b last:border-b-0 border-[var(--hover)] text-sm">
      <span className="text-[var(--ink-2)]">{label}</span>
      <span className={`font-mono font-semibold ${accent ? "text-[var(--danger)]" : ""}`}>{value}</span>
    </div>
  );
}
function Kpi({ label, value, accent }) {
  return (
    <div className={`card-flat ${accent ? "ring-1 ring-[#8B7F6A]/20" : ""}`}>
      <div className="overline">{label}</div>
      <div className={`font-display font-bold text-xl mt-1 ${accent ? "text-[var(--danger)]" : ""}`}>{value}</div>
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
function today() { return dateForInput(new Date()); }
function emptyItem() { return { description: "", quantity: 1, rate: 0 }; }
function updateItem(f, setF, i, k, v) {
  const items = [...f.items]; items[i] = { ...items[i], [k]: v }; setF({ ...f, items });
}
function removeItem(f, setF, i) {
  if (f.items.length === 1) return;
  setF({ ...f, items: f.items.filter((_, idx) => idx !== i) });
}
