import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { Plus, X, FilePdf, CheckCircle, Prohibit, Trash, Warning } from "@phosphor-icons/react";
import api from "../lib/api";
import { askForm } from "../lib/confirm";
import { formatDate } from "../lib/format";
import PdfPreviewModal from "./PdfPreview";
import RowActions from "./RowActions";

const ACK = {
  awaiting: ["Awaiting receipt", "chip-sent"],
  partly_acknowledged: ["Partly acknowledged", "chip-draft"],
  acknowledged: ["Acknowledged", "chip-paid"],
  void: ["Void", "chip-cancelled"],
};
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function Modal({ title, children, onClose }) {
  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[291] w-full max-w-2xl bg-white shadow-2xl max-h-[92vh] overflow-auto" role="dialog" aria-label={title}>
        <div className="flex items-start justify-between p-5 border-b border-[var(--line)] sticky top-0 bg-white z-[1]">
          <div className="font-display font-bold text-xl">{title}</div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>, document.body);
}

function NewTransmittal({ projectId, drawings, purposes, people, onClose, onDone }) {
  const sendable = useMemo(() => drawings.filter((d) => !d.archived && d.current), [drawings]);
  const [picked, setPicked] = useState(() => new Set());
  const [clients, setClients] = useState(() => new Set());
  const [others, setOthers] = useState([]);
  const [form, setForm] = useState({ purpose: "approval", issued_date: todayIso(), note: "", share_in_portal: true });
  const [busy, setBusy] = useState(false);
  const toggle = (set, setSet, id) => { const n = new Set(set); if (n.has(id)) n.delete(id); else n.add(id); setSet(n); };
  const setOther = (i, k, v) => setOthers((rows) => rows.map((r, n) => (n === i ? { ...r, [k]: v } : r)));

  const submit = async (e) => {
    e.preventDefault();
    const recipients = [...[...clients].map((id) => ({ portal_person_id: id })),
      ...others.filter((r) => r.name.trim()).map((r) => ({ name: r.name, company: r.company || null, email: r.email || null }))];
    if (!picked.size) { toast.error("Choose at least one drawing"); return; }
    if (!recipients.length) { toast.error("Add at least one recipient"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/projects/${projectId}/transmittals`, {
        items: [...picked].map((drawing_id) => ({ drawing_id })), recipients,
        purpose: form.purpose, issued_date: form.issued_date || null, note: form.note || null,
        share_in_portal: form.share_in_portal });
      toast.success(`Transmittal ${data.number} issued`);
      onDone(data);
    } catch (ex) { toast.error(ex?.response?.data?.detail || "Could not issue the transmittal"); setBusy(false); }
  };

  return (
    <Modal title="New transmittal" onClose={onClose}>
      <form onSubmit={submit} className="space-y-5" data-testid="transmittal-form">
        <fieldset>
          <legend className="overline mb-2 flex items-center gap-3 w-full">
            <span>Drawings (current revision)</span>
            {sendable.length > 0 && (
              <button type="button" className="ml-auto text-xs normal-case tracking-normal text-[var(--accent-strong)] hover:underline"
                onClick={() => setPicked(picked.size === sendable.length ? new Set() : new Set(sendable.map((d) => d.id)))}>
                {picked.size === sendable.length ? "Clear" : "Select all"}
              </button>
            )}
          </legend>
          {sendable.length === 0 ? <p className="text-sm text-[var(--ink-3)]">Issue a revision of a drawing first.</p> : (
            <div className="border border-[var(--line)] max-h-56 overflow-auto divide-y divide-[var(--line-soft)]">
              {sendable.map((d) => (
                <label key={d.id} className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-[var(--surface-2)]">
                  <input type="checkbox" aria-label={`${d.number} ${d.title} rev ${d.current.rev}`} checked={picked.has(d.id)} onChange={() => toggle(picked, setPicked, d.id)} data-testid={`transmittal-pick-${d.number}`} />
                  <span className="font-mono font-semibold w-20 shrink-0">{d.number}</span>
                  <span className="flex-1 min-w-0 truncate">{d.title}</span>
                  <span className="font-mono text-xs text-[var(--ink-2)]">rev {d.current.rev}</span>
                </label>
              ))}
            </div>
          )}
        </fieldset>

        <fieldset>
          <legend className="overline mb-2">Recipients</legend>
          {people.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {people.map((p) => (
                <label key={p.id} className={`flex items-center gap-2 border px-3 py-1.5 text-sm cursor-pointer ${clients.has(p.id) ? "border-[var(--ink)]" : "border-[var(--line)]"}`}>
                  <input type="checkbox" aria-label={`Send to ${p.name}`} checked={clients.has(p.id)} onChange={() => toggle(clients, setClients, p.id)} data-testid={`transmittal-client-${p.id}`} />
                  {p.name} <span className="text-xs text-[var(--ink-3)]">client link</span>
                </label>
              ))}
            </div>
          )}
          {others.map((r, i) => (
            <div key={i} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 mb-2">
              <input className="input-flat" placeholder="Name" aria-label="Recipient name" value={r.name} onChange={(e) => setOther(i, "name", e.target.value)} />
              <input className="input-flat" placeholder="Company" aria-label="Recipient company" value={r.company} onChange={(e) => setOther(i, "company", e.target.value)} />
              <input className="input-flat" type="email" placeholder="Email (optional)" aria-label="Recipient email" value={r.email} onChange={(e) => setOther(i, "email", e.target.value)} />
              <button type="button" className="btn-ghost" aria-label="Remove recipient" onClick={() => setOthers((rows) => rows.filter((_, n) => n !== i))}><Trash size={14} /></button>
            </div>
          ))}
          <button type="button" className="btn-ghost text-xs" onClick={() => setOthers((rows) => [...rows, { name: "", company: "", email: "" }])} data-testid="transmittal-add-other">
            <Plus size={13} /> Contractor or consultant
          </button>
          {people.length === 0 && <p className="text-xs text-[var(--ink-3)] mt-1">Clients with a personal link (Client tab) can acknowledge receipt in the portal.</p>}
        </fieldset>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-xs text-[var(--ink-2)]">Issued for
            <select className="input-flat w-full mt-1" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} data-testid="transmittal-purpose">
              {Object.entries(purposes).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </label>
          <label className="block text-xs text-[var(--ink-2)]">Date
            <input type="date" className="input-flat w-full mt-1" value={form.issued_date} onChange={(e) => setForm({ ...form, issued_date: e.target.value })} />
          </label>
        </div>
        <label className="block text-xs text-[var(--ink-2)]">Note (optional)
          <textarea className="input-flat w-full mt-1" rows={2} maxLength={1000} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.share_in_portal} onChange={(e) => setForm({ ...form, share_in_portal: e.target.checked })} />
          Show in the client portal
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy} data-testid="transmittal-issue">{busy ? "Issuing…" : "Issue transmittal"}</button>
        </div>
      </form>
    </Modal>
  );
}

/** Transmittals: numbered issue sets with recipients and receipt acknowledgement. */
export default function DrawingTransmittals({ projectId, drawings = [], purposes = {}, onCount }) {
  const [data, setData] = useState(null);
  const [people, setPeople] = useState([]);
  const [creating, setCreating] = useState(false);
  const [pdf, setPdf] = useState(null);

  const load = () => api.get(`/projects/${projectId}/transmittals`)
    .then(({ data: d }) => { setData(d); onCount && onCount(d.summary?.total || 0); })
    .catch((e) => { setData({ transmittals: [], summary: {} }); toast.error(e?.response?.data?.detail || "Could not load transmittals"); });
  useEffect(() => {
    load();
    api.get(`/projects/${projectId}/approvals`).then(({ data: d }) => setPeople(d.people || [])).catch(() => setPeople([]));
  }, [projectId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const recordReceipt = async (t, r) => {
    const v = await askForm({
      title: `Record receipt by ${r.name}`,
      body: `For ${t.number}: use this when you have a signed copy or a reply confirming they received the drawings.`,
      fields: [
        { name: "received_date", label: "Received on", type: "date", defaultValue: todayIso(), required: true },
        { name: "note", label: "Note (optional)", placeholder: "Signed copy received at site" },
      ],
      confirmLabel: "Record receipt",
    });
    if (!v) return;
    try { await api.post(`/transmittals/${t.id}/recipients/${r.id}/acknowledge`, { received_date: v.received_date, note: v.note || null }); toast.success("Receipt recorded"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not record receipt"); }
  };

  const voidIt = async (t) => {
    const v = await askForm({
      title: `Void ${t.number}?`,
      body: "It stays on record marked VOID and disappears from the client portal. Issue a corrected transmittal afterwards.",
      fields: [{ name: "reason", label: "Reason", required: true, placeholder: "Wrong revision attached" }],
      confirmLabel: "Void transmittal", danger: true,
    });
    if (!v) return;
    try { await api.post(`/transmittals/${t.id}/void`, { reason: v.reason }); toast.success(`${t.number} voided`); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not void"); }
  };

  if (!data) return <div className="overline p-4">LOADING…</div>;
  const rows = data.transmittals || [];
  const s = data.summary || {};

  return (
    <div className="space-y-4" data-testid="drawing-transmittals">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-sm text-[var(--ink-2)] mr-auto">
          {s.total || 0} transmittal{s.total === 1 ? "" : "s"} · {s.awaiting || 0} awaiting receipt
          {s.with_superseded ? <span className="text-[var(--danger)]"> · {s.with_superseded} with superseded drawings</span> : null}
        </div>
        {data.can_issue && (
          <button type="button" className="btn-primary" onClick={() => setCreating(true)} data-testid="transmittal-new"><Plus size={14} /> New transmittal</button>
        )}
      </div>

      {rows.length === 0 && (
        <div className="border border-[var(--line)] p-8 text-center text-sm text-[var(--ink-3)]">
          No transmittals yet. A transmittal records which drawing revisions went to whom, for what, and who confirmed receipt.
        </div>
      )}

      {rows.map((t) => {
        const [label, cls] = ACK[t.ack_status] || ACK.awaiting;
        const isVoid = t.ack_status === "void";
        return (
          <article key={t.id} className={`border border-[var(--line)] ${isVoid ? "opacity-70" : ""}`} data-testid={`transmittal-${t.number}`}>
            <div className="flex flex-wrap items-center gap-2 p-4 border-b border-[var(--line-soft)]">
              <span className="font-mono font-bold">{t.number}</span>
              <span className={`status-chip ${cls}`}>{label}</span>
              <span className="text-xs text-[var(--ink-2)]">{formatDate(t.issued_date)} · {purposes[t.purpose] || t.purpose}{t.share_in_portal ? " · in client portal" : ""}</span>
              <span className="ml-auto flex items-center gap-1">
                <button type="button" className="btn-ghost text-xs" onClick={() => setPdf(t)} data-testid={`transmittal-pdf-${t.number}`}><FilePdf size={13} /> PDF</button>
                {data.can_issue && !isVoid && (
                  <RowActions label={`transmittal ${t.number}`} actions={[
                    { label: "Void transmittal", icon: Prohibit, danger: true, onSelect: () => voidIt(t) },
                  ]} />
                )}
              </span>
            </div>
            {isVoid && <div className="px-4 pt-3 text-xs text-[var(--danger)]">Void: {t.void_reason} ({t.voided_by_name})</div>}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4">
              <div>
                <div className="overline mb-1">Drawings</div>
                <ul className="text-sm space-y-1">
                  {t.items.map((i) => (
                    <li key={i.drawing_id} className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-mono font-semibold">{i.number}</span>
                      <span className="font-mono text-xs">rev {i.rev}</span>
                      <span className="text-[var(--ink-2)] truncate max-w-[220px]">{i.title}</span>
                      {i.superseded_by && (
                        <span className="text-[11px] font-semibold text-[var(--danger)] inline-flex items-center gap-1" data-testid={`transmittal-superseded-${i.number}`}>
                          <Warning size={12} /> superseded by rev {i.superseded_by}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="overline mb-1">Recipients</div>
                <ul className="text-sm space-y-1.5">
                  {t.recipients.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      {r.acknowledged_at ? <CheckCircle size={15} weight="fill" className="text-[var(--success)]" /> : <span className="w-[15px] h-[15px] rounded-full border border-[var(--line-strong)]" />}
                      <span className="font-semibold">{r.name}</span>
                      {r.company && <span className="text-xs text-[var(--ink-3)]">{r.company}</span>}
                      {r.acknowledged_at ? (
                        <span className="text-xs text-[var(--ink-2)]">
                          received {formatDate(r.received_date || r.acknowledged_at)} {r.acknowledged_via === "portal" ? "· client portal" : `· recorded by ${r.recorded_by_name}`}
                        </span>
                      ) : data.can_issue && !isVoid && (
                        <button type="button" className="text-xs text-[var(--accent-strong)] hover:underline" onClick={() => recordReceipt(t, r)} data-testid={`transmittal-record-${t.number}-${r.id}`}>
                          Record receipt
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            {t.note && <p className="px-4 pb-4 text-sm text-[var(--ink-2)] [overflow-wrap:anywhere]">{t.note}</p>}
          </article>
        );
      })}

      {creating && (
        <NewTransmittal projectId={projectId} drawings={drawings} purposes={purposes} people={people}
          onClose={() => setCreating(false)} onDone={() => { setCreating(false); load(); }} />
      )}
      {pdf && <PdfPreviewModal path={`/transmittals/${pdf.id}/pdf`} title={`Transmittal ${pdf.number}`}
        filename={`transmittal-${pdf.number}.pdf`} onClose={() => setPdf(null)} />}
    </div>
  );
}
