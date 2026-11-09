import { useEffect, useRef, useState } from "react";
import api, { API } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import { safeExternalUrl } from "../lib/url";
import { formatDate, formatINR, statusLabel } from "../lib/format";
import {
  Receipt, Plus, Warning, Check, X, ThumbsUp, ThumbsDown, Wallet,
  PencilSimple, Trash, Camera, Paperclip, LinkSimple, FilePdf,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import { SkeletonRows, EmptyRow } from "../components/TableState";

const fmtMoney = (n) => formatINR(n);
function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}

const STATUS_TONE = {
  draft: "bg-[var(--line-soft)] text-[var(--ink-2)]",
  pending_l1: "bg-[var(--warning-soft)] text-[var(--warning)]",
  pending_l2: "bg-[var(--warning-soft)] text-[var(--warning)]",
  receipt_required: "bg-[var(--warning-soft)] text-[var(--warning)]",
  approved: "bg-[var(--hover)] text-[#5F5A4B]",
  rejected: "bg-[var(--danger-soft)] text-[var(--danger)]",
  reimbursed: "bg-[var(--success-soft)] text-[var(--success)]",
  cancelled: "bg-[var(--line-soft)] text-[var(--ink-2)]",
};

export default function Expenses() {
  const { user, hasPerm } = useAuth();
  const [tab, setTab] = useState("all");
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editExpense, setEditExpense] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const isAdmin = hasPerm("*.*");
  const isFinance = hasPerm("finance.create");
  const canCreate = hasPerm("expenses.create");
  const canManage = hasPerm("expenses.update");
  const canDeletePosted = hasPerm("finance.delete");

  const load = async () => {
    setLoading(true);
    try {
      const params = tab === "mine" ? { mine: true } : (tab === "approvals" ? { status: "pending_l1,pending_l2" } : {});
      const [e, s, a] = await Promise.all([
        api.get("/expenses", { params }),
        api.get("/expenses/summary/dashboard"),
        isFinance ? api.get("/accounts?type=asset") : Promise.resolve({ data: [] }),
      ]);
      let rows = e.data;
      if (tab === "approvals") {
        // filter to expenses awaiting my role's decision (or any if admin)
        rows = rows.filter((x) => ["pending_l1", "pending_l2"].includes(x.status) &&
          (isAdmin || x.pending_approver_role === user?.role));
      }
      setExpenses(rows); setSummary(s.data);
      setAccounts(a.data.filter((x) => x.is_bank || ["Cash", "Bank - Primary", "Petty Cash"].includes(x.name)));
    } catch (ex) { setErr(fmtErr(ex?.response?.data?.detail)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tab]);

  if (loading) return <div className="skeleton h-96"></div>;

  return (
    <div className="space-y-6" data-testid="expenses-page">
      <PageHero eyebrow="FINANCE / STAFF EXPENSE CLAIMS"
        title="Expense claims"
        kicker="For staff reimbursement claims that need approval. For direct company expenses (rent, tea, salary etc.), use Accounting → Expense."
        count={expenses.length}>
        {canCreate && <button onClick={() => setShowCreate(true)} className="btn-primary" data-testid="new-expense-btn">
          <Plus size={13}/> New claim
        </button>}
      </PageHero>

      {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]"><Warning size={13} className="inline mr-1"/>{err}</div>}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI label="PENDING APPROVAL" value={summary.pending} tone="#7A4E1A" />
          <KPI label="APPROVED · TO PAY" value={summary.approved} tone="#8B7F6A" />
          <KPI label="REIMBURSED · MONTH" value={summary.reimbursed_this_month} tone="#1D633E" />
          <KPI label="MY PENDING" value={summary.my_pending} tone="#7A4E1A" />
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[var(--line)]">
        {[["all","All"],["mine","My Expenses"],["approvals","Awaiting My Approval"]].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm border-b-2 ${tab === k ? "border-[var(--accent)] text-[var(--accent-strong)] font-semibold" : "border-transparent text-[var(--ink-2)]"}`}
            data-testid={`tab-${k}`}>
            {l}
          </button>
        ))}
      </div>

      <div className="card-flat p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px]" data-testid="expenses-table">
            <thead className="bg-[var(--surface-2)] border-y border-[var(--line)]"><tr className="text-left">
              <Th>Title</Th><Th>Claimant</Th><Th>Total</Th><Th>Status</Th><Th>Next Approver</Th><Th>Date</Th>
            </tr></thead>
            <tbody>
              {expenses.map((e) => (
                <tr key={e.id} onClick={() => setDetail(e.id)} className="row-hover border-b border-[var(--line-soft)] cursor-pointer" data-testid={`exp-row-${e.id}`}>
                  <Td className="font-semibold text-sm">{e.title}</Td>
                  <Td className="text-xs">{e.claimant_name}</Td>
                  <Td className="font-mono">{fmtMoney(e.total)}</Td>
                  <Td><span className={`text-[10px] font-mono uppercase px-2 py-0.5 ${STATUS_TONE[e.status]}`}>{statusLabel(e.status)}</span></Td>
                  <Td className="text-xs">{e.pending_approver_role || "—"}</Td>
                  <Td className="font-mono text-xs">{formatDate(e.created_at)}</Td>
                </tr>
              ))}
              {loading && expenses.length === 0 && <SkeletonRows cols={6} />}
              {!loading && expenses.length === 0 && (
                <EmptyRow cols={6} icon={Receipt} title="No claims here"
                  hint="Staff claims for travel, site purchases and other spends appear here for approval."
                  actionLabel={canCreate ? "New claim" : undefined} onAction={() => setShowCreate(true)} />
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && <CreateExpense onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {editExpense && <CreateExpense initial={editExpense} expenseId={editExpense.id}
        onClose={() => setEditExpense(null)} onCreated={() => { setEditExpense(null); load(); }} />}
      {detail && <ExpenseDetail expId={detail} accounts={accounts} isAdmin={isAdmin}
        isFinance={isFinance} canCreate={canCreate} canManage={canManage} canDeletePosted={canDeletePosted}
        userId={user?.user_id} userRole={user?.role} onClose={() => setDetail(null)}
        onEdit={(expense) => { setDetail(null); setEditExpense(expense); }} onChange={load} />}
    </div>
  );
}

function KPI({ label, value, tone }) {
  return (
    <div className="card-flat p-4 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: tone }} />
      <div className="overline text-[10px] text-[var(--ink-2)] mb-1">{label}</div>
      <div className="font-display font-bold tracking-tighter text-3xl tabular-nums">{value ?? "—"}</div>
    </div>
  );
}

const CATEGORIES = ["travel","meals","materials","utilities","site","office","other"];
const CATEGORY_LABEL = {
  travel: "Travel", meals: "Meals", materials: "Materials", utilities: "Utilities",
  site: "Site spend", office: "Office", other: "Other",
};
let lineKeySeq = 0;
const nextLineKey = () => `line-${++lineKeySeq}`;
const blankLine = () => ({
  _key: nextLineKey(), category: "travel", amount: "", description: "", tax_rate: 0,
  receipt_url: "", receipt_file_id: null, receipt_file: null, link_mode: false,
});

// Receipts: a photo or PDF stored on our own server (see POST /expenses/receipts).
const RECEIPT_ID = /^rcpt_[a-f0-9]{12}$/;
const RECEIPT_TYPES = { "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf" };
const RECEIPT_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".pdf"];
const RECEIPT_ACCEPT = `${Object.keys(RECEIPT_TYPES).join(",")},${RECEIPT_EXTENSIONS.join(",")}`;
const MAX_RECEIPT_BYTES = 15 * 1024 * 1024;
const SHRINK_PHOTOS_ABOVE = 1.5 * 1024 * 1024;  // phone photos are often 4–12 MB
const PHOTO_MAX_SIDE = 2000;                    // still sharp enough to read a bill

const receiptHref = (file) =>
  (file && RECEIPT_ID.test(file.id || "") ? `${API}/expenses/receipts/${file.id}/content` : null);

const fileExtension = (name) => ((name || "").toLowerCase().match(/\.[a-z0-9]+$/) || [""])[0];

function receiptTypeOk(file) {
  return Boolean(RECEIPT_TYPES[file.type]) || RECEIPT_EXTENSIONS.includes(fileExtension(file.name));
}

/** The server decides the type from the file name's extension and contents; make sure there is one. */
function withReceiptName(file) {
  if (RECEIPT_EXTENSIONS.includes(fileExtension(file.name))) return file;
  const extension = RECEIPT_TYPES[file.type] || ".jpg";
  return new File([file], `receipt${extension}`, { type: file.type });
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("unreadable image")); };
    img.src = url;
  });
}

/** Big phone photos are re-saved as a smaller JPEG so they upload quickly on mobile data. */
async function shrinkPhoto(file) {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size <= SHRINK_PHOTOS_ABOVE) return file;
  try {
    const img = await loadImage(file);
    const scale = Math.min(1, PHOTO_MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#FFFFFF";  // transparent PNGs become white, not black
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
    if (!blob || blob.size >= file.size) return file;
    const base = (file.name || "receipt").replace(/\.[^.]+$/, "") || "receipt";
    return new File([blob], `${base}.jpg`, { type: "image/jpeg" });
  } catch {
    return file;  // send the original; the server still checks it
  }
}

const isTouchDevice = () => {
  try { return Boolean(window.matchMedia?.("(pointer: coarse)")?.matches); } catch { return false; }
};

function CreateExpense({ onClose, onCreated, initial = null, expenseId = null }) {
  const [f, setF] = useState({
    title: initial?.title || "", payment_mode: initial?.payment_mode || "personal",
    notes: initial?.notes || "", project_id: initial?.project_id || null,
    vendor_id: initial?.vendor_id || null,
    reimburse_to_account_id: initial?.reimburse_to_account_id || null,
    lines: initial?.lines?.map((line) => ({
      _key: nextLineKey(),
      category: line.category, amount: Number(line.amount || 0),
      description: line.description || "", receipt_url: line.receipt_url || "",
      receipt_file_id: line.receipt_file_id || null, receipt_file: line.receipt_file || null,
      link_mode: Boolean(line.receipt_url) && !line.receipt_file_id,
      tax_rate: Number(line.tax_rate || 0), date: line.date || null,
    })) || [blankLine()],
  });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const [receiptAbove, setReceiptAbove] = useState(null);
  const [touch] = useState(isTouchDevice);
  const total = f.lines.reduce((s, l) => s + Number(l.amount || 0) + Number(l.amount || 0) * Number(l.tax_rate || 0)/100, 0);
  const uploading = f.lines.some((line) => line._busy);
  const hasAnyReceipt = f.lines.some((line) => line.receipt_file_id || (line.link_mode && safeExternalUrl(line.receipt_url)));
  const needsReceipt = receiptAbove > 0 && total > receiptAbove && !hasAnyReceipt;

  useEffect(() => {
    let live = true;
    api.get("/expense-policy")
      .then(({ data }) => { if (live) setReceiptAbove(Number(data?.require_receipt_above) || 0); })
      .catch(() => {});
    return () => { live = false; };
  }, []);

  const patchLine = (key, patch) =>
    setF((s) => ({ ...s, lines: s.lines.map((x) => (x._key === key ? { ...x, ...patch } : x)) }));

  // Receipts uploaded in this form but not saved on the claim yet can be thrown away.
  const discardReceipt = (line) => {
    if (line?._fresh && line.receipt_file_id) api.delete(`/expenses/receipts/${line.receipt_file_id}`).catch(() => {});
  };
  const close = () => { f.lines.forEach(discardReceipt); onClose(); };

  const attachReceipt = async (key, picked) => {
    if (!receiptTypeOk(picked)) {
      patchLine(key, { _error: "Attach a photo (JPG, PNG or WebP) or a PDF. For iPhone HEIC photos, use Photo to take a fresh picture." });
      return;
    }
    patchLine(key, { _busy: true, _progress: 0, _error: "" });
    try {
      const file = await shrinkPhoto(withReceiptName(picked));
      if (file.size > MAX_RECEIPT_BYTES) throw new Error("This file is larger than 15 MB. Take the photo again or attach a smaller PDF.");
      const form = new FormData();
      form.append("upload", file, file.name);
      const { data } = await api.post("/expenses/receipts", form, {
        onUploadProgress: (event) => {
          if (event.total) patchLine(key, { _progress: Math.min(99, Math.round((event.loaded * 100) / event.total)) });
        },
      });
      patchLine(key, {
        _busy: false, _progress: null, _fresh: true, receipt_file_id: data.id, receipt_file: data,
        receipt_url: "", link_mode: false,
      });
    } catch (ex) {
      patchLine(key, {
        _busy: false, _progress: null,
        _error: ex?.response
          ? fmtErr(ex.response.data?.detail, "Upload failed")
          : (ex?.message && !/network/i.test(ex.message) ? ex.message : "Upload failed. Check your connection and try again."),
      });
    }
  };

  const removeReceipt = (line) => {
    discardReceipt(line);
    patchLine(line._key, { receipt_file_id: null, receipt_file: null, _fresh: false, _error: "" });
  };

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const body = {
        ...f,
        lines: f.lines.map((line) => ({
          category: line.category, description: line.description, date: line.date || null,
          tax_rate: Number(line.tax_rate) || 0, amount: Number(line.amount) || 0,
          receipt_file_id: line.receipt_file_id || null,
          receipt_url: line.link_mode ? (line.receipt_url || "").trim() || null : null,
        })),
      };
      if (expenseId) await api.put(`/expenses/${expenseId}`, body);
      else await api.post("/expenses", body);
      onCreated();
    } catch (ex) {
      setErr(fmtErr(ex?.response?.data?.detail, "Submit failed"));
    } finally { setBusy(false); }
  };
  return (
    <Modal onClose={close} title={expenseId ? "Correct Expense Claim" : "Submit Expense Claim"} eyebrow={expenseId ? "EDIT CLAIM" : "NEW CLAIM"} wide>
      <form onSubmit={submit} className="space-y-4" data-testid="exp-create-form">
        <F label="Title *"><input required data-testid="exp-title" className="input-flat w-full" value={f.title} onChange={(e) => setF({...f, title: e.target.value})} /></F>
        <F label="Payment mode">
          <select aria-label="Payment mode" className="input-flat w-full" value={f.payment_mode} onChange={(e) => setF({...f, payment_mode: e.target.value})}>
            <option value="personal">Paid personally (reimburse me)</option>
            <option value="cash">Company cash</option>
            <option value="corporate_card">Corporate card</option>
            <option value="bank_transfer">Bank transfer</option>
          </select>
        </F>

        <div>
          <div className="overline mb-2">WHAT WAS SPENT</div>
          <div className="hidden md:grid grid-cols-12 gap-2 px-1 pb-1 text-[11px] font-semibold text-[var(--ink-3)]">
            <span className="col-span-2">Category</span>
            <span className="col-span-4">What it was for</span>
            <span className="col-span-2 text-right">Amount (₹)</span>
            <span className="col-span-3">Receipt</span>
          </div>
          <div className="space-y-2">
            {f.lines.map((l, i) => {
              const setLine = (patch) => patchLine(l._key, patch);
              return (
                <div key={l._key} className="grid grid-cols-2 md:grid-cols-12 gap-2 items-center rounded-lg md:rounded-none border md:border-0 border-[var(--line)] p-2 md:p-0" data-testid={`exp-line-${i}`}>
                  <select aria-label="Category" className="input-flat col-span-1 md:col-span-2" value={l.category} onChange={(e) => setLine({ category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] || c}</option>)}
                  </select>
                  <input type="number" step="0.01" min="0" inputMode="decimal" aria-label="Amount" placeholder="0.00"
                    className="input-flat col-span-1 md:col-span-2 md:order-3 text-right tabular-nums" value={l.amount}
                    onChange={(e) => setLine({ amount: e.target.value })} />
                  <input aria-label="What it was for" placeholder="e.g. Auto to site, Andheri" className="input-flat col-span-2 md:col-span-4 md:order-2" value={l.description}
                    onChange={(e) => setLine({ description: e.target.value })} />
                  <div className="col-span-2 md:col-span-3 md:order-4 min-w-0">
                    <ReceiptCell line={l} index={i} touch={touch}
                      onPick={(file) => attachReceipt(l._key, file)}
                      onRemove={() => removeReceipt(l)}
                      onLink={(patch) => setLine(patch)} />
                  </div>
                  <div className="col-span-2 md:col-span-1 md:order-5 flex justify-end">
                    {f.lines.length > 1 && (
                      <button type="button" aria-label={`Remove line ${i + 1}`} title="Remove line"
                        onClick={() => { discardReceipt(l); setF((s) => ({ ...s, lines: s.lines.filter((x) => x._key !== l._key) })); }}
                        className="p-2 rounded-md text-[var(--ink-3)] hover:text-[var(--danger)] hover:bg-[var(--danger-soft)]"><X size={14} /></button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <button type="button" onClick={() => setF((s) => ({ ...s, lines: [...s.lines, blankLine()] }))} className="btn-ghost text-xs mt-2"><Plus size={11}/> Add another item</button>
          <p className="text-[11px] text-[var(--ink-3)] mt-2">
            {receiptAbove > 0
              ? `Claims above ${fmtMoney(receiptAbove)} need a receipt before they go for approval. Take a photo of the bill or attach a PDF.`
              : "Take a photo of each bill or attach a PDF so the approver can check it."}
          </p>
          {needsReceipt && (
            <p className="text-[11px] text-[var(--warning)] mt-1" data-testid="exp-receipt-warning">
              <Warning size={11} className="inline mr-1" />
              This claim is above {fmtMoney(receiptAbove)} and has no receipt yet. It will wait as “{statusLabel("receipt_required")}” until you attach one.
            </p>
          )}
        </div>

        <F label="Notes"><textarea className="input-flat w-full h-16" value={f.notes} onChange={(e) => setF({...f, notes: e.target.value})} /></F>
        <div className="flex items-baseline justify-end gap-3 border-t border-[var(--line)] pt-3">
          <span className="text-sm text-[var(--ink-2)]">Total claim</span>
          <span className="font-display font-bold text-2xl tabular-nums" data-testid="exp-total">{fmtMoney(total)}</span>
        </div>

        {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={close} className="btn-ghost">Cancel</button>
          <button disabled={busy || uploading || !f.title || f.lines.length === 0 || f.lines.some((line) => !(Number(line.amount) > 0))} className="btn-primary" data-testid="exp-submit">{busy ? "Saving…" : uploading ? "Uploading receipt…" : expenseId ? "Save and restart approval" : "Submit claim"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ReceiptCell({ line, index, touch, onPick, onRemove, onLink }) {
  const photoInput = useRef(null);
  const fileInput = useRef(null);
  const label = `line ${index + 1}`;
  const pick = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";  // choosing the same file again still fires
    if (file) onPick(file);
  };
  const error = line._error && (
    <p role="alert" className="text-[11px] text-[var(--danger)] mt-1" data-testid={`exp-line-${index}-receipt-error`}>{line._error}</p>
  );

  if (line._busy) {
    return (
      <div className="h-[38px] flex items-center gap-2 text-xs text-[var(--ink-2)]" role="status" data-testid={`exp-line-${index}-receipt-uploading`}>
        <span className="h-3 w-3 rounded-full border-2 border-[var(--line-strong)] border-t-[var(--accent-strong)] animate-spin" aria-hidden="true" />
        Uploading receipt… {line._progress ? `${line._progress}%` : ""}
      </div>
    );
  }
  if (line.receipt_file) {
    return (
      <div>
        <ReceiptChip file={line.receipt_file} testId={`exp-line-${index}-receipt`}
          onRemove={onRemove} removeLabel={`Remove receipt from ${label}`} />
        {error}
      </div>
    );
  }
  if (line.link_mode) {
    return (
      <div>
        <div className="flex items-center gap-1">
          <input aria-label="Receipt link" type="url" placeholder="Paste a photo or Drive link"
            className="input-flat w-full min-w-0" value={line.receipt_url}
            onChange={(e) => onLink({ receipt_url: e.target.value })} />
          <button type="button" className="btn-icon shrink-0" aria-label={`Attach a file instead for ${label}`}
            title="Attach a photo or PDF instead" onClick={() => onLink({ link_mode: false, receipt_url: "" })}><X size={13} /></button>
        </div>
        {error}
      </div>
    );
  }
  return (
    <div>
      <div className="flex items-center gap-1.5 flex-wrap">
        {touch && (
          <button type="button" className="btn-ghost text-xs" aria-label={`Take a photo of the receipt for ${label}`}
            onClick={() => photoInput.current?.click()} data-testid={`exp-line-${index}-photo`}>
            <Camera size={14} /> Photo
          </button>
        )}
        <button type="button" className="btn-ghost text-xs" aria-label={`Attach a receipt photo or PDF for ${label}`}
          onClick={() => fileInput.current?.click()} data-testid={`exp-line-${index}-attach`}>
          <Paperclip size={14} /> {touch ? "File" : "Attach receipt"}
        </button>
        <button type="button" className="btn-icon h-8 w-8" aria-label={`Paste a receipt link for ${label}`}
          title="Paste a link instead" onClick={() => onLink({ link_mode: true })}><LinkSimple size={14} /></button>
        <input ref={photoInput} type="file" accept="image/*" capture="environment" className="hidden"
          tabIndex={-1} aria-hidden="true" onChange={pick} data-testid={`exp-line-${index}-photo-input`} />
        <input ref={fileInput} type="file" accept={RECEIPT_ACCEPT} className="hidden"
          tabIndex={-1} aria-hidden="true" onChange={pick} data-testid={`exp-line-${index}-file-input`} />
      </div>
      {error}
    </div>
  );
}

function ReceiptChip({ file, testId, onRemove, removeLabel }) {
  const href = receiptHref(file);
  const isImage = String(file?.content_type || "").startsWith("image/");
  const name = file?.original_name || (isImage ? "Receipt photo" : "Receipt");
  if (!href) return <span className="text-[var(--ink-3)]">—</span>;
  return (
    <div className="flex items-center gap-2 min-w-0" data-testid={testId}>
      <a href={href} target="_blank" rel="noreferrer" className="shrink-0" aria-label={`Open ${name}`}>
        {isImage
          ? <img src={href} alt="" loading="lazy" className="h-9 w-9 object-cover rounded border border-[var(--line)] bg-[var(--surface-2)]" />
          : <span className="h-9 w-9 rounded border border-[var(--line)] bg-[var(--surface-2)] flex items-center justify-center"><FilePdf size={18} className="text-[var(--danger)]" /></span>}
      </a>
      <a href={href} target="_blank" rel="noreferrer" title={name} className="accent-blue text-xs truncate min-w-0">{name}</a>
      {onRemove && (
        <button type="button" aria-label={removeLabel} title="Remove receipt" onClick={onRemove}
          className="p-1.5 rounded-md text-[var(--ink-3)] hover:text-[var(--danger)] hover:bg-[var(--danger-soft)] shrink-0"><X size={12} /></button>
      )}
    </div>
  );
}

function ExpenseDetail({ expId, accounts, isAdmin, isFinance, canCreate, canManage, canDeletePosted, userId, userRole, onClose, onEdit, onChange }) {
  const [exp, setExp] = useState(null);
  const [comment, setComment] = useState("");
  const [payFrom, setPayFrom] = useState(accounts[0]?.id || "");
  const [busy, setBusy] = useState(""); const [err, setErr] = useState("");

  const load = async () => { try { const { data } = await api.get(`/expenses/${expId}`); setExp(data); } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); } };
  useEffect(() => { load(); }, [expId]);

  const decide = async (decision) => {
    setBusy(decision); setErr("");
    try {
      await api.post(`/expenses/${expId}/decision`, { decision, comment });
      setComment("");
      await load(); onChange && onChange();
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
    finally { setBusy(""); }
  };
  const reimburse = async () => {
    if (!payFrom) return;
    setBusy("reimburse"); setErr("");
    try {
      await api.post(`/expenses/${expId}/reimburse`, { paid_from_account_id: payFrom });
      await load(); onChange && onChange();
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
    finally { setBusy(""); }
  };
  const cancelExpense = async () => {
    const posted = exp.status === "reimbursed";
    const message = posted
      ? "Delete this reimbursed expense? A balanced accounting reversal will be retained in the audit trail."
      : "Delete this expense claim? It will remain in the audit trail as cancelled.";
    if (!await confirmAction(message)) return;
    setBusy("delete"); setErr("");
    try {
      await api.delete(`/expenses/${expId}`);
      await load(); onChange && onChange();
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail)); }
    finally { setBusy(""); }
  };

  if (!exp) return <Modal onClose={onClose} title="Loading…" wide><div className="skeleton h-64"/></Modal>;
  const canDecide = ["pending_l1","pending_l2"].includes(exp.status) && (isAdmin || exp.pending_approver_role === userRole);
  const canReimburse = exp.status === "approved" && isFinance;
  const isOwner = exp.claimant_id === userId;
  const canEdit = !["reimbursed", "cancelled"].includes(exp.status) &&
    ((isOwner && canCreate) || isAdmin || canManage);
  const canCancel = exp.status !== "cancelled" && (exp.status === "reimbursed"
    ? (isAdmin || canDeletePosted)
    : ((isOwner && canCreate) || isAdmin || canManage));

  return (
    <Modal onClose={onClose} title={exp.title} eyebrow={`EXPENSE · ${exp.claimant_name}`} wide>
      {err && <div className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 mb-3">{err}</div>}

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <span className={`text-[10px] font-mono uppercase px-3 py-1 ${STATUS_TONE[exp.status]}`}>{statusLabel(exp.status)}</span>
        {exp.pending_approver_role && <span className="text-xs text-[var(--ink-2)]">Awaiting: <b>{exp.pending_approver_role}</b></span>}
        <span className="font-mono font-bold text-lg ml-auto accent-blue">{fmtMoney(exp.total)}</span>
      </div>

      {(canEdit || canCancel) && (
        <div className="flex gap-2 mb-4">
          {canEdit && <button type="button" className="btn-ghost text-xs" onClick={() => onEdit(exp)}><PencilSimple size={12}/> Edit claim</button>}
          {canCancel && <button type="button" disabled={busy === "delete"} className="btn-ghost text-xs text-[var(--danger)]" onClick={cancelExpense}><Trash size={12}/> {exp.status === "reimbursed" ? "Delete with reversal" : "Delete"}</button>}
        </div>
      )}

      {exp.status === "receipt_required" && (
        <div className="border border-[var(--warning)] bg-[var(--warning-soft)] p-3 mb-4 text-sm text-[var(--warning)] flex flex-wrap items-center gap-2" data-testid="exp-receipt-required">
          <Warning size={14} className="shrink-0" />
          <span>This claim needs a receipt before it can go for approval.</span>
          {canEdit && <button type="button" className="btn-ghost text-xs sm:ml-auto" onClick={() => onEdit(exp)}><Paperclip size={12}/> Attach receipt</button>}
        </div>
      )}

      <div className="overline mb-2">LINE ITEMS</div>
      <div className="border border-[var(--line)] mb-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]"><tr className="text-left">
            <Th>Category</Th><Th>Description</Th><Th>Amount</Th><Th>Receipt</Th>
          </tr></thead>
          <tbody>
            {exp.lines.map((l) => (
              <tr key={l.id} className="border-b border-[var(--line-soft)]">
                <Td className="text-xs uppercase font-mono">{l.category}</Td>
                <Td>{l.description || "—"}</Td>
                <Td className="font-mono">{fmtMoney(l.amount)}</Td>
                <Td className="max-w-[220px]">
                  {l.receipt_file
                    ? <ReceiptChip file={l.receipt_file} testId={`exp-receipt-${l.id}`} />
                    : safeExternalUrl(l.receipt_url)
                      ? <a href={safeExternalUrl(l.receipt_url)} target="_blank" rel="noreferrer" className="accent-blue text-xs">View link</a>
                      : <span className="text-[var(--ink-3)]">—</span>}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {exp.approval_trail?.length > 0 && (
        <div className="mb-6">
          <div className="overline mb-2">APPROVAL TRAIL</div>
          <div className="space-y-2">
            {exp.approval_trail.map((t, i) => (
              <div key={i} className="border border-[var(--line)] p-2 text-xs">
                <div className="font-mono">{(t.at || "").slice(0,16)} · {t.actor_name || t.actor} ({t.actor_role || "system"})</div>
                <div><b>{t.decision}</b> {t.comment && `— ${t.comment}`}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {canDecide && (
        <div className="border border-[var(--line)] rounded-lg p-3 mb-4 bg-[var(--surface-2)]">
          <div className="overline mb-2">MY DECISION</div>
          <textarea className="input-flat w-full h-16 mb-2" placeholder="Optional comment" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="dec-comment" />
          <div className="flex gap-2">
            <button disabled={busy === "approve"} onClick={() => decide("approve")} className="btn-primary text-xs" data-testid="approve-btn"><ThumbsUp size={12}/> Approve</button>
            <button disabled={busy === "reject"} onClick={() => decide("reject")} className="btn-ghost text-xs text-[var(--danger)]" data-testid="reject-btn"><ThumbsDown size={12}/> Reject</button>
          </div>
        </div>
      )}

      {canReimburse && (
        <div className="border border-[var(--line)] rounded-lg p-3 bg-[var(--hover)]">
          <div className="overline mb-2">REIMBURSE</div>
          <div className="flex flex-wrap gap-2 items-center">
            <select aria-label="Pay from" className="input-flat" value={payFrom} onChange={(e) => setPayFrom(e.target.value)} data-testid="pay-from">
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <button disabled={busy === "reimburse" || !payFrom} onClick={reimburse} className="btn-primary text-xs" data-testid="reimburse-btn">
              <Wallet size={12}/> {busy === "reimburse" ? "Posting…" : `Reimburse ${fmtMoney(exp.total)}`}
            </button>
          </div>
        </div>
      )}

      {exp.status === "reimbursed" && (
        <div className="border border-[var(--success)] bg-[var(--success-soft)] p-3 text-sm text-[var(--success)]">
          <Check size={13} className="inline mr-1"/> Reimbursed on {formatDate(exp.reimbursed_at)} · JE {exp.reimbursement_journal_id}
        </div>
      )}
    </Modal>
  );
}

function F({ label, children }) { return <label className="block"><div className="text-xs text-[var(--ink-2)] mb-1">{label}</div>{children}</label>; }
function Modal({ children, onClose, title, eyebrow, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className={`bg-white p-6 w-full border border-[var(--line)] rounded-xl max-h-[92vh] overflow-y-auto ${wide ? "max-w-5xl" : "max-w-2xl"}`}>
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
