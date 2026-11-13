import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import {
  Plus, X, Copy, ArrowsClockwise, Trash, UserCircle, ArrowCounterClockwise, FileText,
} from "@phosphor-icons/react";
import api from "../lib/api";
import { askForm, confirmAction } from "../lib/confirm";
import { formatDate, formatINR } from "../lib/format";
import { safeFileUrl } from "../lib/url";
import RowActions from "./RowActions";

const KIND = { drawing: "Drawing", variation: "Variation", document: "Document" };
export const APPROVAL_STATUS = {
  pending: ["Waiting for client", "chip-sent"],
  approved: ["Approved by client", "chip-paid"],
  changes_requested: ["Changes asked", "chip-overdue"],
  withdrawn: ["Withdrawn", "chip-cancelled"],
  superseded: ["Replaced", "chip-cancelled"],
};
const signed = (n) => (n > 0 ? `+${formatINR(n)}` : n < 0 ? `−${formatINR(Math.abs(n))}` : formatINR(0));

function LinkModal({ person, onClose }) {
  const url = `${window.location.origin}/portal/${person.token}`;
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); toast.success("Link copied"); }
    catch { toast.error("Copy failed. Select the link and copy it."); }
  };
  return createPortal(
    <div className="fixed inset-0 z-[290] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[291] w-full max-w-lg bg-white shadow-2xl" role="dialog" aria-label="Personal client link" data-testid="portal-link-modal">
        <div className="flex items-start justify-between p-5 border-b border-[var(--line)]">
          <div>
            <div className="overline">PERSONAL LINK</div>
            <div className="font-display font-bold text-xl">{person.name}</div>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-sm text-[var(--ink-2)]">
            Send this link to {person.name} by WhatsApp or email. They can view the project and approve or send back what you ask them to.
            For safety it is shown only now. If it gets lost, make a new link (the old one stops working).
          </p>
          <input readOnly className="input-flat w-full font-mono text-xs" value={url} onFocus={(e) => e.target.select()} aria-label="Personal client link" data-testid="portal-link-value" />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-ghost" onClick={onClose}>Done</button>
            <button type="button" className="btn-primary" onClick={copy} data-testid="portal-link-copy"><Copy size={14} /> Copy link</button>
          </div>
        </div>
      </div>
    </div>, document.body);
}

/** Client tab: who has a personal portal link, and what the client was asked to approve. */
export default function ProjectApprovals({ projectId, files = [], onCount }) {
  const [data, setData] = useState(null);
  const [link, setLink] = useState(null);

  const load = () => api.get(`/projects/${projectId}/approvals`)
    .then(({ data: d }) => { setData(d); onCount && onCount(d.summary?.pending || 0); })
    .catch((e) => { setData({ approvals: [], people: [], summary: {} }); toast.error(e?.response?.data?.detail || "Could not load client approvals"); });
  useEffect(() => { load(); }, [projectId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const canManage = Boolean(data?.can_manage);
  const s = data?.summary || {};

  const addPerson = async () => {
    const v = await askForm({
      title: "Give a client a personal link",
      body: "Each person gets their own link, so every approval shows who made it.",
      fields: [
        { name: "name", label: "Name", required: true, placeholder: "Mrs Anita Mehta" },
        { name: "email", label: "Email (optional)", type: "email" },
        { name: "phone", label: "Phone (optional)", type: "tel" },
      ],
      confirmLabel: "Create link",
    });
    if (!v) return;
    try {
      const { data: person } = await api.post(`/projects/${projectId}/portal-people`, {
        name: v.name, email: v.email || null, phone: v.phone || null });
      setLink(person);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not create the link"); }
  };

  const renew = async (person) => {
    if (!await confirmAction(`Make a new link for ${person.name}? Their current link stops working immediately.`)) return;
    try { const { data: p } = await api.post(`/portal-people/${person.id}/new-link`); setLink(p); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not make a new link"); }
  };

  const revoke = async (person) => {
    if (!await confirmAction(`Remove ${person.name}'s link? It stops working immediately. Their past approvals stay on record.`)) return;
    try { await api.delete(`/portal-people/${person.id}`); toast.success("Link removed"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not remove the link"); }
  };

  const newRequest = async (kind) => {
    const fileOptions = [{ value: "", label: "No file" }, ...files.map((f) => ({ value: f.id, label: f.name }))];
    const fields = [
      { name: "title", label: kind === "variation" ? "What is changing" : "Title", required: true,
        placeholder: kind === "variation" ? "False ceiling in bedroom 2" : "Kitchen material board" },
      { name: "description", label: "Details (optional)", multiline: true },
    ];
    if (kind === "variation") {
      fields.push({ name: "amount", label: "Cost change (₹)", required: true, type: "number", hint: "Use a minus sign for a saving, 0 if the price doesn't change." });
      fields.push({ name: "days", label: "Time change in days (optional)", type: "number" });
    }
    fields.push({ name: "file_id", label: "Attach a project file", options: fileOptions });
    fields.push({ name: "note", label: "Message to the client (optional)", multiline: true });
    const v = await askForm({ title: kind === "variation" ? "Ask the client to approve a variation" : "Ask the client to approve a document", fields, confirmLabel: "Send to client" });
    if (!v) return;
    const amount = v.amount === "" || v.amount == null ? null : Number(v.amount);
    const days = v.days === "" || v.days == null ? null : Math.round(Number(v.days));
    if ((amount !== null && !Number.isFinite(amount)) || (days !== null && !Number.isFinite(days))) {
      toast.error("Enter numbers for cost and time");
      return;
    }
    try {
      await api.post(`/projects/${projectId}/approvals`, {
        kind, title: v.title, description: v.description || null, note: v.note || null,
        file_id: v.file_id || null, amount, days });
      toast.success(data?.people?.length ? "Sent. It's waiting in the client's portal." : "Saved. Give the client a personal link so they can approve it.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not send the request"); }
  };

  const withdraw = async (a) => {
    if (!await confirmAction(`Withdraw "${a.title}"? The client will no longer see it.`)) return;
    try { await api.post(`/approvals/${a.id}/withdraw`, {}); toast.success("Withdrawn"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Could not withdraw"); }
  };

  if (!data) return <div className="overline p-4">LOADING…</div>;
  const people = data.people || [];
  const rows = data.approvals || [];

  return (
    <div className="space-y-6" data-testid="project-approvals">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="approvals-summary">
        <div className="card-flat"><div className="overline">WAITING</div><div className="font-display font-bold text-3xl">{s.pending || 0}</div></div>
        <div className="card-flat"><div className="overline">APPROVED</div><div className="font-display font-bold text-3xl">{s.approved || 0}</div></div>
        <div className="card-flat"><div className="overline">CHANGES ASKED</div><div className="font-display font-bold text-3xl">{s.changes_requested || 0}</div></div>
        <div className="card-flat"><div className="overline">APPROVED VARIATIONS</div>
          <div className="font-display font-bold text-2xl font-mono">{signed(s.variations_approved_amount || 0)}</div>
          {s.variations_approved_days ? <div className="text-xs text-[var(--ink-2)]">{s.variations_approved_days > 0 ? "+" : ""}{s.variations_approved_days} days</div> : null}
        </div>
      </div>

      <section className="border border-[var(--line)]" data-testid="portal-people">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-[var(--line)]">
          <div className="mr-auto">
            <div className="font-display font-bold text-lg">Client links</div>
            <div className="text-xs text-[var(--ink-2)]">People with a personal link can approve. The shared project link is view-only.</div>
          </div>
          {canManage && <button type="button" className="btn-primary" onClick={addPerson} data-testid="portal-person-add"><Plus size={14} /> Add person</button>}
        </div>
        {people.length === 0 ? (
          <p className="p-4 text-sm text-[var(--ink-3)]">No personal links yet. Add the client (and anyone else who signs off, such as a spouse or the owner's architect).</p>
        ) : (
          <ul className="divide-y divide-[var(--line-soft)]">
            {people.map((p) => (
              <li key={p.id} className="p-4 flex flex-wrap items-center gap-3" data-testid={`portal-person-${p.id}`}>
                <UserCircle size={28} className="text-[var(--ink-3)] shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{p.name}</div>
                  <div className="text-xs text-[var(--ink-2)] [overflow-wrap:anywhere]">
                    {[p.email, p.phone].filter(Boolean).join(" · ") || "No contact details"} · {p.last_used_at ? `last opened ${formatDate(p.last_used_at)}` : "not opened yet"}
                  </div>
                </div>
                {canManage && (
                  <RowActions label={`link for ${p.name}`} actions={[
                    { label: "Make a new link", icon: ArrowsClockwise, onSelect: () => renew(p) },
                    { label: "Remove link", icon: Trash, danger: true, divider: true, onSelect: () => revoke(p) },
                  ]} />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="border border-[var(--line)]" data-testid="approval-requests">
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-[var(--line)]">
          <div className="mr-auto">
            <div className="font-display font-bold text-lg">Approval requests</div>
            <div className="text-xs text-[var(--ink-2)]">Send drawings from Drawings (⋯ → Ask client to approve).</div>
          </div>
          {canManage && (
            <>
              <button type="button" className="btn-ghost" onClick={() => newRequest("document")} data-testid="approval-new-document"><FileText size={14} /> Document</button>
              <button type="button" className="btn-primary" onClick={() => newRequest("variation")} data-testid="approval-new-variation"><Plus size={14} /> Variation</button>
            </>
          )}
        </div>
        {rows.length === 0 ? (
          <p className="p-4 text-sm text-[var(--ink-3)]">Nothing sent to the client yet.</p>
        ) : (
          <ul className="divide-y divide-[var(--line-soft)]">
            {rows.map((a) => {
              const [label, cls] = APPROVAL_STATUS[a.status] || [a.status, "chip-draft"];
              const file = a.file_id ? safeFileUrl(`/api/files/${a.file_id}/content`) : null;
              return (
                <li key={a.id} className="p-4 flex flex-wrap items-start gap-3" data-testid={`approval-row-${a.id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="overline">{KIND[a.kind]}</span>
                      <span className={`status-chip ${cls}`}>{label}</span>
                    </div>
                    <div className="font-semibold mt-1 [overflow-wrap:anywhere]">{a.title}</div>
                    <div className="text-xs text-[var(--ink-2)]">
                      {a.kind === "variation" && <span className="font-mono">{signed(Number(a.amount || 0))}{a.days ? ` · ${a.days > 0 ? "+" : ""}${a.days} days` : ""} · </span>}
                      Sent {formatDate(a.requested_at)} by {a.requested_by_name || "—"}
                      {file && <> · <a className="text-[var(--accent-strong)] hover:underline" href={file} target="_blank" rel="noreferrer">{a.file_name || "file"}</a></>}
                    </div>
                    {a.decided_at && (
                      <div className="text-sm mt-1">
                        <b>{a.decided_by_name}</b> {a.status === "approved" ? "approved" : "asked for changes"} on {formatDate(a.decided_at)}
                        {a.decision_comment && <span className="text-[var(--ink-2)]">: “{a.decision_comment}”</span>}
                      </div>
                    )}
                    {a.closed_reason && !a.decided_at && <div className="text-xs text-[var(--ink-3)] mt-1">{a.closed_reason}</div>}
                  </div>
                  {canManage && a.status === "pending" && (
                    <button type="button" className="btn-ghost text-xs" onClick={() => withdraw(a)} data-testid={`approval-withdraw-${a.id}`}>
                      <ArrowCounterClockwise size={13} /> Withdraw
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {link && <LinkModal person={link} onClose={() => setLink(null)} />}
    </div>
  );
}
