import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle, ArrowBendUpLeft, FileText, ArrowSquareOut, LockKey, Eye } from "@phosphor-icons/react";
import api, { API } from "../lib/api";
import { safeExternalUrl, safeFileUrl } from "../lib/url";
import { formatDate, formatINR, statusLabel } from "../lib/format";

const KIND = { drawing: "Drawing", variation: "Change to the work", document: "Document" };
const DECIDED = {
  approved: ["Approved", "chip-paid"],
  changes_requested: ["Changes asked", "chip-overdue"],
};

/** A link the portal may open: our own portal file route, or a plain http(s) URL. */
function approvalFileUrl(value) {
  if (typeof value === "string" && /^\/api\/portal\/[A-Za-z0-9_-]+\/approvals\/[A-Za-z0-9_-]+\/file$/.test(value)) {
    return new URL(value, window.location.origin).href;
  }
  return safeExternalUrl(value);
}

function initials(name) {
  return String(name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "·";
}

const money = (n) => formatINR(n || 0);
const signed = (n) => (n > 0 ? `+${money(n)}` : n < 0 ? `−${money(Math.abs(n))}` : "No change in cost");
const daysText = (d) => (!d ? null : d > 0 ? `+${d} day${d === 1 ? "" : "s"}` : `${d} day${d === -1 ? "" : "s"}`);

function Section({ label, title, children, testid }) {
  return (
    <section className="max-w-5xl mx-auto px-4 sm:px-8 pb-12" data-testid={testid}>
      <div className="overline mb-1">{label}</div>
      {title && <h2 className="font-display font-bold tracking-tight text-2xl mb-4">{title}</h2>}
      {children}
    </section>
  );
}

function ApprovalCard({ a, viewer, studio, onDecide }) {
  const [mode, setMode] = useState(null);     // null | "approve" | "changes"
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const file = approvalFileUrl(a.file_url);
  const submit = async (e) => {
    e.preventDefault();
    if (mode === "changes" && !comment.trim()) { setError("Say what should change."); return; }
    setBusy(true);
    setError("");
    try {
      await onDecide(a, mode, comment.trim());
    } catch (ex) {
      setError(ex?.response?.data?.detail || "Could not save your decision. Please try again.");
      setBusy(false);
    }
  };
  return (
    <article className="border border-[var(--line-strong)] bg-white p-4 sm:p-5" data-testid={`portal-approval-${a.id}`}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <div className="min-w-0 flex-1">
          <div className="overline">{KIND[a.kind] || "Request"}{a.rev ? ` · revision ${a.rev}` : ""}</div>
          <h3 className="font-display font-bold text-lg leading-snug [overflow-wrap:anywhere]">{a.title}</h3>
        </div>
        <div className="basis-full sm:basis-auto text-xs text-[var(--ink-3)]">Sent {formatDate(a.requested_at)}{a.requested_by_name ? ` by ${a.requested_by_name}` : ""}</div>
      </div>
      {a.kind === "variation" && (
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          <span className="font-mono font-semibold">{signed(Number(a.amount || 0))}</span>
          {daysText(a.days) && <span className="text-[var(--ink-2)]">· time {daysText(a.days)}</span>}
        </div>
      )}
      {a.description && <p className="mt-2 text-sm text-[var(--ink-2)] whitespace-pre-line [overflow-wrap:anywhere]">{a.description}</p>}
      {a.note && <p className="mt-2 text-sm border-l-2 border-[var(--accent)] pl-3 [overflow-wrap:anywhere]">{a.note}</p>}
      {file && (
        <a href={file} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--accent-strong)] hover:underline">
          <FileText size={16} /> {a.file_name || "Open the document"} <ArrowSquareOut size={13} />
        </a>
      )}
      {viewer.can_decide ? (
        mode ? (
          <form onSubmit={submit} className="mt-4 space-y-2" data-testid="portal-decision-form">
            <label className="block text-xs text-[var(--ink-2)]">
              {mode === "approve" ? "Comment for the studio (optional)" : "What should change?"}
              <textarea className="input-flat w-full mt-1 min-h-[84px]" value={comment} maxLength={1000}
                onChange={(e) => setComment(e.target.value)} autoFocus data-testid="portal-decision-comment" />
            </label>
            {mode === "approve" && (
              <p className="text-xs text-[var(--ink-3)]">You are approving this as {viewer.name}. {studio} will see your name, the date and time.</p>
            )}
            {error && <p className="text-sm text-[var(--danger)]" role="alert">{error}</p>}
            <div className="flex flex-wrap gap-2">
              <button className="btn-primary" disabled={busy} data-testid="portal-decision-confirm">
                {busy ? "Saving…" : mode === "approve" ? "Confirm approval" : "Send back to the studio"}
              </button>
              <button type="button" className="btn-ghost" onClick={() => { setMode(null); setError(""); }} disabled={busy}>Cancel</button>
            </div>
          </form>
        ) : (
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" className="btn-primary" onClick={() => setMode("approve")} data-testid="portal-approve">
              <CheckCircle size={16} /> Approve
            </button>
            <button type="button" className="btn-ghost" onClick={() => setMode("changes")} data-testid="portal-changes">
              <ArrowBendUpLeft size={16} /> Ask for changes
            </button>
          </div>
        )
      ) : (
        <p className="mt-4 text-xs text-[var(--ink-3)]">To approve or send this back, open the personal link {studio} sent you.</p>
      )}
    </article>
  );
}

export default function ClientPortal() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState(false);
  const [logoFailed, setLogoFailed] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const { data: d } = await api.get(`/portal/${token}`);
      setData(d);
      if (d.viewer?.name) setName((n) => n || d.viewer.name);
    } catch {
      setErr("This link is not valid any more. Ask the studio for a new one.");
    }
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const send = async (e) => {
    e.preventDefault();
    if (!msg.trim() || !name.trim()) return;
    await api.post(`/portal/${token}/message`, { from_name: name, message: msg });
    setSent(true);
    setMsg("");
  };

  const decide = async (a, mode, comment) => {
    await api.post(`/portal/${token}/approvals/${a.id}/decision`, { decision: mode === "approve" ? "approve" : "changes", comment: comment || null });
    setNotice(mode === "approve" ? `Thank you. "${a.title}" is approved.` : `Thanks. The studio has your comments on "${a.title}".`);
    await load();
  };

  if (err) return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-[var(--surface-2)]">
      <div className="text-center max-w-sm">
        <div className="overline">CLIENT PORTAL</div>
        <h1 className="font-display font-bold tracking-tight text-3xl mt-1">Link not available</h1>
        <p className="text-[var(--ink-2)] mt-2">{err}</p>
      </div>
    </div>
  );

  if (!data) return <div className="p-10 overline">LOADING…</div>;

  const { project, tasks_summary, files, invoices, account = {}, approvals = [], viewer = {}, brand = {} } = data;
  const studio = brand.name || "the studio";
  const stageIdx = project.all_stages.indexOf(project.stage);
  const pending = approvals.filter((a) => a.status === "pending");
  const decided = approvals.filter((a) => a.status !== "pending");
  const logo = !logoFailed && brand.logo_url;

  return (
    <div className="min-h-screen bg-white" data-testid="client-portal">
      <header className="border-b border-[var(--line)] bg-[var(--surface-2)]">
        <div className="max-w-5xl mx-auto px-4 sm:px-8 pt-6 pb-10 sm:pb-14">
          <div className="flex items-center justify-between gap-3 mb-8 sm:mb-10">
            <div className="flex items-center gap-3 min-w-0">
              {logo ? (
                <img src={logo} alt="" className="h-9 w-auto max-w-[140px] object-contain" onError={() => setLogoFailed(true)} />
              ) : (
                <div className="w-9 h-9 bg-[var(--accent)] flex items-center justify-center shrink-0">
                  <span className="text-white font-display font-bold text-xs">{initials(studio)}</span>
                </div>
              )}
              <span className="font-display font-bold tracking-tight truncate" data-testid="portal-studio">{studio}</span>
            </div>
            <div className="overline shrink-0">CLIENT PORTAL</div>
          </div>
          <div className="overline mb-2">{[project.project_type, project.client_name].filter(Boolean).join(" · ") || "Your project"}</div>
          <h1 className="font-display font-bold tracking-tight text-4xl sm:text-5xl leading-[0.95] max-w-3xl [overflow-wrap:anywhere]">{project.name}</h1>
          {project.description && <p className="mt-4 text-[var(--ink-2)] max-w-2xl sm:text-lg [overflow-wrap:anywhere]">{project.description}</p>}
          <div className="mt-6 inline-flex items-start gap-2 text-sm bg-white border border-[var(--line)] px-3 py-2 max-w-full" data-testid="portal-viewer">
            {viewer.kind === "personal" ? <LockKey size={16} className="mt-0.5 shrink-0" /> : <Eye size={16} className="mt-0.5 shrink-0" />}
            <span>
              {viewer.kind === "personal"
                ? <>Personal link for <b>{viewer.name}</b>. Please don't forward it: approvals made here are recorded in your name.</>
                : <>View-only link. To approve drawings and changes, use the personal link {studio} sent you.</>}
            </span>
          </div>
        </div>
      </header>

      {notice && (
        <div className="max-w-5xl mx-auto px-4 sm:px-8 pt-6">
          <div className="border border-[var(--success)] text-[var(--success)] bg-white px-4 py-3 text-sm" role="status">{notice}</div>
        </div>
      )}

      {pending.length > 0 && (
        <Section label="WAITING FOR YOU" title={`${pending.length} ${pending.length === 1 ? "item needs" : "items need"} your decision`} testid="portal-pending">
          <div className="space-y-3">
            {pending.map((a) => <ApprovalCard key={a.id} a={a} viewer={viewer} studio={studio} onDecide={decide} />)}
          </div>
        </Section>
      )}

      <section className="max-w-5xl mx-auto px-4 sm:px-8 py-10">
        <div className="flex items-end justify-between gap-4 mb-5">
          <div>
            <div className="overline mb-1">PROGRESS</div>
            <div className="font-display font-bold tracking-tight text-2xl">Stage: {project.stage}</div>
          </div>
          <div className="font-display font-bold tracking-tight text-4xl sm:text-5xl accent-blue">{project.progress}%</div>
        </div>
        <div className="h-1 bg-[var(--line-soft)]">
          <div className="h-1 bg-[var(--accent)]" style={{ width: `${project.progress}%` }} />
        </div>
        <ol className="mt-5 grid grid-cols-3 md:grid-cols-9 gap-1">
          {project.all_stages.map((s, i) => (
            <li key={s} aria-current={i === stageIdx ? "step" : undefined}
              className={`p-2 text-[10px] font-mono uppercase tracking-wider border ${
                i < stageIdx ? "bg-[var(--ink)] text-white border-[var(--ink)]"
                : i === stageIdx ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                : "bg-white text-[var(--ink-2)] border-[var(--line)]"}`}>
              <div className="opacity-70">STEP {i + 1}</div>
              <div className="font-semibold">{s}</div>
            </li>
          ))}
        </ol>
      </section>

      <section className="max-w-5xl mx-auto px-4 sm:px-8 pb-12 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card-flat">
          <div className="overline mb-2">TASKS DONE</div>
          <div className="font-display font-bold text-4xl">{tasks_summary.done}/{tasks_summary.total}</div>
          <div className="text-sm text-[var(--ink-2)] mt-2">{tasks_summary.in_progress} in progress</div>
        </div>
        <div className="card-flat">
          <div className="overline mb-2">FILES SHARED</div>
          <div className="font-display font-bold text-4xl">{files.length}</div>
          <div className="text-sm text-[var(--ink-2)] mt-2">{approvals.length ? `${decided.length} decision${decided.length === 1 ? "" : "s"} recorded` : "Listed below"}</div>
        </div>
        <div className="card-flat">
          <div className="overline mb-2">BALANCE DUE</div>
          <div className="font-display font-bold text-3xl font-mono" data-testid="portal-balance">{money(account.balance)}</div>
          <div className="text-sm text-[var(--ink-2)] mt-2">{money(account.paid)} paid of {money(account.invoiced)}</div>
        </div>
      </section>

      <Section label="DELIVERABLES" title="Files">
        <div className="space-y-2">
          {files.length === 0 && <p className="text-[var(--ink-2)] text-sm">No files shared yet.</p>}
          {files.map((f) => {
            const fileUrl = safeFileUrl(f.url, token);
            const body = (
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold [overflow-wrap:anywhere]">{f.name}</div>
                  <div className="text-xs text-[var(--ink-2)] mt-1">{f.stage || "—"} · {formatDate(f.created_at)}</div>
                </div>
                <div className="overline shrink-0">{fileUrl ? "OPEN →" : "UNAVAILABLE"}</div>
              </div>
            );
            return fileUrl ? (
              <a key={f.id} href={fileUrl} target="_blank" rel="noreferrer" className="block border border-[var(--line)] p-4 hover:border-[var(--ink)] transition">{body}</a>
            ) : <div key={f.id} className="block border border-[var(--line)] p-4">{body}</div>;
          })}
        </div>
      </Section>

      <Section label="FINANCIALS" title="Invoices and payments">
        <div className="space-y-2" data-testid="portal-invoices">
          {invoices.length === 0 && <p className="text-[var(--ink-2)] text-sm">No invoices yet.</p>}
          {invoices.map((i) => (
            <div key={i.id} className="border border-[var(--line)] p-4 flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="font-mono font-semibold">{i.number}</div>
                <div className="text-xs text-[var(--ink-2)]">
                  {statusLabel(i.doc_type || "invoice")}{i.issue_date ? ` · ${formatDate(i.issue_date)}` : ""} · Due {formatDate(i.due_date)}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <div className="text-right">
                  <div className="font-mono font-semibold">{money(i.total)}</div>
                  {i.paid != null && i.paid > 0 && i.balance > 0 && <div className="text-xs text-[var(--ink-2)]">{money(i.paid)} paid · {money(i.balance)} due</div>}
                </div>
                <span className={`status-chip chip-${i.status}`}>{statusLabel(i.status)}</span>
                <a href={`${API}/invoices/${i.id}/pdf?token=${token}`} target="_blank" rel="noreferrer" className="text-xs text-[var(--accent-strong)] underline">PDF</a>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {decided.length > 0 && (
        <Section label="RECORD" title="Decisions" testid="portal-decided">
          <ul className="divide-y divide-[var(--line-soft)] border border-[var(--line)]">
            {decided.map((a) => {
              const [label, cls] = DECIDED[a.status] || [a.status, "chip-draft"];
              return (
                <li key={a.id} className="p-4 flex flex-wrap items-start gap-x-3 gap-y-1">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold [overflow-wrap:anywhere]">{a.title}</div>
                    <div className="text-xs text-[var(--ink-2)]">
                      {KIND[a.kind]}{a.kind === "variation" ? ` · ${signed(Number(a.amount || 0))}` : ""} · {a.decided_by_name} · {formatDate(a.decided_at)}
                    </div>
                    {a.decision_comment && <div className="text-sm mt-1 [overflow-wrap:anywhere]">“{a.decision_comment}”</div>}
                  </div>
                  <span className={`status-chip ${cls}`}>{label}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <section className="max-w-5xl mx-auto px-4 sm:px-8 pb-20">
        <div className="border-t border-[var(--ink)] pt-8">
          <div className="overline mb-1">A QUICK WORD</div>
          <h2 className="font-display font-bold tracking-tight text-2xl sm:text-3xl mb-4">Leave a note for the team</h2>
          {sent ? (
            <p className="text-sm text-[var(--success)]" role="status">Thanks, we've received your message and will reply soon.</p>
          ) : (
            <form onSubmit={send} className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <label className="sr-only" htmlFor="portal-name">Your name</label>
              <input id="portal-name" required className="input-flat" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
              <label className="sr-only" htmlFor="portal-message">Message</label>
              <input id="portal-message" required className="input-flat md:col-span-2" placeholder="Message" value={msg} onChange={(e) => setMsg(e.target.value)} />
              <button className="btn-primary justify-center">Send</button>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
