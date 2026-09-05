import { useEffect, useState } from "react";
import api, { API } from "../lib/api";
import { Plus, FilePdf, Trash, Eye, PencilSimple } from "@phosphor-icons/react";

export default function Invoices({ docType = "invoice" }) {
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(initialForm(docType));
  const [editingId, setEditingId] = useState(null);
  const [preview, setPreview] = useState(null);

  function initialForm(dt) {
    return {
      client_id: "", project_id: "",
      items: [{ description: "", quantity: 1, rate: 0, amount: 0 }],
      tax_rate: 18, notes: "Payment due within 15 days.",
      due_date: "", status: "draft", doc_type: dt,
    };
  }

  const load = async () => {
    const [inv, cl, pr] = await Promise.all([
      api.get(`/invoices?doc_type=${docType}`),
      api.get("/clients"),
      api.get("/projects"),
    ]);
    setRows(inv.data);
    setClients(cl.data);
    setProjects(pr.data);
  };
  useEffect(() => { load(); setForm(initialForm(docType)); /* eslint-disable-next-line */ }, [docType]);

  const updateItem = (i, key, val) => {
    const items = [...form.items];
    items[i] = { ...items[i], [key]: val };
    items[i].amount = (Number(items[i].quantity) || 0) * (Number(items[i].rate) || 0);
    setForm({ ...form, items });
  };

  const addItem = () => setForm({ ...form, items: [...form.items, { description: "", quantity: 1, rate: 0, amount: 0 }] });
  const removeItem = (i) => setForm({ ...form, items: form.items.filter((_, idx) => idx !== i) });

  const subtotal = form.items.reduce((s, it) => s + (Number(it.quantity) || 0) * (Number(it.rate) || 0), 0);
  const tax = subtotal * (Number(form.tax_rate) || 0) / 100;
  const total = subtotal + tax;

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
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
      due_date: r.due_date || "", status: r.status, doc_type: r.doc_type,
    });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const changeStatus = async (id, status) => {
    const row = rows.find((r) => r.id === id);
    if (status === "paid" && row?.doc_type !== "quotation") {
      const ok = window.confirm(
        `Mark ${row?.number || "this invoice"} as PAID?\n\nThis records a receipt of ₹${(row?.total || 0).toLocaleString("en-IN")} in Accounting (dated today). You can undo by changing status back to "sent".`
      );
      if (!ok) { load(); return; }
    }
    try {
      await api.patch(`/invoices/${id}/status`, { status });
    } catch (e) {
      alert(e?.response?.data?.detail || "Could not update status");
    }
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Delete?")) return;
    try {
      await api.delete(`/invoices/${id}`);
    } catch (e) {
      alert(e?.response?.data?.detail || "Could not delete");
    }
    load();
  };

  const download = (id) => {
    window.open(`${API}/invoices/${id}/pdf`, "_blank");
  };

  return (
    <div className="space-y-6" data-testid={`${docType}s-page`}>
      <div className="flex items-end justify-between">
        <div>
          <div className="overline mb-1">FINANCE / {docType.toUpperCase()}S</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">
            {docType === "quotation" ? "Proposals, polished." : "Send. Track. Collect."}
          </h1>
        </div>
        <button onClick={() => { setShowForm(!showForm); setEditingId(null); setForm(initialForm(docType)); }} className="btn-primary" data-testid={`new-${docType}-btn`}>
          <Plus size={14} /> {showForm ? "Cancel" : `New ${docType}`}
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="invoice-form">
          <div className="card-flat space-y-4">
            <div className="overline">DETAILS</div>
            <div className="grid grid-cols-2 gap-3">
              <select className="input-flat" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
                <option value="">Select client</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">Select project</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <input type="date" className="input-flat" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
              <input type="number" className="input-flat" placeholder="Tax %" value={form.tax_rate} onChange={(e) => setForm({ ...form, tax_rate: e.target.value })} />
            </div>

            <div className="overline">LINE ITEMS</div>
            <div className="space-y-2">
              {form.items.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-center">
                  <input className="input-flat col-span-6" placeholder="Description" value={it.description} onChange={(e) => updateItem(i, "description", e.target.value)} />
                  <input type="number" className="input-flat col-span-2" placeholder="Qty" value={it.quantity} onChange={(e) => updateItem(i, "quantity", e.target.value)} />
                  <input type="number" className="input-flat col-span-3" placeholder="Rate" value={it.rate} onChange={(e) => updateItem(i, "rate", e.target.value)} />
                  <button type="button" onClick={() => removeItem(i)} className="text-[#FF2A00]"><Trash size={14} /></button>
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
                <div>DATE · {new Date().toLocaleDateString()}</div>
                <div>DUE · {form.due_date || "—"}</div>
              </div>
            </div>
            <div className="border-t border-b border-[#0A0A0A] py-2 grid grid-cols-12 text-[10px] font-mono tracking-widest uppercase font-semibold">
              <div className="col-span-6">Description</div>
              <div className="col-span-2 text-right">Qty</div>
              <div className="col-span-2 text-right">Rate</div>
              <div className="col-span-2 text-right">Amount</div>
            </div>
            {form.items.map((it, i) => (
              <div key={i} className="grid grid-cols-12 py-2 border-b border-[#F0F0F0] text-sm">
                <div className="col-span-6">{it.description || "—"}</div>
                <div className="col-span-2 text-right font-mono">{it.quantity}</div>
                <div className="col-span-2 text-right font-mono">{Number(it.rate || 0).toLocaleString("en-IN")}</div>
                <div className="col-span-2 text-right font-mono">{((Number(it.quantity) || 0) * (Number(it.rate) || 0)).toLocaleString("en-IN")}</div>
              </div>
            ))}
            <div className="pt-4 space-y-1 text-sm">
              <Row label="Subtotal" val={subtotal} />
              <Row label={`Tax (${form.tax_rate}%)`} val={tax} />
              <div className="border-t border-[#0A0A0A] pt-2 mt-2">
                <Row label="Total" val={total} bold />
              </div>
            </div>
            <button type="submit" className="btn-primary w-full justify-center mt-6" data-testid="invoice-submit">
              {editingId ? `Save changes` : `Save ${docType}`}
            </button>
          </div>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <table className="w-full">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Number</Th><Th>Client</Th><Th>Project</Th><Th>Due</Th><Th>Total</Th><Th>Status</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[#F0F0F0] hover:bg-[#FAFAFA]" data-testid={`${docType}-row-${r.id}`}>
                <Td className="font-mono font-semibold">{r.number}</Td>
                <Td>{r.client_name || "—"}</Td>
                <Td>{r.project_name || "—"}</Td>
                <Td className="font-mono text-xs">{r.due_date || "—"}</Td>
                <Td className="font-mono font-semibold">₹{(r.total || 0).toLocaleString("en-IN")}</Td>
                <Td>
                  <select className={`status-chip chip-${r.status}`} value={r.status} onChange={(e) => changeStatus(r.id, e.target.value)}>
                    <option value="draft">draft</option>
                    <option value="sent">sent</option>
                    <option value="paid">paid</option>
                    <option value="overdue">overdue</option>
                  </select>
                </Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setPreview(r)} className="text-[#8B7F6A]" title="Preview"><Eye size={16} /></button>
                    <button onClick={() => download(r.id)} className="text-[#8B7F6A]" title="PDF"><FilePdf size={16} /></button>
                    {r.status !== "paid" && (
                      <button onClick={() => startEdit(r)} className="text-[#5C5C5C] hover:text-[#0A0A0A]" title="Edit" data-testid={`${docType}-edit-${r.id}`}><PencilSimple size={16} /></button>
                    )}
                    <button onClick={() => del(r.id)} className="text-[#FF2A00]" title="Delete"><Trash size={16} /></button>
                  </div>
                </Td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan="7" className="p-6 text-center text-[#5C5C5C]">No {docType}s yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {preview && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setPreview(null)}>
          <div className="bg-white max-w-3xl w-full max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <iframe
              title="preview"
              src={`${API}/invoices/${preview.id}/pdf`}
              className="w-full h-[90vh]"
            />
          </div>
        </div>
      )}
    </div>
  );
}

const Th = ({ children }) => <th className="px-4 py-3 overline">{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
const Row = ({ label, val, bold }) => (
  <div className="flex items-center justify-between">
    <div className={`${bold ? "font-display font-bold text-lg" : "text-[#5C5C5C]"}`}>{label}</div>
    <div className={`font-mono ${bold ? "font-display font-bold text-lg" : ""}`}>₹{Number(val || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
  </div>
);
