import { useEffect, useState } from "react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import {
  Bank, TrendUp, TrendDown, Wallet, ChartLine, ArrowsClockwise,
  Plus, X, ArrowDown, ArrowUp, Coins, ListDashes, Money, Receipt,
  Scales, Waves, DownloadSimple,
} from "@phosphor-icons/react";

const CURRENCY = (n) => `₹${(Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const TABS = [
  { id: "dashboard", label: "Dashboard", Icon: ChartLine },
  { id: "income",    label: "Income",    Icon: ArrowDown },
  { id: "expense",   label: "Expense",   Icon: ArrowUp },
  { id: "coa",       label: "Chart of Accounts", Icon: ListDashes },
  { id: "reports",   label: "Reports",   Icon: Receipt },
  { id: "balance",   label: "Balance Sheet", Icon: Scales },
  { id: "cashflow",  label: "Cash Flow", Icon: Waves },
];

export default function Accounting() {
  const [tab, setTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [journal, setJournal] = useState([]);
  const [pl, setPL] = useState(null);
  const [tb, setTB] = useState(null);
  const [bs, setBS] = useState(null);
  const [cf, setCF] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [meta, setMeta] = useState(null);

  const loadCommon = async () => {
    const [a, c, p, m, v] = await Promise.all([
      api.get("/accounts"),
      api.get("/clients"),
      api.get("/projects"),
      api.get("/accounting/meta"),
      api.get("/vendors").catch(() => ({ data: [] })),
    ]);
    setAccounts(a.data); setClients(c.data); setProjects(p.data); setMeta(m.data); setVendors(v.data);
  };
  const loadDashboard = async () => (setDashboard((await api.get("/accounting/dashboard")).data));
  const loadJournal = async () => (setJournal((await api.get("/journal-entries")).data));
  const loadReports = async () => {
    const [p, t] = await Promise.all([
      api.get("/accounting/reports/pl"),
      api.get("/accounting/reports/trial-balance"),
    ]);
    setPL(p.data); setTB(t.data);
  };

  useEffect(() => { loadCommon(); loadDashboard(); loadJournal(); }, []);
  useEffect(() => { if (tab === "reports") loadReports(); }, [tab]);
  useEffect(() => {
    if (tab === "balance")  api.get("/accounting/reports/balance-sheet").then(({ data }) => setBS(data));
    if (tab === "cashflow") api.get("/accounting/reports/cash-flow").then(({ data }) => setCF(data));
  }, [tab]);

  // CSV download helper — hits an auth-cookied endpoint via fetch (blob) → save.
  const downloadCsv = async (url, filename) => {
    const base = process.env.REACT_APP_BACKEND_URL;
    const res = await fetch(`${base}/api${url}`, { credentials: "include" });
    if (!res.ok) return;
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const banks = accounts.filter((a) => a.is_bank || ["Cash", "Petty Cash"].includes(a.name));
  const incomeAccs = accounts.filter((a) => a.type === "income");
  const expenseAccs = accounts.filter((a) => a.type === "expense");

  return (
    <div className="space-y-6" data-testid="accounting-page">
      <PageHero
        eyebrow="FINANCE / ACCOUNTING"
        title="Every rupee, in its place."
        kicker="Double-entry bookkeeping wired into projects, clients, and payroll."
      >
        <button onClick={() => { setShowForm({ kind: "income" }); setTab("income"); }}
          className="btn-primary bg-[#1D633E]" data-testid="quick-income-btn">
          <ArrowDown size={14} /> Record income
        </button>
        <button onClick={() => { setShowForm({ kind: "expense" }); setTab("expense"); }}
          className="btn-primary bg-[#B4001C]" data-testid="quick-expense-btn">
          <ArrowUp size={14} /> Record expense
        </button>
      </PageHero>

      <div className="flex items-center gap-1 border-b border-[#E5E5E5]">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} onClick={() => setTab(id)} data-testid={`tab-${id}`}
            className={`px-4 py-2.5 text-sm border-b-2 -mb-px flex items-center gap-2 transition ${tab === id
              ? "border-[#002FA7] text-[#002FA7] font-semibold"
              : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"}`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {tab === "dashboard" && dashboard && (
        <Dashboard d={dashboard} onRefresh={loadDashboard} />
      )}

      {tab === "income" && (
        <TxnList
          kind="income" showForm={showForm} setShowForm={setShowForm}
          accounts={accounts} banks={banks} txnAccs={incomeAccs}
          clients={clients} projects={projects}
          journal={journal.filter((j) => j.source === "income")}
          onSubmit={async (payload) => {
            await api.post("/accounting/income", payload);
            setShowForm(false); loadJournal(); loadDashboard();
          }}
        />
      )}

      {tab === "expense" && (
        <TxnList
          kind="expense" showForm={showForm} setShowForm={setShowForm}
          accounts={accounts} banks={banks} txnAccs={expenseAccs}
          clients={clients} projects={projects} vendors={vendors}
          journal={journal.filter((j) => j.source === "expense")}
          onSubmit={async (payload) => {
            await api.post("/accounting/expense", payload);
            setShowForm(false); loadJournal(); loadDashboard();
          }}
        />
      )}

      {tab === "coa" && (
        <ChartOfAccounts accounts={accounts} onReload={loadCommon} meta={meta} />
      )}

      {tab === "reports" && (
        <Reports pl={pl} tb={tb} onReload={loadReports} onDownload={downloadCsv} />
      )}

      {tab === "balance" && (
        <BalanceSheetView bs={bs} onDownload={downloadCsv} />
      )}

      {tab === "cashflow" && (
        <CashFlowView cf={cf} onDownload={downloadCsv} />
      )}
    </div>
  );
}

// ================================================================
function BalanceSheetView({ bs, onDownload }) {
  if (!bs) return <div className="overline">LOADING BALANCE SHEET…</div>;
  const Section = ({ title, rows, total, extraRow }) => (
    <div className="card-flat">
      <div className="overline mb-3">{title}</div>
      <table className="w-full text-sm">
        <tbody>
          {rows.length === 0 && <tr><td className="text-[#9A9A9A] py-2">No entries.</td></tr>}
          {rows.map((r) => (
            <tr key={r.account_id} className="border-b border-[#F5F5F5]">
              <td className="py-1.5">{r.name}</td>
              <td className="py-1.5 text-right font-mono">{CURRENCY(r.balance)}</td>
            </tr>
          ))}
          {extraRow}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-[#0A0A0A]">
            <td className="py-2 overline">TOTAL</td>
            <td className="py-2 text-right font-mono font-bold text-lg">{CURRENCY(total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
  return (
    <div className="space-y-4" data-testid="balance-sheet-tab">
      <div className="flex items-center justify-between">
        <div className="overline">AS OF {bs.as_of || "TODAY"} · {bs.balanced ? "BALANCED ✓" : "MISMATCH"}</div>
        <button className="btn-ghost text-xs" onClick={() => onDownload("/accounting/reports/balance-sheet.csv", "balance-sheet.csv")} data-testid="dl-bs-csv">
          <DownloadSimple size={12} /> CSV
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Section title="Assets" rows={bs.assets.rows} total={bs.assets.total} />
        <div className="space-y-4">
          <Section title="Liabilities" rows={bs.liabilities.rows} total={bs.liabilities.total} />
          <Section
            title="Equity"
            rows={bs.equity.rows}
            total={bs.equity.total_with_net_income}
            extraRow={
              <tr className="border-b border-[#F5F5F5] italic text-[#5C5C5C]">
                <td className="py-1.5">Net Income (period)</td>
                <td className="py-1.5 text-right font-mono">{CURRENCY(bs.equity.net_income)}</td>
              </tr>
            }
          />
        </div>
      </div>
      <div className={`p-4 border text-sm ${bs.balanced ? "border-[#1D633E] bg-[#EFF7EF] text-[#1D633E]" : "border-[#B22B22] bg-[#FCEEEC] text-[#B22B22]"}`}>
        <span className="overline">RECONCILIATION</span> · Assets {CURRENCY(bs.total_assets)} = Liabilities + Equity {CURRENCY(bs.total_liabilities_and_equity)}
      </div>
    </div>
  );
}

// ================================================================
function CashFlowView({ cf, onDownload }) {
  if (!cf) return <div className="overline">LOADING CASH FLOW…</div>;
  const Row = ({ label, value, tint }) => (
    <div className="flex justify-between border-b border-[#F5F5F5] py-1.5 text-sm">
      <span className="text-[#5C5C5C] capitalize">{label.replace(/_/g, " ")}</span>
      <span className={`font-mono ${tint || ""}`}>{CURRENCY(value)}</span>
    </div>
  );
  return (
    <div className="space-y-4" data-testid="cashflow-tab">
      <div className="flex items-center justify-between">
        <div className="overline">
          {cf.from ? `${cf.from} → ${cf.to || "today"}` : "ALL TIME"}
        </div>
        <button className="btn-ghost text-xs" onClick={() => onDownload("/accounting/reports/cash-flow.csv", "cash-flow.csv")} data-testid="dl-cf-csv">
          <DownloadSimple size={12} /> CSV
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <KPI label="Opening balance" value={CURRENCY(cf.opening_balance)} Icon={Wallet} tint="#5C5C5C" />
        <KPI label="Inflows" value={CURRENCY(cf.total_inflow)} Icon={TrendUp} tint="#1D633E" />
        <KPI label="Outflows" value={CURRENCY(cf.total_outflow)} Icon={TrendDown} tint="#B4001C" />
        <KPI label="Closing balance" value={CURRENCY(cf.closing_balance)} Icon={Wallet} tint={cf.closing_balance >= 0 ? "#002FA7" : "#B4001C"} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card-flat">
          <div className="overline mb-3">INFLOWS</div>
          {Object.entries(cf.inflows).map(([k, v]) => (
            <Row key={k} label={k} value={v} tint="text-[#1D633E]" />
          ))}
          <div className="flex justify-between pt-3 mt-2 border-t-2 border-[#0A0A0A]">
            <span className="overline">TOTAL</span>
            <span className="font-mono font-bold">{CURRENCY(cf.total_inflow)}</span>
          </div>
        </div>
        <div className="card-flat">
          <div className="overline mb-3">OUTFLOWS</div>
          {Object.entries(cf.outflows).map(([k, v]) => (
            <Row key={k} label={k} value={v} tint="text-[#B4001C]" />
          ))}
          <div className="flex justify-between pt-3 mt-2 border-t-2 border-[#0A0A0A]">
            <span className="overline">TOTAL</span>
            <span className="font-mono font-bold">{CURRENCY(cf.total_outflow)}</span>
          </div>
        </div>
      </div>

      <div className={`p-4 border text-sm ${cf.net_change >= 0 ? "border-[#1D633E] bg-[#EFF7EF] text-[#1D633E]" : "border-[#B4001C] bg-[#FCEEEC] text-[#B4001C]"}`}>
        <span className="overline">NET CHANGE FOR PERIOD</span>
        <span className="ml-3 font-mono font-bold text-lg">{CURRENCY(cf.net_change)}</span>
      </div>
    </div>
  );
}

// ================================================================
function Dashboard({ d, onRefresh }) {
  const k = d.kpis;
  return (
    <div className="space-y-6" data-testid="dashboard-tab">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPI label="Cash & Bank" value={CURRENCY(k.cash_bank)} Icon={Wallet} tint="#002FA7" testid="kpi-cash" />
        <KPI label="This month P&L" value={CURRENCY(k.profit_month)} Icon={ChartLine} tint={k.profit_month >= 0 ? "#1D633E" : "#B4001C"} testid="kpi-profit" />
        <KPI label="Outstanding" value={CURRENCY(k.outstanding)} Icon={TrendDown} tint="#F0A93A" testid="kpi-outstanding" />
        <KPI label="Overdue" value={CURRENCY(k.overdue)} Icon={TrendDown} tint="#B4001C" testid="kpi-overdue" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SubKPI label="Income (month)" value={CURRENCY(k.income_month)} tint="#1D633E" />
        <SubKPI label="Expense (month)" value={CURRENCY(k.expense_month)} tint="#B4001C" />
        <SubKPI label="Salary (month)" value={CURRENCY(k.salary_month)} tint="#8A6DFF" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-flat">
          <div className="flex items-center justify-between mb-3">
            <div className="overline">CASH & BANK ACCOUNTS</div>
            <button onClick={onRefresh} className="btn-ghost text-xs"><ArrowsClockwise size={12} /> Refresh</button>
          </div>
          {k.cash_bank_by_account.map((b) => (
            <div key={b.account_id} className="flex items-center justify-between border-b border-[#F0F0F0] py-2 text-sm" data-testid={`bank-${b.account_id}`}>
              <div className="flex items-center gap-2"><Bank size={14} className="text-[#002FA7]" />{b.name}</div>
              <span className="font-mono font-semibold">{CURRENCY(b.balance)}</span>
            </div>
          ))}
        </div>

        <div className="card-flat">
          <div className="overline mb-3">UPCOMING PAYMENTS · next 30d</div>
          {d.upcoming_payments.length === 0 && <div className="text-center py-6 text-sm text-[#9A9A9A]">All clear.</div>}
          {d.upcoming_payments.slice(0, 8).map((m) => (
            <div key={m.id} className="flex items-center justify-between border-b border-[#F0F0F0] py-2 text-sm">
              <div>
                <div className="font-semibold">{m.name}</div>
                <div className="text-xs font-mono text-[#5C5C5C]">DUE · {m.due_date || "—"}</div>
              </div>
              <span className="font-mono font-semibold">{CURRENCY(m.amount)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card-flat">
        <div className="overline mb-3">RECENT TRANSACTIONS</div>
        <table className="w-full text-sm">
          <thead className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Narration</th><th className="p-2 text-left">Source</th><th className="p-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            {d.recent_transactions.map((t) => (
              <tr key={t.id} className="border-t border-[#F0F0F0]" data-testid={`recent-${t.id}`}>
                <td className="p-2 font-mono text-xs">{t.date}</td>
                <td className="p-2">{t.narration}</td>
                <td className="p-2 text-xs uppercase">{t.source}</td>
                <td className="p-2 text-right font-mono font-semibold">{CURRENCY(t.total)}</td>
              </tr>
            ))}
            {d.recent_transactions.length === 0 && <tr><td colSpan={4} className="p-8 text-center text-[#9A9A9A]">No transactions yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function KPI({ label, value, Icon, tint, testid }) {
  return (
    <div className="card-flat" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="overline">{label}</div>
        <Icon size={16} style={{ color: tint }} />
      </div>
      <div className="font-display font-bold text-3xl mt-2 tracking-tight" style={{ color: tint }}>{value}</div>
    </div>
  );
}

function SubKPI({ label, value, tint }) {
  return (
    <div className="card-flat">
      <div className="overline">{label}</div>
      <div className="font-display font-bold text-2xl mt-1" style={{ color: tint }}>{value}</div>
    </div>
  );
}

// ================================================================
function TxnList({ kind, showForm, setShowForm, accounts, banks, txnAccs, clients, projects, vendors, journal, onSubmit }) {
  const [form, setForm] = useState(() => ({
    date: new Date().toISOString().slice(0, 10), amount: "",
    ...(kind === "income" ? { income_account_id: "", bank_account_id: "", client_id: "", project_id: "" }
                          : { expense_account_id: "", paid_from_account_id: "", vendor_id: "", project_id: "", gst: "" }),
    payment_method: "bank_transfer", reference: "", notes: "",
  }));

  useEffect(() => {
    if (banks.length && !form.bank_account_id && !form.paid_from_account_id) {
      if (kind === "income") setForm((s) => ({ ...s, bank_account_id: banks[0].id }));
      else setForm((s) => ({ ...s, paid_from_account_id: banks[0].id }));
    }
    if (txnAccs.length) {
      const key = kind === "income" ? "income_account_id" : "expense_account_id";
      if (!form[key]) setForm((s) => ({ ...s, [key]: txnAccs[0].id }));
    }
  }, [banks, txnAccs]);

  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form, amount: Number(form.amount) };
    if (kind === "expense" && form.gst) payload.gst = Number(form.gst);
    Object.keys(payload).forEach((k) => { if (payload[k] === "" || payload[k] === null) delete payload[k]; });
    await onSubmit(payload);
  };

  return (
    <div className="space-y-4" data-testid={`${kind}-tab`}>
      <div className="flex justify-end">
        <button onClick={() => setShowForm(showForm && showForm.kind === kind ? false : { kind })}
          className={`btn-primary ${kind === "income" ? "bg-[#1D633E]" : "bg-[#B4001C]"}`} data-testid={`${kind}-new-btn`}>
          <Plus size={14} /> {showForm && showForm.kind === kind ? "Cancel" : `New ${kind}`}
        </button>
      </div>

      {showForm && showForm.kind === kind && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3" data-testid={`${kind}-form`}>
          <input type="date" required className="input-flat" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <input type="number" required step="0.01" className="input-flat" placeholder="Amount"
            value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid={`${kind}-amount`} />
          <select className="input-flat" value={kind === "income" ? form.income_account_id : form.expense_account_id}
            onChange={(e) => setForm({ ...form, [kind === "income" ? "income_account_id" : "expense_account_id"]: e.target.value })}
            data-testid={`${kind}-acc`}>
            <option value="" disabled>Select {kind} account</option>
            {txnAccs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <select className="input-flat" value={kind === "income" ? form.bank_account_id : form.paid_from_account_id}
            onChange={(e) => setForm({ ...form, [kind === "income" ? "bank_account_id" : "paid_from_account_id"]: e.target.value })}
            data-testid={`${kind}-bank`}>
            <option value="" disabled>Cash / Bank</option>
            {banks.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>

          {kind === "income" && (
            <>
              <select className="input-flat" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
                <option value="">— Client (optional) —</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">— Project (optional) —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </>
          )}

          {kind === "expense" && (
            <>
              <select
                data-testid="expense-vendor-select"
                className="input-flat"
                value={form.vendor_id || ""}
                onChange={(e) => setForm({ ...form, vendor_id: e.target.value })}
              >
                <option value="">— Vendor (optional) —</option>
                {vendors.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}{v.company ? ` · ${v.company}` : ""}
                  </option>
                ))}
              </select>
              <select className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">— Project (optional) —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <input type="number" step="0.01" className="input-flat" placeholder="GST amount (optional)" value={form.gst || ""} onChange={(e) => setForm({ ...form, gst: e.target.value })} />
            </>
          )}

          <select className="input-flat" value={form.payment_method} onChange={(e) => setForm({ ...form, payment_method: e.target.value })}>
            {["cash", "bank_transfer", "upi", "cheque", "credit_card", "online", "other"].map((m) => <option key={m}>{m}</option>)}
          </select>
          <input className="input-flat" placeholder="Reference no." value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
          <input className="input-flat md:col-span-3" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <button className="btn-primary md:col-span-3" data-testid={`${kind}-submit`}>Save {kind}</button>
        </form>
      )}

      <div className="border border-[#E5E5E5] overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Narration</th><th className="p-2 text-left">Account</th><th className="p-2 text-left">Reference</th><th className="p-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            {journal.map((j) => {
              const primary = j.lines?.find((l) => l.account_type === (kind === "income" ? "income" : "expense"));
              return (
                <tr key={j.id} className="border-t border-[#F0F0F0]" data-testid={`${kind}-row-${j.id}`}>
                  <td className="p-2 font-mono text-xs">{j.date}</td>
                  <td className="p-2">{j.narration}</td>
                  <td className="p-2 text-xs">{primary?.account_name || "—"}</td>
                  <td className="p-2 font-mono text-xs">{j.reference || "—"}</td>
                  <td className={`p-2 text-right font-mono font-semibold ${kind === "income" ? "text-[#1D633E]" : "text-[#B4001C]"}`}>
                    {CURRENCY(j.total)}
                  </td>
                </tr>
              );
            })}
            {journal.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-[#9A9A9A]">No {kind} entries yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ================================================================
function ChartOfAccounts({ accounts, onReload, meta }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", type: "expense", code: "", is_bank: false, opening_balance: "" });
  const grouped = accounts.reduce((acc, a) => {
    (acc[a.type] = acc[a.type] || []).push(a); return acc;
  }, {});
  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form, opening_balance: Number(form.opening_balance) || 0 };
    await api.post("/accounts", payload);
    setForm({ name: "", type: "expense", code: "", is_bank: false, opening_balance: "" });
    setShowForm(false); onReload();
  };
  return (
    <div className="space-y-4" data-testid="coa-tab">
      <div className="flex justify-end">
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-account-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New account"}
        </button>
      </div>
      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-5 gap-3" data-testid="account-form">
          <input required className="input-flat md:col-span-2" placeholder="Account name" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="account-name" />
          <select className="input-flat" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {(meta?.account_types || []).map((t) => <option key={t}>{t}</option>)}
          </select>
          <input className="input-flat" placeholder="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          <input type="number" className="input-flat" placeholder="Opening balance" value={form.opening_balance}
            onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} />
          <label className="text-xs col-span-full flex items-center gap-2">
            <input type="checkbox" checked={form.is_bank} onChange={(e) => setForm({ ...form, is_bank: e.target.checked })} />
            Mark as bank / cash account
          </label>
          <button className="btn-primary md:col-span-5" data-testid="account-submit">Create account</button>
        </form>
      )}
      {Object.entries(grouped).map(([type, list]) => (
        <div key={type} className="card-flat" data-testid={`coa-group-${type}`}>
          <div className="overline mb-2">{type.toUpperCase()} · {list.length}</div>
          <table className="w-full text-sm">
            <tbody>
              {list.map((a) => (
                <tr key={a.id} className="border-b border-[#F0F0F0]" data-testid={`account-${a.id}`}>
                  <td className="p-2 font-mono text-xs w-20">{a.code || "—"}</td>
                  <td className="p-2 font-semibold">{a.name}</td>
                  <td className="p-2 text-right font-mono text-xs text-[#5C5C5C]">{CURRENCY(a.opening_balance)}</td>
                  <td className="p-2 text-right">{a.is_bank && <Bank size={12} className="text-[#002FA7] ml-auto" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

// ================================================================
function Reports({ pl, tb, onReload, onDownload }) {
  if (!pl || !tb) return <div className="text-center py-16 overline">LOADING…</div>;
  return (
    <div className="space-y-6" data-testid="reports-tab">
      <div className="flex justify-between items-center">
        <div className="overline">FINANCIAL REPORTS</div>
        <div className="flex items-center gap-2">
          <button onClick={() => onDownload("/accounting/reports/pl.csv", "profit-loss.csv")} className="btn-ghost text-xs" data-testid="dl-pl-csv">
            <DownloadSimple size={12} /> P&amp;L
          </button>
          <button onClick={() => onDownload("/accounting/reports/trial-balance.csv", "trial-balance.csv")} className="btn-ghost text-xs" data-testid="dl-tb-csv">
            <DownloadSimple size={12} /> Trial balance
          </button>
          <button onClick={() => onDownload("/journal-entries.csv", "journal.csv")} className="btn-ghost text-xs" data-testid="dl-journal-csv">
            <DownloadSimple size={12} /> Journal
          </button>
          <button onClick={onReload} className="btn-ghost text-xs" data-testid="reports-refresh"><ArrowsClockwise size={12} /> Refresh</button>
        </div>
      </div>

      <div className="card-flat" data-testid="pl-report">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="overline">PROFIT &amp; LOSS</div>
            <div className="text-xs text-[#5C5C5C] mt-0.5">All time</div>
          </div>
          <div className="text-right">
            <div className="overline">NET</div>
            <div className={`font-display font-bold text-3xl ${pl.net_profit >= 0 ? "text-[#1D633E]" : "text-[#B4001C]"}`}>
              {CURRENCY(pl.net_profit)}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ReportBlock title="INCOME" rows={pl.income} total={pl.total_income} tint="#1D633E" testid="pl-income" />
          <ReportBlock title="EXPENSE" rows={pl.expense} total={pl.total_expense} tint="#B4001C" testid="pl-expense" />
        </div>
      </div>

      <div className="card-flat" data-testid="tb-report">
        <div className="flex items-center justify-between mb-4">
          <div className="overline">TRIAL BALANCE</div>
          <div className="text-xs font-mono">
            DR {CURRENCY(tb.total_debit)} · CR {CURRENCY(tb.total_credit)}
          </div>
        </div>
        <table className="w-full text-sm">
          <thead className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr><th className="p-2 text-left">Account</th><th className="p-2 text-left">Type</th><th className="p-2 text-right">Debit</th><th className="p-2 text-right">Credit</th><th className="p-2 text-right">Balance</th></tr>
          </thead>
          <tbody>
            {tb.rows.map((r) => (
              <tr key={r.account_id} className="border-t border-[#F0F0F0]">
                <td className="p-2">{r.account_name}</td>
                <td className="p-2 text-xs uppercase text-[#5C5C5C]">{r.account_type}</td>
                <td className="p-2 text-right font-mono">{CURRENCY(r.debit)}</td>
                <td className="p-2 text-right font-mono">{CURRENCY(r.credit)}</td>
                <td className="p-2 text-right font-mono font-semibold">{CURRENCY(r.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReportBlock({ title, rows, total, tint, testid }) {
  return (
    <div data-testid={testid}>
      <div className="overline mb-2" style={{ color: tint }}>{title}</div>
      {rows.length === 0 && <div className="text-xs text-[#9A9A9A]">No entries.</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center justify-between text-sm border-b border-[#F0F0F0] py-1.5">
          <span>{r.name}</span>
          <span className="font-mono">{CURRENCY(r.amount)}</span>
        </div>
      ))}
      <div className="flex items-center justify-between text-sm font-semibold pt-2 mt-2 border-t-2 border-[#0A0A0A]">
        <span>TOTAL</span>
        <span className="font-mono" style={{ color: tint }}>{CURRENCY(total)}</span>
      </div>
    </div>
  );
}
