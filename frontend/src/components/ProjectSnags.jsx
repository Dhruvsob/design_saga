import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { Plus, X, Camera, CheckCircle, ArrowCounterClockwise, Prohibit, PencilSimple, Trash, ClockCounterClockwise } from "@phosphor-icons/react";
import api from "../lib/api";
import { formatDate } from "../lib/format";
import { askForm, confirmAction } from "../lib/confirm";
import RowActions from "./RowActions";
import { AuthImage, shrinkPhoto } from "./SiteVisits";

const STATUS = {
  open: ["Open", "chip-overdue"], fixed: ["Fixed · to verify", "chip-sent"],
  closed: ["Closed", "chip-paid"], wont_fix: ["Won't fix", "chip-cancelled"],
};
const PRIORITY = { urgent: "Urgent", high: "High", normal: "Normal", low: "Low" };

function Modal({ title, children, onClose }) {
  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}
        className="relative z-[291] w-full max-w-lg bg-white shadow-2xl max-h-[90vh] overflow-auto">
        <div className="flex items-start justify-between p-5 border-b border-[var(--line)]">
          <div className="font-display font-bold text-xl">{title}</div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>, document.body);
}

/** Site snags: raise with a photo, fix with a photo, verify and close. */
export default function ProjectSnags({ projectId, employees = [] }) {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("active");
  const [form, setForm] = useState(null);      // null | {} new | snag (edit)
  const [fixing, setFixing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [vendors, setVendors] = useState([]);

  const load = () => api.get(`/projects/${projectId}/snags`).then(({ data: d }) => setData(d))
    .catch((e) => { setData({ snags: [], counts: {} }); toast.error(e?.response?.data?.detail || "Could not load snags"); });
  useEffect(() => { load(); }, [projectId]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.get("/vendors").then(({ data: d }) => setVendors(Array.isArray(d) ? d : d.items || [])).catch(() => setVendors([])); }, []);

  const mine = new Set(data?.my_ids || []);
  const rows = useMemo(() => (data?.snags || []).filter((s) =>
    filter === "all" ? true : filter === "active" ? ["open", "fixed"].includes(s.status)
      : filter === "mine" ? mine.has(s.assignee_user_id) && s.status === "open" : s.status === filter),
  [data, filter]);   // eslint-disable-line react-hooks/exhaustive-deps
  const people = employees.filter((e) => e.user_id).map((e) => ({ value: e.user_id, label: `${e.first_name || ""} ${e.last_name || ""}`.trim() || e.email }));

  const setStatus = async (s, action) => {
    let note = null;
    if (action !== "close") {
      const v = await askForm({ title: action === "reopen" ? `Reopen ${s.number}` : `${s.number}: won't fix`,
        fields: [{ name: "note", label: "Why?", required: true }], confirmLabel: action === "reopen" ? "Reopen" : "Save" });
      if (!v) return;
      note = v.note;
    } else if (!await confirmAction(`Verify the fix and close ${s.number}?`)) return;
    try { await api.post(`/snags/${s.id}/status`, { action, note }); toast.success("Updated"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not update"); }
  };
  const remove = async (s) => {
    if (!await confirmAction(`Delete ${s.number}? Use this only for a snag raised by mistake.`)) return;
    try { await api.delete(`/snags/${s.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not delete"); }
  };

  const c = data?.counts || {};
  return (
    <div className="space-y-4" data-testid="project-snags">
      <div className="flex flex-wrap items-center gap-1.5">
        {[["active", `Open & to verify ${(c.open || 0) + (c.fixed || 0)}`], ["mine", "Assigned to me"], ["fixed", `To verify ${c.fixed || 0}`], ["closed", `Closed ${c.closed || 0}`], ["all", "All"]].map(([id, label]) => (
          <button key={id} type="button" onClick={() => setFilter(id)} aria-pressed={filter === id}
            className={`px-3 py-1.5 text-xs border rounded-full ${filter === id ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--line)]"}`}>{label}</button>
        ))}
        {data?.can_raise && <button type="button" className="btn-primary ml-auto" onClick={() => setForm({})} data-testid="snag-add"><Plus size={14} /> Raise snag</button>}
      </div>

      <div className="space-y-2">
        {data === null && <div className="overline">LOADING…</div>}
        {data && rows.length === 0 && (
          <div className="border border-dashed border-[var(--line)] rounded-md p-8 text-center text-sm text-[var(--ink-3)]">
            {filter === "active" ? "No open snags. Raise one from site with a photo; the assignee fixes it with a photo; a manager verifies and closes it." : "Nothing in this view."}
          </div>
        )}
        {rows.map((s) => {
          const [label, chip] = STATUS[s.status] || [s.status, "chip-draft"];
          const first = s.photos?.[0];
          const late = s.due_date && s.status === "open" && s.due_date < new Date().toISOString().slice(0, 10);
          const canFix = s.status === "open" && (data.can_manage || mine.has(s.assignee_user_id));
          return (
            <div key={s.id} className="border border-[var(--line)] rounded-md p-3 flex gap-3 items-start" data-testid={`snag-${s.number}`}>
              <button type="button" className="shrink-0 w-16 h-16 bg-[var(--surface-2)] overflow-hidden" onClick={() => setViewing(s)} aria-label={`Open ${s.number}`}>
                {first ? <AuthImage src={`/snags/${s.id}/photos/${first.id}`} alt="" className="w-16 h-16 object-cover" />
                  : <Camera size={20} className="m-auto text-[var(--ink-3)]" />}
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-[var(--ink-3)]">{s.number}</span>
                  <span className="font-semibold">{s.title}</span>
                  <span className={`status-chip ${chip}`}>{label}</span>
                  {["urgent", "high"].includes(s.priority) && <span className="text-[10px] uppercase tracking-wider text-[var(--danger)]">{PRIORITY[s.priority]}</span>}
                </div>
                <div className="text-xs text-[var(--ink-2)] mt-0.5">
                  {s.area || "No area"} · {s.assignee_name || s.vendor_name || "Unassigned"}{s.vendor_name && s.assignee_name ? ` / ${s.vendor_name}` : ""}
                  {s.due_date && <span className={late ? "text-[var(--danger)]" : ""}> · due {formatDate(s.due_date)}</span>}
                  {s.reopen_count > 0 && <span> · reopened {s.reopen_count}×</span>}
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {canFix && <button type="button" className="btn-ghost text-xs" onClick={() => setFixing(s)} data-testid={`snag-fix-${s.number}`}><Camera size={13} /> Mark fixed</button>}
                {data.can_manage && s.status === "fixed" && <button type="button" className="btn-primary text-xs" onClick={() => setStatus(s, "close")} data-testid={`snag-close-${s.number}`}><CheckCircle size={13} /> Verify &amp; close</button>}
                <RowActions label={`snag ${s.number}`} testid={`snag-actions-${s.number}`} actions={[
                  { label: "Photos & history", icon: ClockCounterClockwise, onSelect: () => setViewing(s) },
                  { label: "Edit", icon: PencilSimple, hidden: ["closed", "wont_fix"].includes(s.status) || !data.can_raise, onSelect: () => setForm(s) },
                  { label: "Reopen", icon: ArrowCounterClockwise, hidden: !data.can_manage || s.status === "open", onSelect: () => setStatus(s, "reopen") },
                  { label: "Won't fix", icon: Prohibit, hidden: !data.can_manage || s.status !== "open", onSelect: () => setStatus(s, "wont_fix") },
                  { label: "Delete", icon: Trash, danger: true, divider: true, hidden: s.status !== "open" || s.reopen_count > 0 || !data.can_raise, onSelect: () => remove(s) },
                ]} />
              </div>
            </div>
          );
        })}
      </div>

      {form && <SnagForm projectId={projectId} snag={form.id ? form : null} people={people} vendors={vendors}
        onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
      {fixing && <FixForm snag={fixing} onClose={() => setFixing(null)} onSaved={() => { setFixing(null); load(); }} />}
      {viewing && (
        <Modal title={`${viewing.number} · ${viewing.title}`} onClose={() => setViewing(null)}>
          <div className="grid grid-cols-2 gap-2 mb-4" data-testid="snag-photos">
            {(viewing.photos || []).map((p) => (
              <figure key={p.id} className="space-y-1">
                <AuthImage src={`/snags/${viewing.id}/photos/${p.id}`} alt={p.kind} className="w-full aspect-square object-cover" />
                <figcaption className="text-[10px] text-[var(--ink-3)]">{p.kind === "fix" ? "Fix" : "Issue"} · {p.uploaded_by_name} · {formatDate(p.captured_at)}{p.caption ? ` · ${p.caption}` : ""}</figcaption>
              </figure>
            ))}
            {!viewing.photos?.length && <div className="col-span-2 text-sm text-[var(--ink-3)]">No photos.</div>}
          </div>
          {viewing.description && <p className="text-sm mb-3">{viewing.description}</p>}
          <ol className="space-y-1 text-xs">
            {(viewing.history || []).map((h, i) => (
              <li key={i}><span className="text-[var(--ink-3)]">{formatDate(h.at)}</span> · <b>{h.action}</b> by {h.by_name}{h.note ? ` — ${h.note}` : ""}</li>
            ))}
          </ol>
        </Modal>
      )}
    </div>
  );
}

function SnagForm({ projectId, snag, people, vendors, onClose, onSaved }) {
  const [f, setF] = useState({
    title: snag?.title || "", area: snag?.area || "", description: snag?.description || "", priority: snag?.priority || "normal",
    due_date: snag?.due_date || "", assignee_user_id: snag?.assignee_user_id || "", vendor_id: snag?.vendor_id || "",
  });
  const [photo, setPhoto] = useState(null);
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (snag) {
        await api.patch(`/snags/${snag.id}`, { ...f, due_date: f.due_date || null, assignee_user_id: f.assignee_user_id || null, vendor_id: f.vendor_id || null });
      } else {
        const body = new FormData();
        Object.entries(f).forEach(([k, v]) => v && body.append(k, v));
        if (photo) body.append("photo", await shrinkPhoto(photo));
        await api.post(`/projects/${projectId}/snags`, body);
      }
      toast.success(snag ? "Snag updated" : "Snag raised");
      onSaved();
    } catch (ex) { toast.error(ex?.response?.data?.detail || "Could not save the snag"); setBusy(false); }
  };
  return (
    <Modal title={snag ? `Edit ${snag.number}` : "Raise a snag"} onClose={onClose}>
      <form onSubmit={save} className="space-y-3" data-testid="snag-form">
        <input className="input-flat w-full" placeholder="What is wrong? e.g. Cracked tile at entrance" required minLength={2} maxLength={160}
          value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="snag-title" />
        <div className="grid grid-cols-2 gap-3">
          <input className="input-flat" placeholder="Area / room" value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })} />
          <select className="input-flat" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })} aria-label="Priority">
            {Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="input-flat" value={f.assignee_user_id} onChange={(e) => setF({ ...f, assignee_user_id: e.target.value })} aria-label="Assign to" data-testid="snag-assignee">
            <option value="">Assign to team member…</option>
            {people.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          <select className="input-flat" value={f.vendor_id} onChange={(e) => setF({ ...f, vendor_id: e.target.value })} aria-label="Vendor">
            <option value="">Vendor responsible (optional)</option>
            {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
          <label className="text-xs text-[var(--ink-2)] col-span-2 sm:col-span-1">Fix by
            <input type="date" className="input-flat w-full mt-1" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
          </label>
        </div>
        <textarea className="input-flat w-full" rows={2} placeholder="Details (optional)" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        {!snag && (
          <label className="block text-xs text-[var(--ink-2)]">Photo of the issue
            <input type="file" accept="image/*" capture="environment" className="input-flat w-full mt-1" onChange={(e) => setPhoto(e.target.files?.[0] || null)} data-testid="snag-photo" />
          </label>
        )}
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy} data-testid="snag-save">{busy ? "Saving…" : snag ? "Save" : "Raise snag"}</button></div>
      </form>
    </Modal>
  );
}

function FixForm({ snag, onClose, onSaved }) {
  const [photo, setPhoto] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    if (!photo) { toast.error("Add a photo of the fix"); return; }
    setBusy(true);
    try {
      const body = new FormData();
      body.append("photo", await shrinkPhoto(photo));
      if (note) body.append("note", note);
      await api.post(`/snags/${snag.id}/fixed`, body);
      toast.success(`${snag.number} marked fixed. A manager will verify it.`);
      onSaved();
    } catch (ex) { toast.error(ex?.response?.data?.detail || "Could not save"); setBusy(false); }
  };
  return (
    <Modal title={`${snag.number}: mark fixed`} onClose={onClose}>
      <form onSubmit={save} className="space-y-3" data-testid="snag-fix-form">
        <label className="block text-xs text-[var(--ink-2)]">Photo of the fix (required)
          <input type="file" accept="image/*" capture="environment" className="input-flat w-full mt-1" onChange={(e) => setPhoto(e.target.files?.[0] || null)} data-testid="snag-fix-photo" />
        </label>
        <input className="input-flat w-full" placeholder="What was done (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy} data-testid="snag-fix-save">{busy ? "Saving…" : "Mark fixed"}</button></div>
      </form>
    </Modal>
  );
}
