import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import {
  Plus, X, FileArrowUp, CheckCircle, XCircle, ChatText, PencilSimple, Archive, ArrowCounterClockwise,
  ClockCounterClockwise, FileXls, Trash, ArrowSquareOut, PaperPlaneTilt,
} from "@phosphor-icons/react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { formatDate } from "../lib/format";
import { askForm, confirmAction } from "../lib/confirm";
import { safeFileUrl } from "../lib/url";
import { downloadFile } from "../lib/download";
import RowActions from "./RowActions";

const STATUS = {
  issued: ["Issued", "chip-sent"], approved: ["Approved", "chip-paid"], rejected: ["Changes asked", "chip-overdue"],
  commented: ["Commented", "chip-draft"], superseded: ["Superseded", "chip-cancelled"],
};
const Chip = ({ status }) => {
  const [label, cls] = STATUS[status] || ["Not issued", "chip-draft"];
  return <span className={`status-chip ${cls}`}>{label}</span>;
};

function Modal({ title, children, onClose }) {
  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[291] w-full max-w-xl bg-white shadow-2xl max-h-[90vh] overflow-auto" role="dialog" aria-label={title}>
        <div className="flex items-start justify-between p-5 border-b border-[var(--line)]">
          <div className="font-display font-bold text-xl">{title}</div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>, document.body);
}

/** Drawing register: numbered drawings with revisions A, B, C... that point at project files. */
export default function ProjectDrawings({ projectId, projectName, files = [], onFilesChanged }) {
  const { hasPerm } = useAuth();
  const canEdit = hasPerm("files.create");
  const canDecide = hasPerm("projects.update");
  const [data, setData] = useState(null);
  const [showArchived, setShowArchived] = useState(false);
  const [discipline, setDiscipline] = useState("");
  const [issueFor, setIssueFor] = useState(null);
  const [historyFor, setHistoryFor] = useState(null);
  const [waiting, setWaiting] = useState({});    // "drawingId:rev" -> pending client request

  const load = () => {
    api.get(`/projects/${projectId}/approvals`)
      .then(({ data: a }) => setWaiting(Object.fromEntries((a.approvals || [])
        .filter((x) => x.kind === "drawing" && x.status === "pending").map((x) => [`${x.drawing_id}:${x.rev}`, x]))))
      .catch(() => setWaiting({}));
    return api.get(`/projects/${projectId}/drawings`, { params: { include_archived: showArchived } })
      .then(({ data: d }) => setData(d))
      .catch((e) => { setData({ drawings: [], counts: {}, purposes: {}, disciplines: [] }); toast.error(e?.response?.data?.detail || "Could not load drawings"); });
  };
  useEffect(() => { load(); }, [projectId, showArchived]);   // eslint-disable-line react-hooks/exhaustive-deps

  const askClient = async (d) => {
    const v = await askForm({
      title: `Ask the client to approve ${d.number} rev ${d.current.rev}`,
      body: "It appears in the client portal. Only people with a personal link (Client tab) can approve or send it back; their decision is written onto this revision.",
      fields: [{ name: "note", label: "Message to the client (optional)", multiline: true, placeholder: "Please check the wardrobe elevations" }],
      confirmLabel: "Send to client",
    });
    if (!v) return;
    try {
      await api.post(`/projects/${projectId}/approvals`, { kind: "drawing", drawing_id: d.id, note: v.note || null });
      toast.success(`${d.number} rev ${d.current.rev} sent to the client`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not send to the client"); }
  };

  const rows = useMemo(() => (data?.drawings || []).filter((d) => !discipline || d.discipline === discipline), [data, discipline]);
  const purposes = data?.purposes || {};

  const addDrawing = async (existing) => {
    const v = await askForm({
      title: existing ? `Edit ${existing.number}` : "Add drawing",
      body: existing?.revision_count ? "This drawing has been issued, so its number is fixed." : undefined,
      fields: [
        { name: "number", label: "Drawing number", required: true, defaultValue: existing?.number || "", placeholder: "A-101" },
        { name: "title", label: "Title", required: true, defaultValue: existing?.title || "", placeholder: "Ground floor plan" },
        { name: "discipline", label: "Discipline", defaultValue: existing?.discipline || "Architecture",
          options: (data?.disciplines || ["Architecture"]).map((x) => ({ value: x, label: x })) },
        { name: "scale", label: "Scale (optional)", defaultValue: existing?.scale || "", placeholder: "1:100" },
      ],
      confirmLabel: existing ? "Save" : "Add drawing",
    });
    if (!v) return;
    try {
      if (existing) await api.patch(`/drawings/${existing.id}`, v);
      else await api.post(`/projects/${projectId}/drawings`, v);
      toast.success(existing ? "Drawing updated" : `Drawing ${v.number.toUpperCase()} added`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save the drawing"); }
  };

  const decide = async (d, decision) => {
    const cur = d.current;
    const v = await askForm({
      title: `${decision === "approved" ? "Approve" : decision === "rejected" ? "Ask for changes on" : "Comment on"} ${d.number} rev ${cur.rev}`,
      fields: [{ name: "comment", label: decision === "rejected" ? "What needs to change" : "Comment (optional)", required: decision === "rejected" }],
      confirmLabel: decision === "approved" ? "Approve" : decision === "rejected" ? "Ask for changes" : "Save comment",
    });
    if (!v) return;
    try {
      await api.post(`/drawings/${d.id}/revisions/${cur.rev}/decision`, { decision, comment: v.comment || null });
      toast.success(`Rev ${cur.rev} ${decision === "approved" ? "approved" : decision === "rejected" ? "sent back for changes" : "commented"}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save"); }
  };

  const archive = async (d, archived) => {
    if (archived && !await confirmAction(`Archive ${d.number}? It leaves the register but its revisions stay on record.`)) return;
    try { await api.patch(`/drawings/${d.id}`, { archived }); toast.success(archived ? "Archived" : "Restored"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not update"); }
  };
  const remove = async (d) => {
    if (!await confirmAction(`Delete ${d.number}? It has never been issued.`)) return;
    try { await api.delete(`/drawings/${d.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not delete"); }
  };
  const exportRegister = () => downloadFile(`/projects/${projectId}/drawings/register.xlsx`, `drawing-register-${projectName || projectId}.xlsx`)
    .catch(() => toast.error("Could not download the register"));

  const c = data?.counts || {};
  return (
    <div className="space-y-4" data-testid="project-drawings">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-sm text-[var(--ink-2)] mr-auto" data-testid="drawings-counts">
          {c.total || 0} drawings · {c.approved || 0} approved · {c.awaiting || 0} awaiting decision · {c.construction || 0} issued for construction
        </div>
        <select className="input-flat text-xs" value={discipline} onChange={(e) => setDiscipline(e.target.value)} aria-label="Discipline">
          <option value="">All disciplines</option>
          {(data?.disciplines || []).map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <label className="flex items-center gap-1 text-xs text-[var(--ink-2)]">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Archived
        </label>
        <button type="button" className="btn-ghost text-xs" onClick={exportRegister}><FileXls size={14} /> Excel</button>
        {canEdit && <button type="button" className="btn-primary" onClick={() => addDrawing(null)} data-testid="drawing-add"><Plus size={14} /> Add drawing</button>}
      </div>

      <div className="border border-[var(--line)] overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]" data-testid="drawings-table">
          <thead className="bg-[var(--surface-2)]"><tr className="overline text-left">
            <th className="p-3">Number</th><th className="p-3">Title</th><th className="p-3">Rev</th>
            <th className="p-3">Issued for</th><th className="p-3">Status</th><th className="p-3">Issued</th><th className="p-3" />
          </tr></thead>
          <tbody>
            {data === null && <tr><td colSpan={7} className="p-6 overline">LOADING…</td></tr>}
            {data && rows.length === 0 && (
              <tr><td colSpan={7} className="p-10 text-center text-[var(--ink-3)]">
                No drawings yet. Add a drawing number (e.g. A-101 Ground floor plan), then issue revision A with its PDF.
              </td></tr>
            )}
            {rows.map((d) => {
              const cur = d.current;
              const url = cur && safeFileUrl(cur.file_url);
              return (
                <tr key={d.id} className={`border-t border-[var(--line-soft)] ${d.archived ? "opacity-60" : ""}`} data-testid={`drawing-row-${d.number}`}>
                  <td className="p-3 font-mono font-semibold whitespace-nowrap">{d.number}</td>
                  <td className="p-3"><div className="font-semibold">{d.title}</div>
                    <div className="text-xs text-[var(--ink-3)]">{d.discipline}{d.scale ? ` · ${d.scale}` : ""}</div></td>
                  <td className="p-3 font-mono">{cur ? cur.rev : "—"}{d.revision_count > 1 && <span className="text-[10px] text-[var(--ink-3)]"> of {d.revision_count}</span>}</td>
                  <td className="p-3 text-xs">{cur ? purposes[cur.purpose] || cur.purpose : "—"}{cur?.issued_to && <div className="text-[var(--ink-3)]">to {cur.issued_to}</div>}</td>
                  <td className="p-3"><Chip status={cur?.status} />
                    {cur && waiting[`${d.id}:${cur.rev}`] && <div className="text-[10px] font-semibold text-[var(--accent-strong)] mt-1" data-testid={`drawing-waiting-${d.number}`}>Waiting for client</div>}
                    {cur?.decided_via === "client_portal" && <div className="text-[10px] text-[var(--ink-2)] mt-1">by {cur.decided_by_name}</div>}
                    {cur?.comment && <div className="text-[10px] text-[var(--ink-3)] mt-1 max-w-[220px] truncate" title={cur.comment}>{cur.comment}</div>}</td>
                  <td className="p-3 text-xs whitespace-nowrap">{cur ? formatDate(cur.issued_on) : "—"}</td>
                  <td className="p-3 text-right whitespace-nowrap">
                    {canEdit && !d.archived && (
                      <button type="button" className="btn-ghost text-xs mr-1" onClick={() => setIssueFor(d)} data-testid={`drawing-issue-${d.number}`}>
                        <FileArrowUp size={13} /> {cur ? `Issue rev ${nextRev(cur.rev)}` : "Issue rev A"}
                      </button>
                    )}
                    <RowActions label={`drawing ${d.number}`} testid={`drawing-actions-${d.number}`} actions={[
                      { label: "Open current PDF", icon: ArrowSquareOut, hidden: !url, onSelect: () => window.open(url, "_blank", "noopener") },
                      { label: "Ask client to approve", icon: PaperPlaneTilt, hidden: !(canDecide && cur?.status === "issued" && !d.archived && !waiting[`${d.id}:${cur.rev}`]), onSelect: () => askClient(d), testid: `drawing-ask-client-${d.number}` },
                      { label: "Approve", icon: CheckCircle, hidden: !(canDecide && cur?.status === "issued"), onSelect: () => decide(d, "approved"), testid: `drawing-approve-${d.number}` },
                      { label: "Ask for changes", icon: XCircle, hidden: !(canDecide && cur?.status === "issued"), onSelect: () => decide(d, "rejected") },
                      { label: "Add comment", icon: ChatText, hidden: !(canDecide && cur?.status === "issued"), onSelect: () => decide(d, "commented") },
                      { label: "Revision history", icon: ClockCounterClockwise, hidden: !d.revision_count, onSelect: () => setHistoryFor(d) },
                      { label: "Edit details", icon: PencilSimple, hidden: !canEdit, onSelect: () => addDrawing(d) },
                      { label: d.archived ? "Restore" : "Archive", icon: d.archived ? ArrowCounterClockwise : Archive, divider: true,
                        hidden: !canEdit || !d.revision_count, onSelect: () => archive(d, !d.archived) },
                      { label: "Delete", icon: Trash, danger: true, divider: true, hidden: !canEdit || d.revision_count > 0, onSelect: () => remove(d) },
                    ]} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {issueFor && <IssueRevision drawing={issueFor} projectId={projectId} files={files} purposes={purposes}
        onClose={() => setIssueFor(null)} onDone={() => { setIssueFor(null); load(); onFilesChanged && onFilesChanged(); }} />}
      {historyFor && (
        <Modal title={`${historyFor.number} · revision history`} onClose={() => setHistoryFor(null)}>
          <ol className="space-y-3" data-testid="drawing-history">
            {[...historyFor.revisions].reverse().map((r) => (
              <li key={r.rev} className="border-l-2 border-[var(--line)] pl-3">
                <div className="flex items-center gap-2"><span className="font-mono font-semibold">Rev {r.rev}</span><Chip status={r.status} />
                  <span className="text-xs text-[var(--ink-3)] ml-auto">{formatDate(r.issued_on)}</span></div>
                <div className="text-xs text-[var(--ink-2)]">{purposes[r.purpose] || r.purpose}{r.issued_to ? ` · to ${r.issued_to}` : ""} · {r.created_by_name}</div>
                {r.note && <div className="text-xs mt-1">{r.note}</div>}
                {r.decided_by_name && <div className="text-xs mt-1 text-[var(--ink-2)]">{STATUS[r.status]?.[0]} by {r.decided_by_name}{r.decided_via === "client_portal" ? " in the client portal" : ""}{r.decided_at ? ` on ${formatDate(r.decided_at)}` : ""}{r.comment ? `: ${r.comment}` : ""}</div>}
                {safeFileUrl(r.file_url) && <a className="text-xs text-[var(--accent-strong)] hover:underline" href={safeFileUrl(r.file_url)} target="_blank" rel="noreferrer">{r.file_name || "Open file"}</a>}
              </li>
            ))}
          </ol>
        </Modal>
      )}
    </div>
  );
}

function nextRev(rev) {
  if (!rev) return "A";
  let n = 0;
  for (const ch of rev.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
  n += 1;
  let out = "";
  while (n) { const r = (n - 1) % 26; out = String.fromCharCode(65 + r) + out; n = Math.floor((n - 1) / 26); }
  return out;
}

function IssueRevision({ drawing, projectId, files, purposes, onClose, onDone }) {
  const rev = nextRev(drawing.current?.rev);
  const [mode, setMode] = useState("upload");
  const [file, setFile] = useState(null);
  const [fileId, setFileId] = useState("");
  const [form, setForm] = useState({ purpose: drawing.current?.purpose === "construction" ? "construction" : "review", issued_to: "", note: "", issued_on: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let id = fileId;
      if (mode === "upload") {
        if (!file) { toast.error("Choose the drawing file"); setBusy(false); return; }
        const body = new FormData();
        body.append("project_id", projectId);
        body.append("name", `${drawing.number} rev ${rev} - ${drawing.title}`);
        body.append("stage", `Drawing ${drawing.number}`);
        body.append("client_visible", "false");
        body.append("upload", file);
        id = (await api.post("/files/upload", body)).data.id;
      }
      if (!id) { toast.error("Choose a file"); setBusy(false); return; }
      await api.post(`/drawings/${drawing.id}/revisions`, { file_id: id, ...form, issued_on: form.issued_on || undefined });
      toast.success(`${drawing.number} rev ${rev} issued`);
      onDone();
    } catch (ex) { toast.error(ex?.response?.data?.detail || "Could not issue the revision"); setBusy(false); }
  };
  return (
    <Modal title={`Issue ${drawing.number} rev ${rev}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" data-testid="drawing-issue-form">
        {drawing.current && <p className="text-xs text-[var(--ink-2)]">Rev {drawing.current.rev} will be marked superseded. Its file and history stay.</p>}
        <div className="flex gap-3 text-sm">
          <label className="flex items-center gap-1"><input type="radio" checked={mode === "upload"} onChange={() => setMode("upload")} /> Upload file</label>
          <label className="flex items-center gap-1"><input type="radio" checked={mode === "existing"} onChange={() => setMode("existing")} disabled={!files.length} /> Use a project file</label>
        </div>
        {mode === "upload" ? (
          <input type="file" className="input-flat w-full" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="drawing-file" />
        ) : (
          <select className="input-flat w-full" value={fileId} onChange={(e) => setFileId(e.target.value)} aria-label="Project file">
            <option value="">Choose a file…</option>
            {files.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
        <label className="block text-xs text-[var(--ink-2)]">Issued for
          <select className="input-flat w-full mt-1" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} data-testid="drawing-purpose">
            {Object.entries(purposes).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-xs text-[var(--ink-2)]">Issued to
            <input className="input-flat w-full mt-1" placeholder="Client, contractor, consultant" value={form.issued_to} onChange={(e) => setForm({ ...form, issued_to: e.target.value })} />
          </label>
          <label className="block text-xs text-[var(--ink-2)]">Issue date
            <input type="date" className="input-flat w-full mt-1" value={form.issued_on} onChange={(e) => setForm({ ...form, issued_on: e.target.value })} />
          </label>
        </div>
        <label className="block text-xs text-[var(--ink-2)]">What changed (optional)
          <input className="input-flat w-full mt-1" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="e.g. Kitchen layout revised as per client" />
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy} data-testid="drawing-issue-save">{busy ? "Issuing…" : `Issue rev ${rev}`}</button>
        </div>
      </form>
    </Modal>
  );
}
