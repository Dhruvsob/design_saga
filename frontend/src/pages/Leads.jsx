import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import { Plus, ArrowRight, Trash, DotsSixVertical, PencilSimple, Eye, X, Check, ClockCounterClockwise, NotePencil } from "@phosphor-icons/react";
import PageHero from "../components/PageHero";
import { formatDateTime, statusLabel } from "../lib/format";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";

const FALLBACK_STAGES = ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"];
const FALLBACK_SOURCES = ["Website", "Instagram", "Referral", "Marketplace", "Walk-in"];
const FALLBACK_TYPES = ["Residential", "Commercial"];

const STAGE_COLORS = {
  New: "#5C5C5C",
  Qualified: "#8B7F6A",
  Proposal: "#8B7F6A",
  Negotiation: "#B87500",
  Won: "#1D633E",
  Lost: "#B22B22",
};

export default function Leads() {
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const canCreate = hasPerm("leads.create");
  const canUpdate = hasPerm("leads.update");
  const canDelete = hasPerm("leads.delete");
  const canConvert = canUpdate && hasPerm("clients.create") && hasPerm("projects.create");
  const { values } = useMasterData();
  const STAGES = values("lead_stage", FALLBACK_STAGES);
  const SOURCES = values("lead_source", FALLBACK_SOURCES);
  const TYPES = values("project_type", FALLBACK_TYPES);
  const [leads, setLeads] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", source: "Website", project_type: "Residential", budget: "", location: "", stage: "New" });
  const [editing, setEditing] = useState(null); // lead being edited
  const [dragId, setDragId] = useState(null);
  const [dragOver, setDragOver] = useState(null);
  // Lead notes thread (editable + historically saved)
  const [notes, setNotes] = useState([]);
  const [noteText, setNoteText] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [editNoteId, setEditNoteId] = useState(null);
  const [editNoteText, setEditNoteText] = useState("");
  const [showHistory, setShowHistory] = useState({});

  const load = async () => {
    const { data } = await api.get("/leads");
    setLeads(data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    // Same person entered twice? Compare phone (last 10 digits) and email with existing leads.
    const digits = (v) => String(v || "").replace(/\D/g, "").slice(-10);
    const phone = digits(form.phone);
    const email = String(form.email || "").trim().toLowerCase();
    const dupe = leads.find((l) => (phone.length === 10 && digits(l.phone) === phone)
      || (email && String(l.email || "").trim().toLowerCase() === email));
    if (dupe && !await confirmAction(
      `${dupe.name} is already a lead with this ${phone && digits(dupe.phone) === phone ? "phone number" : "email"} (stage: ${dupe.stage || "New"}). Add another lead anyway?`)) return;
    await api.post("/leads", { ...form, budget: Number(form.budget || 0) });
    setShowForm(false);
    setForm({ name: "", email: "", phone: "", source: "Website", project_type: "Residential", budget: "", location: "", stage: "New" });
    load();
  };

  const drop = async (stage) => {
    if (!dragId) return;
    await api.patch(`/leads/${dragId}/stage`, { stage });
    setDragId(null);
    setDragOver(null);
    load();
  };

  const del = async (id) => {
    if (!await confirmAction("Remove this lead from the active pipeline? Its history will be preserved.")) return;
    try {
      await api.delete(`/leads/${id}`);
      toast.success("Lead removed from the active pipeline");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove lead");
    }
  };

  const startEdit = async (l) => {
    setEditing(l);
    setNotes([]);
    setNoteText("");
    setEditNoteId(null);
    setEditNoteText("");
    setShowHistory({});
    try {
      const { data } = await api.get(`/leads/${l.id}/notes`);
      setNotes(data || []);
    } catch {
      /* notes are non-blocking for editing */
    }
  };

  const loadNotes = async (id) => {
    const { data } = await api.get(`/leads/${id}/notes`);
    setNotes(data || []);
  };

  const addNote = async () => {
    const text = noteText.trim();
    if (!text || !editing) return;
    setSavingNote(true);
    try {
      await api.post(`/leads/${editing.id}/notes`, { text });
      setNoteText("");
      await loadNotes(editing.id);
      toast.success("Note added");
    } catch {
      toast.error("Could not add note");
    } finally {
      setSavingNote(false);
    }
  };

  const startNoteEdit = (n) => {
    setEditNoteId(n.id);
    setEditNoteText(n.text);
  };

  const saveNoteEdit = async () => {
    const text = editNoteText.trim();
    if (!text || !editing) return;
    try {
      await api.patch(`/leads/${editing.id}/notes/${editNoteId}`, { text });
      setEditNoteId(null);
      setEditNoteText("");
      await loadNotes(editing.id);
      toast.success("Note updated");
    } catch {
      toast.error("Could not update note");
    }
  };

  const deleteNote = async (noteId) => {
    if (!editing || !await confirmAction("Delete this note? It stays in history but is hidden from the thread.")) return;
    try {
      await api.delete(`/leads/${editing.id}/notes/${noteId}`);
      await loadNotes(editing.id);
    } catch {
      toast.error("Could not delete note");
    }
  };

  const saveEdit = async (e) => {
    e.preventDefault();
    const { id, ...rest } = editing;
    await api.patch(`/leads/${id}`, {
      name: rest.name, email: rest.email || undefined, phone: rest.phone || undefined,
      source: rest.source || undefined, project_type: rest.project_type || undefined,
      budget: Number(rest.budget || 0), location: rest.location || undefined,
      notes: rest.notes || undefined,
    });
    setEditing(null);
    load();
  };

  const convert = async (id) => {
    const { data } = await api.post(`/leads/${id}/convert`);
    toast.success("Lead converted — client & project created", {
      action: { label: "Open project", onClick: () => navigate(`/projects/${data.project_id}`) },
    });
    load();
  };

  return (
    <div className="space-y-8" data-testid="crm-page">
      <PageHero
        eyebrow="CRM / PIPELINE"
        title="Leads"
        kicker="Drag cards between columns to update stages. Convert qualified leads into projects with one click."
        count={leads.length}
      >
        {canCreate && <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-lead-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New lead"}
        </button>}
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-4 scale-in" data-testid="lead-form">
          <input className="input-flat" placeholder="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="lead-name" />
          <input className="input-flat" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input-flat" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <select aria-label="Source" className="input-flat" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
            {SOURCES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select aria-label="Project type" className="input-flat" value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
            {TYPES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <input className="input-flat" type="number" min="0" placeholder="Enter Budget (₹)" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          <button className="btn-primary" type="submit" data-testid="lead-submit">Save lead</button>
        </form>
      )}

      {/* Kanban */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 border-t border-l border-[var(--line)] stagger">
        {STAGES.map((stage, idx) => {
          const items = leads.filter((l) => l.stage === stage);
          const stageColor = STAGE_COLORS[stage];
          const isOver = dragOver === stage;
          return (
            <div
              key={stage}
              className={`fade-up border-r border-b border-[var(--line)] min-h-[500px] flex flex-col transition-all ${isOver ? "bg-[var(--hover)]" : ""}`}
              onDragOver={(e) => { if (canUpdate) { e.preventDefault(); setDragOver(stage); } }}
              onDragLeave={() => setDragOver(null)}
              onDrop={() => canUpdate && drop(stage)}
              data-testid={`col-${stage}`}
            >
              <div className="p-3 border-b border-[var(--line)] bg-[var(--surface-2)] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: stageColor }} />
                  <div className="overline">{stage}</div>
                </div>
                <div className="font-mono text-xs font-semibold bg-white px-1.5 border border-[var(--line)]">{items.length}</div>
              </div>
              <div className="p-3 flex-1 space-y-3">
                {items.map((l) => (
                  <div
                    key={l.id}
                    draggable={canUpdate}
                    onDragStart={() => setDragId(l.id)}
                    className="border border-[var(--line)] p-3 bg-white hover:border-[var(--ink)] hover:-translate-y-0.5 cursor-grab active:cursor-grabbing transition-all group"
                    data-testid={`lead-${l.id}`}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <div className="font-semibold text-sm leading-snug">{l.name}</div>
                      <DotsSixVertical size={14} className="text-[var(--line-strong)] mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <div className="text-xs text-[var(--ink-2)] mt-1 flex flex-wrap items-center gap-x-1.5">
                      <span>{l.project_type}</span>
                      {l.location && <><span aria-hidden="true">·</span><span>{l.location}</span></>}
                      {l.source && <><span aria-hidden="true">·</span><span className="text-[var(--ink-3)]">{statusLabel(l.source)}</span></>}
                    </div>
                    {Number(l.budget) > 0
                      ? <div className="font-mono text-sm mt-2 tabular-nums font-semibold">₹{Number(l.budget).toLocaleString("en-IN")}</div>
                      : <div className="text-[11px] mt-2 text-[var(--ink-3)]">Budget not set</div>}
                    <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-[var(--line-soft)]">
                      <button
                        onClick={() => startEdit(l)}
                        className="inline-flex items-center gap-1 text-xs text-[var(--ink-2)] hover:text-[var(--ink)]"
                        title="View & add notes"
                        data-testid={`lead-notes-btn-${l.id}`}
                      >
                        <NotePencil size={13} /> Notes
                        {(l.notes_log && l.notes_log.filter((n) => !n.deleted).length > 0) && (
                          <span className="font-mono text-[10px] bg-[var(--hover)] text-[var(--ink)] rounded-full px-1.5 leading-4">
                            {l.notes_log.filter((n) => !n.deleted).length}
                          </span>
                        )}
                      </button>
                      <div className="flex items-center gap-2 shrink-0 ml-auto">
                        {l.converted_project_id && (
                          <Link to={`/projects/${l.converted_project_id}`} className="text-[var(--accent-strong)] hover:underline text-xs flex items-center gap-1 font-semibold"
                             data-testid={`lead-project-${l.id}`}>
                            Project <ArrowRight size={12} weight="bold" />
                          </Link>
                        )}
                        {canConvert && l.stage !== "Won" && l.stage !== "Lost" && (
                          <button onClick={() => convert(l.id)} className="text-[var(--accent-strong)] hover:underline text-xs flex items-center gap-1 font-semibold shrink-0" title="Convert to project">
                            <ArrowRight size={12} weight="bold" /> Convert
                          </button>
                        )}
                        <RowActions label={l.name || "lead"} testid={`lead-actions-${l.id}`} actions={[
                          { label: canUpdate ? "Edit" : "View details", icon: canUpdate ? PencilSimple : Eye, onSelect: () => startEdit(l), testid: `lead-edit-${l.id}` },
                          { label: "Convert to project", icon: ArrowRight, onSelect: () => convert(l.id),
                            hidden: !(canConvert && l.stage !== "Won" && l.stage !== "Lost") },
                          { divider: true },
                          { label: "Delete", icon: Trash, danger: true, onSelect: () => del(l.id), hidden: !canDelete, testid: `lead-delete-${l.id}` },
                        ]} />
                      </div>
                    </div>
                  </div>
                ))}
                {items.length === 0 && (
                  <div className="text-center py-8 text-xs text-[var(--ink-3)]">
                    {canUpdate ? "Drop a lead here" : "No leads"}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Edit lead modal */}
      {editing && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setEditing(null); }}>
          <form onSubmit={saveEdit} className="bg-white border border-[var(--ink)] w-full max-w-2xl p-6 space-y-3 max-h-[90vh] overflow-y-auto" data-testid="lead-edit-modal">
            <div className="flex items-center justify-between">
              <div className="overline">{canUpdate ? "EDIT LEAD" : "LEAD DETAILS"}</div>
              <button type="button" onClick={() => setEditing(null)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <fieldset disabled={!canUpdate} className="space-y-3">
            <input required className="input-flat w-full" placeholder="Name" value={editing.name || ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} data-testid="edit-lead-name" />
            <div className="grid grid-cols-2 gap-3">
              <input className="input-flat" placeholder="Email" value={editing.email || ""} onChange={(e) => setEditing({ ...editing, email: e.target.value })} />
              <input className="input-flat" placeholder="Phone" value={editing.phone || ""} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} />
              <select aria-label="Source" className="input-flat" value={editing.source || ""} onChange={(e) => setEditing({ ...editing, source: e.target.value })}>
                {SOURCES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <select aria-label="Project type" className="input-flat" value={editing.project_type || ""} onChange={(e) => setEditing({ ...editing, project_type: e.target.value })}>
                {TYPES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <input className="input-flat" type="number" min="0" placeholder="Enter Budget (₹)" value={editing.budget ?? ""} onChange={(e) => setEditing({ ...editing, budget: e.target.value })} data-testid="edit-lead-budget" />
              <input className="input-flat" placeholder="Location" value={editing.location || ""} onChange={(e) => setEditing({ ...editing, location: e.target.value })} />
            </div>
            <textarea className="input-flat w-full" rows="2" placeholder="Notes" value={editing.notes || ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} />
            </fieldset>

            {/* Notes & history thread — every note is timestamped and kept in history */}
            <div className="border-t border-[var(--line)] pt-3 space-y-3" data-testid="lead-notes-section">
              <div className="overline flex items-center gap-2">
                <NotePencil size={13} /> Notes &amp; History
                <span className="font-mono text-[10px] bg-[var(--hover)] px-1.5 py-0.5 border border-[var(--line)]" data-testid="lead-notes-count">{notes.length}</span>
              </div>

              {canUpdate && <div className="flex items-start gap-2">
                <textarea
                  className="input-flat w-full"
                  rows="2"
                  placeholder="Add a note… (saved with your name & time)"
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  data-testid="lead-note-input"
                />
                <button
                  type="button"
                  onClick={addNote}
                  disabled={savingNote || !noteText.trim()}
                  className="btn-primary shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                  data-testid="lead-note-add-btn"
                >
                  <Plus size={13} /> Add
                </button>
              </div>}

              <div className="space-y-2 max-h-64 overflow-y-auto pr-1" data-testid="lead-notes-list">
                {notes.length === 0 && (
                  <div className="text-xs text-[var(--ink-3)] py-3 text-center border border-dashed border-[var(--line)]">
                    No notes yet — every note you add is timestamped and kept in history.
                  </div>
                )}
                {notes.map((n) => (
                  <div key={n.id} className="border border-[var(--line)] bg-[var(--surface-2)] p-3" data-testid={`lead-note-${n.id}`}>
                    {editNoteId === n.id ? (
                      <div className="space-y-2">
                        <textarea
                          className="input-flat w-full"
                          rows="2"
                          value={editNoteText}
                          onChange={(e) => setEditNoteText(e.target.value)}
                          data-testid={`lead-note-edit-input-${n.id}`}
                        />
                        <div className="flex items-center gap-2">
                          <button type="button" onClick={saveNoteEdit} disabled={!editNoteText.trim()} className="btn-primary text-xs disabled:opacity-40" data-testid={`lead-note-save-${n.id}`}>
                            <Check size={12} /> Save
                          </button>
                          <button type="button" onClick={() => { setEditNoteId(null); setEditNoteText(""); }} className="btn-ghost text-xs">
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="text-sm whitespace-pre-wrap leading-snug text-[var(--ink)]">{n.text}</div>
                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-[var(--line-soft)]">
                          <div className="text-[11px] text-[var(--ink-2)] min-w-0 truncate">
                            <span className="font-semibold">{n.author_name}</span>
                            <span className="mx-1">·</span>
                            <span className="font-mono">{formatDateTime(n.created_at)}</span>
                            {n.edited_at && <span className="ml-1 italic text-[var(--ink-3)]">(edited)</span>}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            {n.history && n.history.length > 0 && (
                              <button type="button" onClick={() => setShowHistory((s) => ({ ...s, [n.id]: !s[n.id] }))}
                                      className="text-[var(--ink-2)] hover:text-[var(--ink)] transition" title="View edit history"
                                      data-testid={`lead-note-history-toggle-${n.id}`}>
                                <ClockCounterClockwise size={13} />
                              </button>
                            )}
                            {canUpdate && <button type="button" onClick={() => startNoteEdit(n)} className="text-[var(--ink-2)] hover:text-[var(--ink)] transition" title="Edit note" data-testid={`lead-note-edit-${n.id}`}>
                              <PencilSimple size={12} />
                            </button>}
                            {canUpdate && <button type="button" onClick={() => deleteNote(n.id)} className="text-[var(--danger)] hover:scale-110 transition" title="Delete note" data-testid={`lead-note-delete-${n.id}`}>
                              <Trash size={12} />
                            </button>}
                          </div>
                        </div>
                        {showHistory[n.id] && n.history && n.history.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-dashed border-[var(--line)] space-y-1.5" data-testid={`lead-note-history-${n.id}`}>
                            <div className="overline text-[10px] text-[var(--ink-3)]">Previous versions</div>
                            {n.history.slice().reverse().map((h, i) => (
                              <div key={i} className="text-[11px] text-[var(--ink-2)]">
                                <div className="whitespace-pre-wrap line-through decoration-[var(--line-strong)]">{h.text}</div>
                                <div className="font-mono text-[10px] text-[var(--ink-3)]">{h.edited_by} · {formatDateTime(h.edited_at)}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {canUpdate && <button className="btn-primary w-full" data-testid="edit-lead-save">Save changes</button>}
          </form>
        </div>
      )}
    </div>
  );
}
