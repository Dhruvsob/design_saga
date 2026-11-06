import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { HandCoins, Plus, X } from "@phosphor-icons/react";
import api from "../lib/api";
import { dateForInput, formatDate, formatINR } from "../lib/format";
import { methodForAccount } from "../lib/cashbank";
import { confirmAction } from "../lib/confirm";

/** Employee advances: give, see outstanding and recoveries, cancel a mistake. */
export default function EmployeeAdvances({ employeeId, canWrite, onChanged }) {
  const [data, setData] = useState(null);
  const [banks, setBanks] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const blank = { amount: "", date: dateForInput(new Date()), reason: "", bank_account_id: "",
                  payment_method: "cash", reference: "", monthly_recovery: "" };
  const [form, setForm] = useState(blank);

  const load = useCallback(async () => {
    try {
      const { data: res } = await api.get(`/employees/${employeeId}/advances`);
      setData(res);
    } catch (e) {
      setData({ items: [], outstanding: 0, error: e?.response?.data?.detail || "Could not load advances" });
    }
  }, [employeeId]);
  useEffect(() => { load(); }, [load]);

  const openForm = async () => {
    setOpen(true);
    if (!banks.length) {
      const { data: accs } = await api.get("/accounts?type=asset");
      const list = (accs || []).filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name));
      setBanks(list);
      if (list[0]) setForm((f) => ({ ...f, bank_account_id: list[0].id, payment_method: methodForAccount(list[0]) }));
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/employees/${employeeId}/advances`, {
        ...form, amount: Number(form.amount),
        monthly_recovery: form.monthly_recovery === "" ? null : Number(form.monthly_recovery),
        reference: form.reference || null,
      });
      toast.success("Advance recorded and posted to accounts");
      setOpen(false);
      setForm({ ...blank, bank_account_id: form.bank_account_id, payment_method: form.payment_method });
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not record the advance");
    } finally { setBusy(false); }
  };

  const cancel = async (adv) => {
    if (!await confirmAction({
      title: `Cancel the ${formatINR(adv.amount)} advance?`,
      body: "A balancing journal is posted; the original entry stays in the audit trail.",
      confirmLabel: "Cancel advance", cancelLabel: "Go back", danger: true,
    })) return;
    try {
      await api.post(`/employees/${employeeId}/advances/${adv.id}/cancel`);
      toast.success("Advance cancelled");
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not cancel the advance");
    }
  };

  if (!data) return <div className="card-flat text-sm text-[var(--ink-3)]">Loading advances…</div>;

  return (
    <div className="card-flat" data-testid="employee-advances">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <div className="overline flex items-center gap-1.5"><HandCoins size={12} /> ADVANCES</div>
          <div className="mt-1 text-sm text-[var(--ink-2)]">
            Outstanding <strong className="text-[var(--ink)] font-mono text-base" data-testid="advance-outstanding">{formatINR(data.outstanding)}</strong>
            {data.suggested_recovery > 0 && <> · suggested recovery this month {formatINR(data.suggested_recovery)}</>}
          </div>
        </div>
        {canWrite && (
          <button type="button" className="btn-ghost" onClick={open ? () => setOpen(false) : openForm} data-testid="give-advance-btn">
            {open ? <><X size={13} /> Close</> : <><Plus size={13} /> Give advance</>}
          </button>
        )}
      </div>

      {open && (
        <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4 p-4 rounded-lg bg-[var(--surface-2)] border border-[var(--line)]" data-testid="advance-form">
          <label className="text-xs">Amount (Rs.)
            <input type="number" min="1" step="0.01" required className="input-flat mt-1 w-full" value={form.amount}
                   onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="advance-amount" />
          </label>
          <label className="text-xs">Date
            <input type="date" required className="input-flat mt-1 w-full" value={form.date}
                   onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </label>
          <label className="text-xs">Paid from
            <select aria-label="Paid from" className="input-flat mt-1 w-full" value={form.bank_account_id} required
                    onChange={(e) => {
                      const acc = banks.find((b) => b.id === e.target.value);
                      setForm({ ...form, bank_account_id: e.target.value, payment_method: methodForAccount(acc) });
                    }} data-testid="advance-account">
              {banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <label className="text-xs">Recover per month (optional)
            <input type="number" min="0" step="0.01" className="input-flat mt-1 w-full" value={form.monthly_recovery}
                   placeholder="e.g. 2000" onChange={(e) => setForm({ ...form, monthly_recovery: e.target.value })} />
          </label>
          <label className="text-xs sm:col-span-2">Reason
            <input className="input-flat mt-1 w-full" value={form.reason} maxLength={500}
                   placeholder="Emergency, medical, festival…" onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </label>
          <label className="text-xs">Reference
            <input className="input-flat mt-1 w-full" value={form.reference} maxLength={120}
                   onChange={(e) => setForm({ ...form, reference: e.target.value })} />
          </label>
          <div className="flex items-end">
            <button className="btn-primary w-full" disabled={busy || !banks.length} data-testid="advance-submit">
              {busy ? "Saving…" : "Record advance"}
            </button>
          </div>
        </form>
      )}

      {data.error && <p className="text-sm text-[var(--danger)]">{data.error}</p>}
      {data.items.length === 0 ? (
        <p className="text-sm text-[var(--ink-3)]">No advances given to this employee.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-[var(--ink-2)] border-b border-[var(--line)]">
                <th className="py-2 pr-3">Date</th><th className="py-2 pr-3">Reason</th>
                <th className="py-2 pr-3 text-right">Given</th><th className="py-2 pr-3 text-right">Recovered</th>
                <th className="py-2 pr-3 text-right">Outstanding</th><th className="py-2 pr-3">Status</th><th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id} className="border-b border-[var(--line-soft)] align-top">
                  <td className="py-2 pr-3 whitespace-nowrap font-mono text-xs">{formatDate(a.date)}</td>
                  <td className="py-2 pr-3">
                    <div>{a.reason || "—"}</div>
                    <div className="text-[11px] text-[var(--ink-3)]">{a.bank_account_name}{a.monthly_recovery ? ` · ${formatINR(a.monthly_recovery)}/month` : ""}</div>
                    {(a.recoveries || []).filter((r) => r.active !== false).map((r) => (
                      <div key={`${r.payroll_run_id}-${r.amount}`} className="text-[11px] text-[var(--success)]">
                        Recovered {formatINR(r.amount)} in salary {String(r.month).padStart(2, "0")}/{r.year}
                      </div>
                    ))}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono">{formatINR(a.amount)}</td>
                  <td className="py-2 pr-3 text-right font-mono">{formatINR(a.recovered_amount)}</td>
                  <td className="py-2 pr-3 text-right font-mono font-semibold">{formatINR(a.outstanding)}</td>
                  <td className="py-2 pr-3">
                    <span className={`status-chip ${a.status === "open" ? "chip-sent" : a.status === "closed" ? "chip-paid" : "chip-draft"}`}>
                      {a.status === "open" ? "Outstanding" : a.status === "closed" ? "Recovered" : "Cancelled"}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    {canWrite && a.status === "open" && !(a.recovered_amount > 0) && (
                      <button type="button" className="btn-ghost text-xs text-[var(--danger)]" onClick={() => cancel(a)}>Cancel</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
