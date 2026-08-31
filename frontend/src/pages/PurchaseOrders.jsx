import { useEffect, useState } from "react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import {
  Package, Plus, Warning, CheckSquare, PaperPlaneTilt, X, ArrowsClockwise, Truck, ClipboardText,
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
  sent: "bg-[#F5F4F0] text-[#8B7F6A]",
  partial: "bg-[#FFF4E5] text-[#7A4E1A]",
  received: "bg-[#EFF7EF] text-[#1D633E]",
  closed: "bg-[#EFF7EF] text-[#1D633E]",
  cancelled: "bg-[#FCEEEC] text-[#B22B22]",
};

export default function PurchaseOrders() {
  const [pos, setPos] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [p, v] = await Promise.all([
        api.get("/purchase-orders"),
        api.get("/vendors"),
      ]);
      setPos(p.data); setVendors(v.data);
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail));
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading) return <div className="skeleton h-96"></div>;

  return (
    <div className="space-y-8" data-testid="po-page">
      <PageHero eyebrow="PROCUREMENT / PURCHASE ORDERS"
        title="Every rupee, tracked from PO to payment."
        kicker="Auto 3-way match against Goods Receipts and vendor bills."
        count={pos.length}>
        <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="create-po-btn">
          <Plus size={13}/> New PO
        </button>
      </PageHero>

      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] p-3 text-sm text-[#B22B22]"><Warning size={13} className="inline mr-1"/>{err}</div>}

      <div className="card-flat p-0 overflow-hidden">
        <div className="p-6 pb-4"><div className="overline">PO LEDGER · {pos.length}</div></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px]" data-testid="po-table">
            <thead className="bg-[#FAFAFA] border-y border-[#E5E5E5]"><tr className="text-left">
              <Th>PO #</Th><Th>Vendor</Th><Th>Order Date</Th><Th>Expected</Th>
              <Th>Grand Total</Th><Th>Status</Th>
            </tr></thead>
            <tbody>
              {pos.map((po) => (
                <tr key={po.id} className="row-hover border-b border-[#F0F0F0] cursor-pointer"
                    onClick={() => setDetail(po.id)} data-testid={`po-row-${po.id}`}>
                  <Td className="font-mono text-sm accent-blue font-semibold">{po.po_number}</Td>
                  <Td className="text-sm">{po.vendor_name}</Td>
                  <Td className="font-mono text-xs">{po.order_date}</Td>
                  <Td className="font-mono text-xs">{po.expected_delivery || "—"}</Td>
                  <Td className="font-mono text-sm">{fmtMoney(po.grand_total)}</Td>
                  <Td><span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${STATUS_TONE[po.status] || "bg-[#F0F0F0]"}`}>{po.status}</span></Td>
                </tr>
              ))}
              {pos.length === 0 && <tr><td colSpan={6} className="p-12 text-center text-[#5C5C5C]">No purchase orders yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && <CreatePO vendors={vendors} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {detail && <PODetail poId={detail} onClose={() => setDetail(null)} onChange={load} />}
    </div>
  );
}

function CreatePO({ vendors, onClose, onCreated }) {
  const [f, setF] = useState({
    vendor_id: vendors[0]?.id || "", expected_delivery: "", payment_terms: "Net 30",
    delivery_address: "", notes: "", lines: [{ item_name: "", quantity: 1, unit: "nos", unit_price: 0, tax_rate: 18 }],
  });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");

  const addLine = () => setF((s) => ({ ...s, lines: [...s.lines, { item_name: "", quantity: 1, unit: "nos", unit_price: 0, tax_rate: 18 }] }));
  const upLine = (i, patch) => setF((s) => ({ ...s, lines: s.lines.map((l, j) => j === i ? { ...l, ...patch } : l) }));
  const delLine = (i) => setF((s) => ({ ...s, lines: s.lines.filter((_, j) => j !== i) }));
  const subtotal = f.lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0), 0);
  const tax = f.lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0) * Number(l.tax_rate || 0) / 100, 0);

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api.post("/purchase-orders", f);
      onCreated();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Create failed"));
    } finally { setBusy(false); }
  };

  return (
    <Modal onClose={onClose} title="New Purchase Order" eyebrow="PROCUREMENT" wide>
      <form onSubmit={submit} className="space-y-4" data-testid="po-create-form">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <F label="Vendor *">
            <select required data-testid="po-vendor" className="input-flat w-full" value={f.vendor_id} onChange={(e) => setF({...f, vendor_id: e.target.value})}>
              <option value="">— Select —</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </F>
          <F label="Expected delivery"><input type="date" className="input-flat w-full" value={f.expected_delivery} onChange={(e) => setF({...f, expected_delivery: e.target.value})} /></F>
          <F label="Payment terms"><input className="input-flat w-full" value={f.payment_terms} onChange={(e) => setF({...f, payment_terms: e.target.value})} /></F>
        </div>
        <F label="Delivery address"><input className="input-flat w-full" value={f.delivery_address} onChange={(e) => setF({...f, delivery_address: e.target.value})} /></F>

        <div className="overline">LINE ITEMS</div>
        <div className="space-y-2">
          {f.lines.map((l, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center" data-testid={`po-line-${i}`}>
              <input required placeholder="Item" className="input-flat col-span-4" value={l.item_name} onChange={(e) => upLine(i, {item_name: e.target.value})} />
              <input type="number" placeholder="Qty" step="0.01" className="input-flat col-span-2 font-mono" value={l.quantity} onChange={(e) => upLine(i, {quantity: Number(e.target.value)})} />
              <input placeholder="Unit" className="input-flat col-span-1" value={l.unit} onChange={(e) => upLine(i, {unit: e.target.value})} />
              <input type="number" placeholder="Price" step="0.01" className="input-flat col-span-2 font-mono" value={l.unit_price} onChange={(e) => upLine(i, {unit_price: Number(e.target.value)})} />
              <input type="number" placeholder="Tax %" className="input-flat col-span-1 font-mono" value={l.tax_rate} onChange={(e) => upLine(i, {tax_rate: Number(e.target.value)})} />
              <div className="col-span-1 font-mono text-xs text-right">{fmtMoney(l.quantity * l.unit_price)}</div>
              <button type="button" onClick={() => delLine(i)} className="btn-ghost col-span-1 text-[#B22B22]"><X size={12}/></button>
            </div>
          ))}
          <button type="button" onClick={addLine} className="btn-ghost text-xs" data-testid="po-add-line"><Plus size={11}/> Add line</button>
        </div>

        <div className="grid grid-cols-3 gap-3 pt-2 border-t border-[#E5E5E5]">
          <div className="p-3 bg-[#F5F5F5]"><div className="overline text-[10px]">SUBTOTAL</div><div className="font-mono font-bold">{fmtMoney(subtotal)}</div></div>
          <div className="p-3 bg-[#F5F5F5]"><div className="overline text-[10px]">TAX</div><div className="font-mono font-bold">{fmtMoney(tax)}</div></div>
          <div className="p-3 bg-[#8B7F6A]/10"><div className="overline text-[10px]">GRAND TOTAL</div><div className="font-mono font-bold text-lg accent-blue">{fmtMoney(subtotal + tax)}</div></div>
        </div>

        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy || !f.vendor_id} className="btn-primary" data-testid="po-submit">{busy ? "Creating…" : "Create PO"}</button>
        </div>
      </form>
    </Modal>
  );
}

function PODetail({ poId, onClose, onChange }) {
  const [po, setPo] = useState(null);
  const [grns, setGrns] = useState([]);
  const [match, setMatch] = useState(null);
  const [showGRN, setShowGRN] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [p, g, m] = await Promise.all([
        api.get(`/purchase-orders/${poId}`),
        api.get(`/grns?po_id=${poId}`),
        api.get(`/purchase-orders/${poId}/match`),
      ]);
      setPo(p.data); setGrns(g.data); setMatch(m.data);
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
  };
  useEffect(() => { load(); }, [poId]);

  const sendPO = async () => {
    try { await api.post(`/purchase-orders/${poId}/send`); await load(); onChange && onChange(); }
    catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
  };
  const cancelPO = async () => {
    if (!window.confirm("Cancel this PO?")) return;
    try { await api.post(`/purchase-orders/${poId}/cancel`); await load(); onChange && onChange(); }
    catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
  };

  if (!po) return <Modal onClose={onClose} title="Loading…" wide><div className="skeleton h-64"></div></Modal>;
  return (
    <Modal onClose={onClose} title={po.po_number} eyebrow={`PO · ${po.vendor_name}`} wide>
      {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 mb-3">{err}</div>}

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <span className={`text-[10px] font-mono uppercase px-3 py-1 ${STATUS_TONE[po.status]}`}>{po.status}</span>
        <span className="text-sm text-[#5C5C5C]">Order: {po.order_date}</span>
        <span className="text-sm text-[#5C5C5C]">Expected: {po.expected_delivery || "—"}</span>
        <span className="font-mono font-bold text-lg ml-auto accent-blue">{fmtMoney(po.grand_total)}</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {po.status === "draft" && (
          <button onClick={sendPO} className="btn-primary text-xs" data-testid="po-send"><PaperPlaneTilt size={12}/> Send to vendor</button>
        )}
        {["sent","partial"].includes(po.status) && (
          <button onClick={() => setShowGRN(true)} className="btn-primary text-xs" data-testid="grn-btn"><Truck size={12}/> Record GRN</button>
        )}
        {["draft","sent"].includes(po.status) && grns.length === 0 && (
          <button onClick={cancelPO} className="btn-ghost text-xs text-[#B22B22]"><X size={12}/> Cancel PO</button>
        )}
      </div>

      <div className="overline mb-2">LINE ITEMS</div>
      <div className="border border-[#E5E5E5] mb-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]"><tr className="text-left">
            <Th>Item</Th><Th>Ordered</Th><Th>Received</Th><Th>Unit Price</Th><Th>Line Total</Th>
          </tr></thead>
          <tbody>
            {po.lines.map((l) => (
              <tr key={l.id} className="border-b border-[#F0F0F0]">
                <Td>{l.item_name}</Td>
                <Td className="font-mono">{l.quantity} {l.unit}</Td>
                <Td className="font-mono">{l.received_qty_total || 0} / {l.quantity}</Td>
                <Td className="font-mono">{fmtMoney(l.unit_price)}</Td>
                <Td className="font-mono">{fmtMoney(l.quantity * l.unit_price)}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overline mb-2"><Truck size={11} className="inline mr-1"/> GOODS RECEIPTS · {grns.length}</div>
      {grns.length > 0 ? (
        <div className="space-y-2 mb-6">
          {grns.map((g) => (
            <div key={g.id} className="border border-[#E5E5E5] p-3 flex items-center gap-3 text-sm">
              <div className="font-mono accent-blue font-semibold">{g.grn_number}</div>
              <div className="text-[#5C5C5C]">{g.received_date}</div>
              <div className="font-mono ml-auto">{fmtMoney(g.total_value)}</div>
            </div>
          ))}
        </div>
      ) : <div className="text-xs text-[#5C5C5C] mb-6">No goods receipts yet.</div>}

      {match && (
        <div>
          <div className="overline mb-2"><ArrowsClockwise size={11} className="inline mr-1"/> 3-WAY MATCH REPORT</div>
          <div className="border border-[#E5E5E5] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]"><tr className="text-left">
                <Th>Item</Th><Th>PO</Th><Th>GRN</Th><Th>Billed</Th><Th>Variance</Th><Th>Match</Th>
              </tr></thead>
              <tbody>
                {match.lines.map((l) => (
                  <tr key={l.po_line_id} className="border-b border-[#F0F0F0]">
                    <Td>{l.item}</Td>
                    <Td className="font-mono">{l.ordered_qty}</Td>
                    <Td className="font-mono">{l.received_qty}</Td>
                    <Td className="font-mono">{l.billed_qty}</Td>
                    <Td className={`font-mono ${l.qty_variance ? "text-[#B22B22]" : "text-[#1D633E]"}`}>{l.qty_variance || "—"}</Td>
                    <Td>{l.matched ? <CheckSquare size={16} className="text-[#1D633E]"/> : <span className="text-[#5C5C5C]">—</span>}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 text-xs text-[#5C5C5C]">
            PO total: <b>{fmtMoney(match.po_grand_total)}</b> · Billed: <b>{fmtMoney(match.bill_total)}</b>
            {match.all_matched && <span className="ml-2 accent-blue">✓ Fully matched</span>}
          </div>
        </div>
      )}

      {showGRN && <RecordGRN po={po} onClose={() => setShowGRN(false)} onSaved={() => { setShowGRN(false); load(); onChange && onChange(); }} />}
    </Modal>
  );
}

function RecordGRN({ po, onClose, onSaved }) {
  const [lines, setLines] = useState(po.lines.map((l) => ({
    po_line_id: l.id, item_name: l.item_name, ordered: l.quantity,
    already: l.received_qty_total || 0,
    received_qty: Math.max(0, l.quantity - (l.received_qty_total || 0)), rejected_qty: 0, remarks: "",
  })));
  const [challan, setChallan] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      await api.post("/grns", {
        po_id: po.id, delivery_challan_no: challan,
        lines: lines.filter((l) => l.received_qty > 0).map((l) => ({
          po_line_id: l.po_line_id, received_qty: Number(l.received_qty),
          rejected_qty: Number(l.rejected_qty || 0), remarks: l.remarks,
        })),
      });
      onSaved();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "GRN failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} title="Record Goods Receipt" eyebrow={`GRN · ${po.po_number}`} wide>
      <form onSubmit={submit} className="space-y-3" data-testid="grn-form">
        <F label="Delivery Challan No."><input className="input-flat w-full font-mono" value={challan} onChange={(e) => setChallan(e.target.value)} /></F>
        <div className="border border-[#E5E5E5] overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]"><tr className="text-left">
              <Th>Item</Th><Th>Ordered</Th><Th>Already</Th><Th>Receive Now</Th><Th>Rejected</Th><Th>Remarks</Th>
            </tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={l.po_line_id} className="border-b border-[#F0F0F0]">
                  <Td>{l.item_name}</Td>
                  <Td className="font-mono text-xs">{l.ordered}</Td>
                  <Td className="font-mono text-xs">{l.already}</Td>
                  <Td><input type="number" step="0.01" className="input-flat w-24 font-mono" value={l.received_qty} onChange={(e) => setLines((s) => s.map((x, j) => j === i ? {...x, received_qty: Number(e.target.value)} : x))} data-testid={`grn-recv-${i}`} /></Td>
                  <Td><input type="number" step="0.01" className="input-flat w-20 font-mono" value={l.rejected_qty} onChange={(e) => setLines((s) => s.map((x, j) => j === i ? {...x, rejected_qty: Number(e.target.value)} : x))} /></Td>
                  <Td><input className="input-flat w-full" value={l.remarks} onChange={(e) => setLines((s) => s.map((x, j) => j === i ? {...x, remarks: e.target.value} : x))} /></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button disabled={busy} className="btn-primary" data-testid="grn-submit">{busy ? "Recording…" : "Record GRN"}</button>
        </div>
      </form>
    </Modal>
  );
}

function F({ label, children }) {
  return <label className="block"><div className="text-xs text-[#5C5C5C] mb-1">{label}</div>{children}</label>;
}
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className={`bg-white p-6 w-full border border-[#E5E5E5] max-h-[92vh] overflow-y-auto ${wide ? "max-w-6xl" : "max-w-2xl"}`}>
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
