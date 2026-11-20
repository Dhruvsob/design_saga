import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, PaperPlaneTilt, CheckCircle, PencilSimple, Trash, X } from "@phosphor-icons/react";
import api, { optionalList } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { askForm, confirmAction } from "../lib/confirm";
import { errText } from "../lib/errors";
import { formatDate } from "../lib/format";
import RowActions from "./RowActions";
import SearchSelect from "./SearchSelect";

// Room-wise selections (P2.3): what the client approved per room before buying.
export const SELECTION_STATUS = {
  proposed: ["To send", "chip-draft"],
  sent: ["Waiting for client", "chip-sent"],
  approved: ["Approved", "chip-paid"],
  changes_requested: ["Client asked for changes", "chip-overdue"],
};
const ROOMS = ["Living Room", "Kitchen", "Master Bedroom", "Kids Bedroom", "Guest Bedroom", "Master Bath",
  "Common Bath", "Dining", "Foyer", "Balcony", "Study", "Pooja", "Utility"];
const EMPTY = { room: "", product_id: "", item: "", specification: "", vendor_id: "", supplier: "",
  quantity: "", unit: "", notes: "" };

function SelectionForm({ initial, products, vendors, onCancel, onSave }) {
  const [f, setF] = useState(initial);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await onSave(f); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="selection-form">
      <label className="text-xs text-[var(--ink-2)]">Room or area
        <input className="input-flat w-full mt-1" list="selection-rooms" required value={f.room} onChange={set("room")}
               placeholder="Kitchen" data-testid="selection-room" />
        <datalist id="selection-rooms">{ROOMS.map((r) => <option key={r} value={r} />)}</datalist>
      </label>
      <label className="text-xs text-[var(--ink-2)]">From the library (optional)
        <SearchSelect value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })} aria-label="Library product"
                      className="mt-1" data-testid="selection-product">
          <option value="">Not from the library</option>
          {products.map((p) => <option key={p.id} value={p.id}>{[p.brand, p.name].filter(Boolean).join(" ")}</option>)}
        </SearchSelect>
      </label>
      <label className="text-xs text-[var(--ink-2)] md:col-span-2">Item
        <input className="input-flat w-full mt-1" value={f.item} onChange={set("item")}
               placeholder={f.product_id ? "Taken from the library item" : "Kitchen counter top"} data-testid="selection-item" />
      </label>
      <label className="text-xs text-[var(--ink-2)] md:col-span-2">Specification
        <textarea className="input-flat w-full mt-1" rows={2} value={f.specification} onChange={set("specification")}
                  placeholder={f.product_id ? "Taken from the library item" : "Quartz, 20 mm, honed, mitred edge"} data-testid="selection-spec" />
      </label>
      <label className="text-xs text-[var(--ink-2)]">Supplier
        <SearchSelect value={f.vendor_id} onChange={(e) => setF({ ...f, vendor_id: e.target.value })} aria-label="Supplier" className="mt-1"
                      data-testid="selection-vendor">
          <option value="">{vendors.length ? "Not one of our vendors" : "Type the supplier below"}</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </SearchSelect>
        {!f.vendor_id && <input className="input-flat w-full mt-1" value={f.supplier} onChange={set("supplier")} placeholder="Supplier name (optional)" aria-label="Supplier name" />}
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-[var(--ink-2)]">Quantity
          <input className="input-flat w-full mt-1" type="number" min="0" step="any" value={f.quantity} onChange={set("quantity")} />
        </label>
        <label className="text-xs text-[var(--ink-2)]">Unit
          <input className="input-flat w-full mt-1" value={f.unit} onChange={set("unit")} placeholder="sqft" />
        </label>
      </div>
      <label className="text-xs text-[var(--ink-2)] md:col-span-2">Notes for the team (not sent to the client)
        <input className="input-flat w-full mt-1" value={f.notes} onChange={set("notes")} />
      </label>
      <div className="md:col-span-2 flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onCancel}><X size={14} /> Cancel</button>
        <button type="submit" className="btn-primary" disabled={busy} data-testid="selection-save">{busy ? "Saving…" : "Save selection"}</button>
      </div>
    </form>
  );
}

export default function ProjectSelections({ projectId }) {
  const { hasPerm } = useAuth();
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);          // null | "new" | selection
  const [products, setProducts] = useState([]);
  const [vendors, setVendors] = useState([]);

  const load = () => api.get(`/projects/${projectId}/selections`)
    .then(({ data: d }) => setData(d))
    .catch((e) => { setData({ selections: [], summary: {}, error: errText(e, "Selections could not be loaded.") }); });
  useEffect(() => { load(); }, [projectId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const libraryAllowed = hasPerm("quotations.read") || hasPerm("vendors.read") || hasPerm("purchase_orders.read");
  const openForm = async (row) => {
    if (!products.length && libraryAllowed) {
      const { data: p } = await optionalList(true, "/products", { params: { page_size: 100 } });
      setProducts(Array.isArray(p) ? p : p?.items || []);
    }
    if (!vendors.length) {
      const { data: v } = await optionalList(hasPerm("vendors.read"), "/vendors");
      setVendors(Array.isArray(v) ? v : v?.items || v?.vendors || []);
    }
    setEditing(row || "new");
  };

  const save = async (f) => {
    const body = {
      room: f.room.trim(), item: f.item.trim() || null, product_id: f.product_id || null,
      specification: f.specification.trim() || null, vendor_id: f.vendor_id || null,
      supplier: f.vendor_id ? null : (f.supplier.trim() || null),
      quantity: f.quantity === "" ? null : Number(f.quantity), unit: f.unit.trim() || null, notes: f.notes.trim() || null,
    };
    try {
      if (editing === "new") await api.post(`/projects/${projectId}/selections`, body);
      else {
        const { data: row } = await api.patch(`/selections/${editing.id}`, body);
        if (editing.status !== "proposed" && row.status === "proposed") toast("The client will be asked again: the selection changed after their decision.");
      }
      setEditing(null);
      load();
    } catch (e) { toast.error(errText(e, "Could not save the selection")); }
  };

  const send = async (row) => {
    try { await api.post(`/selections/${row.id}/send`, {}); toast.success("Sent to the client portal"); load(); }
    catch (e) { toast.error(errText(e, "Could not send to the client")); }
  };
  const record = async (row) => {
    const v = await askForm({
      title: `Record the client's decision: ${row.item}`,
      body: "For a decision the client gave in person or on a call. It is recorded in your name with your note.",
      fields: [
        { name: "decision", label: "Decision", options: [{ value: "approve", label: "Approved" }, { value: "changes", label: "Asked for changes" }], defaultValue: "approve" },
        { name: "note", label: "How and when", required: true, placeholder: "Approved on site visit, 20 Nov" },
      ],
      confirmLabel: "Record decision",
    });
    if (!v) return;
    try { await api.post(`/selections/${row.id}/decision`, { decision: v.decision || "approve", note: v.note }); load(); }
    catch (e) { toast.error(errText(e, "Could not record the decision")); }
  };
  const remove = async (row) => {
    if (!await confirmAction(`Remove “${row.item}” from ${row.room}?`)) return;
    try { await api.delete(`/selections/${row.id}`); load(); }
    catch (e) { toast.error(errText(e, "Could not remove the selection")); }
  };

  const byRoom = useMemo(() => {
    const m = new Map();
    for (const r of data?.selections || []) {
      if (!m.has(r.room)) m.set(r.room, []);
      m.get(r.room).push(r);
    }
    return [...m.entries()];
  }, [data]);

  if (!data) return <div className="text-sm text-[var(--ink-2)]" role="status">Loading selections…</div>;
  const s = data.summary || {};
  const canManage = Boolean(data.can_manage);
  const formInitial = editing && editing !== "new"
    ? { ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, editing[k] ?? ""])) }
    : EMPTY;

  return (
    <div className="space-y-6" data-testid="project-selections">
      {data.error && <div role="alert" className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-sm px-3 py-2">{data.error}</div>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="selections-summary">
        <div className="card-flat"><div className="overline">APPROVED</div><div className="font-display font-bold text-3xl">{s.approved || 0}<span className="text-base text-[var(--ink-3)]"> / {s.total || 0}</span></div></div>
        <div className="card-flat"><div className="overline">WAITING FOR CLIENT</div><div className="font-display font-bold text-3xl">{s.sent || 0}</div></div>
        <div className="card-flat"><div className="overline">TO SEND</div><div className="font-display font-bold text-3xl">{s.proposed || 0}</div></div>
        <div className="card-flat"><div className="overline">CHANGES ASKED</div><div className="font-display font-bold text-3xl">{s.changes_requested || 0}</div></div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <p className="mr-auto text-sm text-[var(--ink-2)] max-w-2xl">
          What the client chose for each room. Only <b>approved</b> selections should be ordered.
          {canManage && !data.client_contacts && " To send selections to the client, first add a client link under Client → Client approvals."}
        </p>
        {canManage && editing === null && (
          <button type="button" className="btn-primary" onClick={() => openForm(null)} data-testid="selection-add"><Plus size={14} /> Add selection</button>
        )}
      </div>

      {editing !== null && (
        <SelectionForm key={editing === "new" ? "new" : editing.id} initial={formInitial}
                       products={products} vendors={vendors} onCancel={() => setEditing(null)} onSave={save} />
      )}

      {byRoom.length === 0 ? (
        <div className="border border-[var(--line)] p-8 text-center text-sm text-[var(--ink-2)]">
          No selections yet. Add the finishes, fittings and furniture the client needs to approve, room by room.
        </div>
      ) : byRoom.map(([room, rows]) => (
        <section key={room} className="border border-[var(--line)]" data-testid={`selection-room-${room}`}>
          <h3 className="px-4 py-2 border-b border-[var(--line)] font-display font-bold text-lg bg-[var(--surface-2)]">{room}</h3>
          <ul className="divide-y divide-[var(--line-soft)]">
            {rows.map((r) => {
              const [label, cls] = SELECTION_STATUS[r.status] || [r.status, "chip-draft"];
              return (
                <li key={r.id} className="p-4 flex flex-wrap items-start gap-3" data-testid={`selection-row-${r.id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold [overflow-wrap:anywhere]">{r.item}</span>
                      <span className={`status-chip ${cls}`} data-testid={`selection-status-${r.id}`}>{label}</span>
                    </div>
                    {r.specification && <div className="text-sm text-[var(--ink-2)] mt-1 [overflow-wrap:anywhere]">{r.specification}</div>}
                    <div className="text-xs text-[var(--ink-3)] mt-1">
                      {[r.supplier && `Supplier: ${r.supplier}`, r.quantity ? `${r.quantity} ${r.unit || ""}`.trim() : null]
                        .filter(Boolean).join(" · ") || "No supplier yet"}
                    </div>
                    {r.decided_at && (
                      <div className="text-sm mt-1">
                        <b>{r.decided_by_name}</b> {r.status === "approved" ? "approved" : "asked for changes"} on {formatDate(r.decided_at)}
                        {r.decision_comment && <span className="text-[var(--ink-2)]">: “{r.decision_comment}”</span>}
                      </div>
                    )}
                  </div>
                  {canManage && (
                    <RowActions label={`selection ${r.item}`} testid={`selection-actions-${r.id}`} actions={[
                      { label: "Send to client", icon: PaperPlaneTilt, hidden: !(r.status === "proposed" || r.status === "changes_requested"), onSelect: () => send(r), testid: `selection-send-${r.id}` },
                      { label: "Record client's decision", icon: CheckCircle, hidden: r.status === "approved", onSelect: () => record(r) },
                      { label: "Edit", icon: PencilSimple, onSelect: () => openForm(r) },
                      { label: "Remove", icon: Trash, danger: true, divider: true, hidden: r.status === "approved", onSelect: () => remove(r) },
                    ]} />
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
