import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api from "../lib/api";
import {
  Plus, X, PencilSimple, Trash, Play, ClockCounterClockwise, Warning, Pause,
  DownloadSimple, ClockClockwise, CaretDown, CaretRight,
} from "@phosphor-icons/react";

const CURRENCY = (n) => `₹${(Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const FREQ = [
  { id: "weekly", label: "Every week" },
  { id: "monthly", label: "Every month" },
  { id: "quarterly", label: "Every quarter" },
  { id: "yearly", label: "Every year" },
];

// Recurring Expenses tab — pay Rent / Internet / Salaries automatically.
export const RecurringExpenses = ({ accounts = [], vendors = [], projects = [], clients = [], onChanged }) => {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);

  const expenseAccs = useMemo(() => accounts.filter((a) => a.type === "expense" && a.active !== false), [accounts]);
  const banks = useMemo(() => accounts.filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name)), [accounts]);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/recurring-expenses");
      setRules(data || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const scan = async () => {
    try {
      const { data } = await api.post("/recurring-expenses/scan");
      toast.success(`Posted ${data.count} recurring entr${data.count === 1 ? "y" : "ies"}`);
      load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Scan failed");
    }
  };

  const runNow = async (id) => {
    try {
      await api.post(`/recurring-expenses/${id}/run-now`);
      toast.success("Posted!");
      load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not post");
    }
  };

  const togglePause = async (rule) => {
    try {
      await api.patch(`/recurring-expenses/${rule.id}`, { active: !rule.active });
      toast.success(rule.active ? "Paused" : "Resumed");
      load();
    } catch (e) {
      toast.error("Could not update");
    }
  };

  const doDelete = async (id) => {
    if (!window.confirm("Delete this recurring rule? Already-posted entries are kept.")) return;
    try {
      await api.delete(`/recurring-expenses/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) { toast.error("Delete failed"); }
  };

  return (
    <div className="space-y-4" data-testid="recurring-tab">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="overline">RECURRING EXPENSES</div>
          <div className="text-xs text-[#5C5C5C] mt-0.5">Rent, Internet, Salaries — post themselves each period. Idempotent (never posts twice for the same date).</div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={scan} className="btn-ghost text-xs" data-testid="rec-scan-btn">
            <ClockCounterClockwise size={12} /> Post all due
          </button>
          <button onClick={() => { setEditing(null); setShowForm(true); }} className="btn-primary text-xs" data-testid="rec-new-btn">
            <Plus size={12} /> New rule
          </button>
        </div>
      </div>

      {showForm && (
        <RuleForm
          initial={editing}
          expenseAccs={expenseAccs}
          banks={banks}
          vendors={vendors}
          projects={projects}
          clients={clients}
          onCancel={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => { setShowForm(false); setEditing(null); load(); }}
        />
      )}

      <div className="border border-[#E5E5E5] overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr>
              <th className="p-3 text-left">Name</th>
              <th className="p-3 text-left">Frequency</th>
              <th className="p-3 text-left">Account</th>
              <th className="p-3 text-right">Amount</th>
              <th className="p-3 text-left">Next run</th>
              <th className="p-3 text-left">Runs</th>
              <th className="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="rec-rows">
            {rules.map((r) => {
              const expName = expenseAccs.find((a) => a.id === r.expense_account_id)?.name || "—";
              const isDue = r.next_run_date && r.next_run_date <= new Date().toISOString().slice(0, 10);
              return (
                <tr key={r.id} className={`border-t border-[#F0F0F0] ${!r.active ? "opacity-60" : ""}`} data-testid={`rec-row-${r.id}`}>
                  <td className="p-3">
                    <div className="font-semibold">{r.name}</div>
                    {!r.active && <div className="text-[10px] text-[#B87500] mt-0.5"><Pause size={10} className="inline mr-1" />PAUSED</div>}
                  </td>
                  <td className="p-3 text-xs">{FREQ.find((f) => f.id === r.frequency)?.label || r.frequency}</td>
                  <td className="p-3 text-xs">{expName}</td>
                  <td className="p-3 text-right font-mono">{CURRENCY(r.amount)}</td>
                  <td className={`p-3 font-mono text-xs ${isDue && r.active ? "text-[#B4001C] font-semibold" : "text-[#5C5C5C]"}`}>
                    {r.next_run_date}
                    {isDue && r.active && <span className="ml-1 text-[10px] font-semibold">DUE</span>}
                  </td>
                  <td className="p-3 text-xs">{r.run_count || 0}</td>
                  <td className="p-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button onClick={() => runNow(r.id)} className="btn-ghost text-[11px]" title="Post now" data-testid={`rec-run-${r.id}`}>
                        <Play size={11} />
                      </button>
                      <button onClick={() => togglePause(r)} className="btn-ghost text-[11px]" title={r.active ? "Pause" : "Resume"}>
                        <Pause size={11} />
                      </button>
                      <button onClick={() => { setEditing(r); setShowForm(true); }} className="btn-ghost text-[11px]" title="Edit">
                        <PencilSimple size={11} />
                      </button>
                      <button onClick={() => doDelete(r.id)} className="btn-ghost text-[11px] text-[#B4001C]" title="Delete">
                        <Trash size={11} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!loading && rules.length === 0 && (
              <tr><td colSpan={7} className="p-10 text-center text-[#9A9A9A]">
                No recurring rules yet. Add one for Rent, Internet, or Salaries so they post themselves.
              </td></tr>
            )}
            {loading && <tr><td colSpan={7} className="p-10 text-center overline">LOADING…</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const emptyRule = () => ({
  name: "", amount: "", frequency: "monthly", day_of_month: 1,
  day_of_week: 1, expense_account_id: "", paid_from_account_id: "",
  vendor_id: "", project_id: "", client_id: "", reference: "",
  gst: "", notes: "", start_date: new Date().toISOString().slice(0, 10),
  end_date: "",
});

const RuleForm = ({ initial, expenseAccs, banks, vendors, projects, clients, onCancel, onSaved }) => {
  const [form, setForm] = useState(() => (initial ? { ...emptyRule(), ...initial } : emptyRule()));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!form.expense_account_id && expenseAccs[0]) setForm((s) => ({ ...s, expense_account_id: expenseAccs[0].id }));
    if (!form.paid_from_account_id && banks[0]) setForm((s) => ({ ...s, paid_from_account_id: banks[0].id }));
  }, [expenseAccs, banks]); // eslint-disable-line

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = { ...form };
      payload.amount = Number(payload.amount);
      if (payload.gst) payload.gst = Number(payload.gst);
      if (payload.day_of_month) payload.day_of_month = Number(payload.day_of_month);
      if (payload.day_of_week !== "" && payload.day_of_week !== null) payload.day_of_week = Number(payload.day_of_week);
      Object.keys(payload).forEach((k) => { if (payload[k] === "" || payload[k] == null) delete payload[k]; });
      if (initial) {
        await api.patch(`/recurring-expenses/${initial.id}`, payload);
        toast.success("Rule updated");
      } else {
        await api.post("/recurring-expenses", payload);
        toast.success("Rule created");
      }
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="card-flat space-y-3" data-testid="rec-form">
      <div className="flex items-center justify-between">
        <div className="overline">{initial ? "EDIT RULE" : "NEW RECURRING RULE"}</div>
        <button type="button" onClick={onCancel} className="btn-ghost text-xs"><X size={12} /></button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input required className="input-flat" placeholder="Name (e.g. Office Rent)" value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="rec-name" />
        <input required type="number" step="0.01" className="input-flat" placeholder="Amount"
          value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="rec-amount" />
        <select className="input-flat" value={form.frequency}
          onChange={(e) => setForm({ ...form, frequency: e.target.value })} data-testid="rec-frequency">
          {FREQ.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
        </select>
        {form.frequency !== "weekly" && (
          <input type="number" min="1" max="28" className="input-flat" placeholder="Day of month (1-28)"
            value={form.day_of_month} onChange={(e) => setForm({ ...form, day_of_month: e.target.value })} data-testid="rec-dom" />
        )}
        {form.frequency === "weekly" && (
          <select className="input-flat" value={form.day_of_week}
            onChange={(e) => setForm({ ...form, day_of_week: e.target.value })}>
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => <option key={i} value={i}>{d}</option>)}
          </select>
        )}
        <select required className="input-flat" value={form.expense_account_id}
          onChange={(e) => setForm({ ...form, expense_account_id: e.target.value })} data-testid="rec-expense-acc">
          <option value="" disabled>Expense account</option>
          {expenseAccs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select required className="input-flat" value={form.paid_from_account_id}
          onChange={(e) => setForm({ ...form, paid_from_account_id: e.target.value })} data-testid="rec-bank-acc">
          <option value="" disabled>Paid from (bank/cash)</option>
          {banks.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input type="date" className="input-flat" value={form.start_date}
          onChange={(e) => setForm({ ...form, start_date: e.target.value })} placeholder="Start date" />
        <input type="date" className="input-flat" value={form.end_date}
          onChange={(e) => setForm({ ...form, end_date: e.target.value })} placeholder="End date (optional)" />
        <input type="number" step="0.01" className="input-flat" placeholder="GST amount (optional)"
          value={form.gst} onChange={(e) => setForm({ ...form, gst: e.target.value })} />
        <select className="input-flat" value={form.vendor_id}
          onChange={(e) => setForm({ ...form, vendor_id: e.target.value })}>
          <option value="">— Vendor (optional) —</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
        <select className="input-flat" value={form.project_id}
          onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
          <option value="">— Project (optional) —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select className="input-flat" value={form.client_id}
          onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
          <option value="">— Client (optional) —</option>
          {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <input className="input-flat" placeholder="Reference (optional)"
        value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
      <input className="input-flat" placeholder="Notes (optional)"
        value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      <div className="flex items-center gap-2 justify-end">
        <button type="button" onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
        <button type="submit" disabled={busy} className="btn-primary text-xs" data-testid="rec-submit">
          {busy ? "Saving…" : (initial ? "Update rule" : "Create rule")}
        </button>
      </div>
    </form>
  );
};

// Bank Reconciliation tab
export const BankReconciliation = ({ accounts = [] }) => {
  const banks = useMemo(() => accounts.filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name)), [accounts]);
  const [selectedBank, setSelectedBank] = useState("");
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [linkRow, setLinkRow] = useState(null);
  const [createFor, setCreateFor] = useState(null);
  const [batches, setBatches] = useState([]);
  const [showLog, setShowLog] = useState(false);

  useEffect(() => {
    if (!selectedBank && banks[0]) setSelectedBank(banks[0].id);
  }, [banks]); // eslint-disable-line

  const loadBatches = async () => {
    if (!selectedBank) { setBatches([]); return; }
    try {
      const { data } = await api.get(`/bank-reconciliation/${selectedBank}/batches`);
      setBatches(data.batches || []);
    } catch { /* interceptor toasts */ }
  };
  useEffect(() => { loadBatches(); }, [selectedBank]); // eslint-disable-line

  const downloadBatch = async (batch) => {
    try {
      const res = await api.get(`/bank-reconciliation/batches/${batch.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = batch.filename || `import-${batch.id}.csv`;
      document.body.appendChild(link); link.click(); link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Download failed");
    }
  };

  const deleteBatch = async (batch, force = false) => {
    if (!force && !window.confirm(`Delete this import "${batch.filename}"? Its ${batch.rows_saved} statement row(s) will be removed. Posted journal entries are kept.`)) return;
    try {
      const qs = force ? "?force=true" : "";
      await api.delete(`/bank-reconciliation/batches/${batch.id}${qs}`);
      toast.success("Import deleted");
      loadBatches();
      load();
    } catch (e) {
      if (e?.response?.status === 409) {
        if (window.confirm(`${e.response.data.detail}\n\nDelete anyway? Journal entries stay on the books.`)) {
          return deleteBatch(batch, true);
        }
        return;
      }
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  const load = async () => {
    if (!selectedBank) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      const { data } = await api.get(`/bank-reconciliation/${selectedBank}/rows${params.toString() ? "?" + params : ""}`);
      setRows(data.rows || []);
      setCounts(data.counts || {});
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [selectedBank, statusFilter]); // eslint-disable-line

  const upload = async (file) => {
    if (!file || !selectedBank) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/bank-reconciliation/${selectedBank}/upload`, fd);
      toast.success(`${data.rows_saved} rows uploaded · ${data.auto_matched} auto-matched`);
      load();
      loadBatches();
      setShowLog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally { setUploading(false); }
  };

  const act = async (rowId, endpoint, method = "post", body) => {
    try {
      await api[method](`/bank-reconciliation/rows/${rowId}/${endpoint}`, body);
      toast.success("Done");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action failed");
    }
  };

  return (
    <div className="space-y-4" data-testid="bank-rec-tab">
      <div>
        <div className="overline">BANK RECONCILIATION</div>
        <div className="text-xs text-[#5C5C5C] mt-0.5">Upload your bank statement CSV → we auto-match rows to posted journal entries and flag the rest for review.</div>
      </div>

      <div className="card-flat space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <select className="input-flat max-w-xs" value={selectedBank} onChange={(e) => setSelectedBank(e.target.value)} data-testid="bank-rec-account">
            {banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <select className="input-flat max-w-xs" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="bank-rec-status-filter">
            <option value="">All statuses</option>
            <option value="unmatched">Unmatched</option>
            <option value="auto_matched">Auto-matched</option>
            <option value="matched">Matched</option>
            <option value="reconciled">Reconciled</option>
            <option value="ignored">Ignored</option>
          </select>
          <label className="btn-ghost text-xs cursor-pointer" data-testid="bank-rec-upload-btn">
            {uploading ? "Uploading…" : "Upload CSV"}
            <input type="file" accept=".csv,text/csv" className="hidden" disabled={uploading}
              onChange={(e) => upload(e.target.files?.[0])} />
          </label>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
          {[
            { k: "unmatched", label: "Unmatched", tint: "#B4001C" },
            { k: "auto_matched", label: "Auto-matched", tint: "#B87500" },
            { k: "matched", label: "Matched", tint: "#8B7F6A" },
            { k: "reconciled", label: "Reconciled", tint: "#1D633E" },
            { k: "ignored", label: "Ignored", tint: "#5C5C5C" },
          ].map((s) => (
            <div key={s.k} className="border border-[#E5E5E5] p-2 text-center">
              <div className="overline">{s.label}</div>
              <div className="font-mono font-bold text-lg" style={{ color: s.tint }}>{counts[s.k] || 0}</div>
            </div>
          ))}
        </div>
        <div className="text-[11px] text-[#9A9A9A]">
          Expected CSV columns (case-insensitive): <code>Date, Description, Debit, Credit</code> (or a single signed <code>Amount</code>), and optional <code>Reference</code>.
        </div>
      </div>

      {/* Import Log — history of uploaded statements for this account */}
      <div className="card-flat" data-testid="import-log-panel">
        <button
          type="button"
          onClick={() => setShowLog((v) => !v)}
          className="w-full flex items-center justify-between text-left"
          data-testid="import-log-toggle"
        >
          <div className="flex items-center gap-2">
            {showLog ? <CaretDown size={12} /> : <CaretRight size={12} />}
            <ClockClockwise size={13} className="text-[#8B7F6A]" />
            <span className="overline">IMPORT LOG</span>
            <span className="text-[11px] text-[#9A9A9A]">
              {batches.length} upload{batches.length === 1 ? "" : "s"}
            </span>
          </div>
          <span className="text-[11px] text-[#9A9A9A]">Re-download or delete a bad import</span>
        </button>

        {showLog && (
          <div className="mt-3 border border-[#E5E5E5] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
                <tr>
                  <th className="p-3 text-left">Uploaded</th>
                  <th className="p-3 text-left">File</th>
                  <th className="p-3 text-right">Rows</th>
                  <th className="p-3 text-right">Auto-matched</th>
                  <th className="p-3 text-right">Reconciled</th>
                  <th className="p-3 text-right">Remaining</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody data-testid="import-log-rows">
                {batches.map((b) => {
                  const live = b.live || {};
                  return (
                    <tr key={b.id} className="border-t border-[#F0F0F0]" data-testid={`import-batch-${b.id}`}>
                      <td className="p-3 text-xs">
                        <div className="font-mono">{(b.created_at || "").slice(0, 16).replace("T", " ")}</div>
                        <div className="text-[10px] text-[#9A9A9A]">{b.created_by_name || "—"}</div>
                      </td>
                      <td className="p-3 text-xs max-w-[220px] truncate" title={b.filename}>{b.filename || "—"}</td>
                      <td className="p-3 text-right font-mono text-xs">{b.rows_saved ?? 0}</td>
                      <td className="p-3 text-right font-mono text-xs text-[#B87500]">{b.auto_matched ?? 0}</td>
                      <td className="p-3 text-right font-mono text-xs text-[#1D633E]">{live.reconciled ?? 0}</td>
                      <td className="p-3 text-right font-mono text-xs text-[#5C5C5C]">{live.total ?? 0}</td>
                      <td className="p-3 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button onClick={() => downloadBatch(b)} className="btn-ghost text-[11px]" title="Re-download original CSV" data-testid={`import-download-${b.id}`}>
                            <DownloadSimple size={12} /> CSV
                          </button>
                          <button onClick={() => deleteBatch(b)} className="btn-ghost text-[11px] text-[#B4001C]" title="Delete this import" data-testid={`import-delete-${b.id}`}>
                            <Trash size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {batches.length === 0 && (
                  <tr><td colSpan={7} className="p-8 text-center text-[#9A9A9A]">
                    No statement imports yet for this account.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="border border-[#E5E5E5] overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr>
              <th className="p-3 text-left">Date</th>
              <th className="p-3 text-left">Description</th>
              <th className="p-3 text-left">Reference</th>
              <th className="p-3 text-right">Amount</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="bank-rec-rows">
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-[#F0F0F0]" data-testid={`bank-row-${r.id}`}>
                <td className="p-3 font-mono text-xs">{r.date}</td>
                <td className="p-3 max-w-[280px] truncate">{r.description || "—"}</td>
                <td className="p-3 font-mono text-xs text-[#5C5C5C]">{r.reference || "—"}</td>
                <td className={`p-3 text-right font-mono font-semibold ${r.amount > 0 ? "text-[#1D633E]" : "text-[#B4001C]"}`}>
                  {r.amount > 0 ? "+" : ""}{CURRENCY(r.amount)}
                </td>
                <td className="p-3"><StatusChip status={r.status} /></td>
                <td className="p-3 text-right">
                  <div className="inline-flex items-center gap-1">
                    {r.status !== "reconciled" && r.matched_journal_id && (
                      <button onClick={() => act(r.id, "reconcile")} className="btn-ghost text-[11px]">Reconcile</button>
                    )}
                    {!r.matched_journal_id && (
                      <>
                        <button onClick={() => setLinkRow(r)} className="btn-ghost text-[11px]" data-testid={`bank-link-${r.id}`}>Link JE</button>
                        <button onClick={() => setCreateFor(r)} className="btn-ghost text-[11px]" data-testid={`bank-create-${r.id}`}>Create JE</button>
                      </>
                    )}
                    {r.status !== "ignored" && (
                      <button onClick={() => act(r.id, "ignore")} className="btn-ghost text-[11px] text-[#5C5C5C]" title="Ignore">
                        <X size={11} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={6} className="p-10 text-center text-[#9A9A9A]">
                No rows. Upload your bank statement CSV to get started.
              </td></tr>
            )}
            {loading && <tr><td colSpan={6} className="p-10 text-center overline">LOADING…</td></tr>}
          </tbody>
        </table>
      </div>

      {linkRow && (
        <LinkJEDialog row={linkRow} accountId={selectedBank}
          onClose={() => setLinkRow(null)}
          onLinked={() => { setLinkRow(null); load(); }} />
      )}
      {createFor && (
        <CreateJEDialog row={createFor} accounts={accounts}
          onClose={() => setCreateFor(null)}
          onCreated={() => { setCreateFor(null); load(); }} />
      )}
    </div>
  );
};

const StatusChip = ({ status }) => {
  const map = {
    unmatched:    { label: "Unmatched",    tint: "#B4001C", bg: "#FCEEEC", border: "#F1CFCF" },
    auto_matched: { label: "Auto-matched", tint: "#B87500", bg: "#FFF4E5", border: "#EADFB9" },
    matched:      { label: "Matched",      tint: "#8B7F6A", bg: "#F5F4F0", border: "#E5E5E5" },
    reconciled:   { label: "Reconciled",   tint: "#1D633E", bg: "#EFF7EF", border: "#CDE5D8" },
    ignored:      { label: "Ignored",      tint: "#5C5C5C", bg: "#F5F5F5", border: "#E5E5E5" },
  };
  const s = map[status] || map.unmatched;
  return (
    <span className="inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border rounded-full"
      style={{ color: s.tint, background: s.bg, borderColor: s.border }}>
      {s.label}
    </span>
  );
};

const LinkJEDialog = ({ row, accountId, onClose, onLinked }) => {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const load = async () => {
      const from = new Date(new Date(row.date).getTime() - 5 * 86400000).toISOString().slice(0, 10);
      const to = new Date(new Date(row.date).getTime() + 5 * 86400000).toISOString().slice(0, 10);
      const { data } = await api.get(`/journal-entries?from_date=${from}&to_date=${to}&account_id=${accountId}&limit=50&offset=0`);
      const items = Array.isArray(data) ? data : (data.items || []);
      setCandidates(items);
      setLoading(false);
    };
    load();
  }, [row, accountId]);

  const link = async (je) => {
    try {
      await api.post(`/bank-reconciliation/rows/${row.id}/match`, { journal_id: je.id });
      toast.success("Linked");
      onLinked();
    } catch (e) { toast.error("Failed to link"); }
  };

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[301] w-full max-w-2xl bg-white shadow-2xl max-h-[85vh] overflow-hidden flex flex-col rounded-lg" data-testid="link-je-dialog">
        <div className="p-4 border-b border-[#E5E5E5] flex items-start justify-between">
          <div>
            <div className="overline text-[#8B7F6A]">LINK BANK ROW TO JOURNAL ENTRY</div>
            <div className="font-semibold mt-1">{row.description}</div>
            <div className="text-xs text-[#5C5C5C] mt-0.5">{row.date} · {CURRENCY(row.amount)}</div>
          </div>
          <button onClick={onClose} className="btn-ghost"><X size={14} /></button>
        </div>
        <div className="flex-1 overflow-auto">
          {loading && <div className="p-8 text-center overline">LOADING…</div>}
          {!loading && candidates.length === 0 && <div className="p-8 text-center text-[#9A9A9A]">No candidate journal entries in this bank account ±5 days.</div>}
          {candidates.map((je) => (
            <button key={je.id} onClick={() => link(je)}
              className="w-full text-left p-3 border-t border-[#F0F0F0] hover:bg-[#FAFAF7] block">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <div className="text-sm font-semibold truncate">{je.narration || "—"}</div>
                  <div className="text-xs text-[#5C5C5C]">{je.date} · {je.reference || ""} · {je.source}</div>
                </div>
                <div className="font-mono font-semibold text-sm">{CURRENCY(je.total)}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

const CreateJEDialog = ({ row, accounts, onClose, onCreated }) => {
  const wantType = row.amount > 0 ? "income" : "expense";
  const [counterId, setCounterId] = useState("");
  const [narration, setNarration] = useState(row.description || "");
  const options = useMemo(() => accounts.filter((a) => a.type === wantType && a.active !== false), [accounts, wantType]);
  useEffect(() => { if (options[0]) setCounterId(options[0].id); }, [options]);

  const submit = async () => {
    if (!counterId) { toast.error("Pick a counterpart account"); return; }
    try {
      await api.post(`/bank-reconciliation/rows/${row.id}/create-je`, {
        counterpart_account_id: counterId,
        narration,
      });
      toast.success("Journal entry created + linked");
      onCreated();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <div onClick={(e) => e.stopPropagation()} className="relative z-[301] w-full max-w-lg bg-white shadow-2xl rounded-lg" data-testid="create-je-dialog">
        <div className="p-4 border-b border-[#E5E5E5] flex items-start justify-between">
          <div>
            <div className="overline text-[#8B7F6A]">CREATE JOURNAL ENTRY</div>
            <div className="font-semibold mt-1">{row.description}</div>
            <div className="text-xs text-[#5C5C5C] mt-0.5">{row.date} · {CURRENCY(row.amount)} · {wantType.toUpperCase()}</div>
          </div>
          <button onClick={onClose} className="btn-ghost"><X size={14} /></button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">Counterpart {wantType} account</label>
            <select className="input-flat w-full" value={counterId} onChange={(e) => setCounterId(e.target.value)}>
              {options.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-[#9A9A9A]">Narration</label>
            <input className="input-flat w-full" value={narration} onChange={(e) => setNarration(e.target.value)} />
          </div>
        </div>
        <div className="p-4 border-t border-[#E5E5E5] flex justify-end gap-2">
          <button onClick={onClose} className="btn-ghost text-xs">Cancel</button>
          <button onClick={submit} className="btn-primary text-xs" data-testid="create-je-submit">Post & link</button>
        </div>
      </div>
    </div>
  );
};

// Favorite accounts sidebar strip — one-click access to pinned ledgers.
export const FavoriteAccountsStrip = ({ onOpen }) => {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/favorite-accounts").then(({ data }) => setRows(data.accounts || [])).catch(() => {});
  }, []);
  if (rows.length === 0) return null;
  return (
    <div className="card-flat" data-testid="favorite-accounts-strip">
      <div className="overline mb-2">FAVOURITES</div>
      <div className="flex flex-wrap gap-1.5">
        {rows.map((a) => (
          <button key={a.id} onClick={() => onOpen && onOpen(a)}
            className="px-3 py-1 text-xs rounded-full border border-[#E5E5E5] bg-white hover:border-[#8B7F6A] hover:text-[#8B7F6A] transition"
            data-testid={`fav-open-${a.id}`}>
            {a.name}
          </button>
        ))}
      </div>
    </div>
  );
};
