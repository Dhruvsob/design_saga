import { useEffect, useState } from "react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import { Daybook } from "../components/Daybook";
import { AccountLedgerPanel } from "../components/AccountLedgerPanel";
import { TransactionDetail } from "../components/TransactionDetail";
import { RecurringExpenses, BankReconciliation, FavoriteAccountsStrip } from "../components/FinanceExtras";
import { toast } from "sonner";
import { formatDate } from "../lib/format";
import {
  Bank, TrendUp, TrendDown, Wallet, ChartLine, ArrowsClockwise,
  Plus, X, ArrowDown, ArrowUp, Coins, ListDashes, Money, Receipt,
  Scales, Waves, DownloadSimple, Notebook, CaretRight, Repeat, Star,
  HandCoins, ArrowsLeftRight, PencilSimple, Archive, ArrowCounterClockwise, WarningCircle,
} from "@phosphor-icons/react";

const CURRENCY = (n) => `₹${(Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const TABS = [
  { id: "dashboard", label: "Dashboard", Icon: ChartLine },
  { id: "income",    label: "Income",    Icon: ArrowDown },
  { id: "expense",   label: "Expense",   Icon: ArrowUp },
  { id: "receivables", label: "Collections Due", Icon: Money },
  { id: "daybook",   label: "Daybook",   Icon: Notebook },
  { id: "coa",       label: "Chart of Accounts", Icon: ListDashes },
  { id: "ledgers",   label: "Ledgers",   Icon: Bank },
  { id: "reports",   label: "Reports",   Icon: Receipt },
  { id: "balance",   label: "Balance Sheet", Icon: Scales },
  { id: "cashflow",  label: "Cash Flow", Icon: Waves },
  { id: "commissions", label: "Commissions", Icon: Coins },
  { id: "recurring", label: "Recurring", Icon: Repeat },
  { id: "bank",      label: "Bank Reconciliation", Icon: Bank },
  { id: "validation", label: "Validation", Icon: ArrowsClockwise },
];

export default function Accounting() {
  const [tab, setTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [journal, setJournal] = useState([]);
  const [journalPage, setJournalPage] = useState({ total: 0, limit: 100, offset: 0 });
  const [pl, setPL] = useState(null);
  const [tb, setTB] = useState(null);
  const [bs, setBS] = useState(null);
  const [cf, setCF] = useState(null);
  const [commissions, setCommissions] = useState(null);
  const [validation, setValidation] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [showWithdrawal, setShowWithdrawal] = useState(false);
  const [showTransfers, setShowTransfers] = useState(false);
  const [meta, setMeta] = useState(null);
  const [ledgerAccount, setLedgerAccount] = useState(null);
  // Financial period: fy label OR explicit from/to date range
  const [fyOptions, setFyOptions] = useState([]);
  const [fy, setFy] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const loadCommon = async () => {
    const [a, c, p, m, v, e, f] = await Promise.all([
      api.get("/accounts"),
      api.get("/clients"),
      api.get("/projects"),
      api.get("/accounting/meta"),
      api.get("/vendors").catch(() => ({ data: [] })),
      api.get("/employees").catch(() => ({ data: [] })),
      api.get("/accounting/fy/list").catch(() => ({ data: { current: "", choices: [] } })),
    ]);
    setAccounts(a.data); setClients(c.data); setProjects(p.data); setMeta(m.data);
    setVendors(v.data); setEmployees(e.data);
    setFyOptions(f.data?.choices || []);
    if (!fy && f.data?.current) setFy(f.data.current);
  };
  const periodQs = () => {
    const p = new URLSearchParams();
    if (fromDate || toDate) {
      if (fromDate) p.set("from_date", fromDate);
      if (toDate)   p.set("to_date", toDate);
    } else if (fy) {
      p.set("fy", fy);
    }
    return p.toString() ? `?${p.toString()}` : "";
  };
  const loadDashboard = async () => (setDashboard((await api.get("/accounting/dashboard")).data));
  const loadJournal = async (kind = tab, offset = 0) => {
    if (!["income", "expense"].includes(kind)) return;
    const p = new URLSearchParams(periodQs().replace(/^\?/, ""));
    p.set("source", kind);
    p.set("include_related", "true");
    p.set("limit", "100");
    p.set("offset", String(offset));
    const { data } = await api.get(`/journal-entries?${p.toString()}`);
    const items = Array.isArray(data) ? data : (data.items || []);
    setJournal(items);
    setJournalPage({
      total: Array.isArray(data) ? items.length : (data.total || 0),
      limit: Array.isArray(data) ? 100 : (data.limit || 100),
      offset: Array.isArray(data) ? 0 : (data.offset || 0),
    });
  };
  const loadReports = async () => {
    const qs = periodQs();
    const [p, t] = await Promise.all([
      api.get(`/accounting/reports/pl${qs}`),
      api.get(`/accounting/reports/trial-balance${qs}`),
    ]);
    setPL(p.data); setTB(t.data);
  };

  useEffect(() => { loadCommon(); loadDashboard(); }, []);
  useEffect(() => {
    if (["income", "expense"].includes(tab)) loadJournal(tab, 0);
  }, [tab, fy, fromDate, toDate]);
  useEffect(() => { if (tab === "reports") loadReports(); }, [tab, fy, fromDate, toDate]);
  useEffect(() => {
    const qs = periodQs();
    if (tab === "balance")  api.get(`/accounting/reports/balance-sheet${qs}`).then(({ data }) => setBS(data));
    if (tab === "cashflow") api.get(`/accounting/reports/cash-flow${qs}`).then(({ data }) => setCF(data));
    if (tab === "commissions") api.get("/commissions/dashboard").then(({ data }) => setCommissions(data));
    if (tab === "validation") api.get(`/accounting/dashboard/validation${qs}`).then(({ data }) => setValidation(data)).catch(() => setValidation({ error: "Admin only" }));
  }, [tab, fy, fromDate, toDate]);

  // CSV download helper — hits an auth-cookied endpoint via fetch (blob) → save.
  const downloadCsv = async (url, filename) => {
    const base = import.meta.env.VITE_BACKEND_URL || "";
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
        kicker="Double-entry bookkeeping wired into projects, clients, and payroll. For staff reimbursement claims, use the Expenses module."
      >
        <button onClick={() => { setShowForm({ kind: "income" }); setTab("income"); }}
          className="btn-primary bg-[#1D633E]" data-testid="quick-income-btn">
          <ArrowDown size={14} /> Record income
        </button>
        <button onClick={() => { setShowForm({ kind: "expense" }); setTab("expense"); }}
          className="btn-primary bg-[#B4001C]" data-testid="quick-expense-btn">
          <ArrowUp size={14} /> Record expense
        </button>
        <button onClick={() => setShowWithdrawal(true)}
          className="btn-ghost" data-testid="owner-withdrawal-btn">
          <HandCoins size={14} /> Owner withdrawal
        </button>
        <button onClick={() => setShowTransfers(true)}
          className="btn-ghost" data-testid="capital-transfers-btn">
          <ArrowsLeftRight size={14} /> Capital &amp; transfers
        </button>
      </PageHero>

      {showWithdrawal && (
        <OwnerWithdrawalForm
          accounts={accounts}
          banks={banks}
          onClose={() => setShowWithdrawal(false)}
          onSaved={() => { setShowWithdrawal(false); loadDashboard(); }}
        />
      )}

      {showTransfers && (
        <CapitalTransfersForm
          banks={banks}
          onClose={() => setShowTransfers(false)}
          onSaved={() => {
            setShowTransfers(false);
            loadCommon();
            loadDashboard();
          }}
        />
      )}

      <div className="flex items-center gap-1 border-b border-[#E5E5E5] overflow-x-auto no-scrollbar -mx-4 px-4 md:mx-0 md:px-0" data-testid="accounting-tabs">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} onClick={() => setTab(id)} data-testid={`tab-${id}`}
            className={`px-3 md:px-4 py-2.5 text-xs md:text-sm border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap transition ${tab === id
              ? "border-[#8B7F6A] text-[#8B7F6A] font-semibold"
              : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"}`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* Shared financial period selector. "All time" is sent explicitly. */}
      {["income", "expense", "reports", "balance", "cashflow", "ledgers", "validation"].includes(tab) && (
        <div className="flex items-center gap-3 flex-wrap text-xs" data-testid="fy-bar">
          <span className="overline">FINANCIAL PERIOD</span>
          <select
            value={fy}
            onChange={(e) => { setFy(e.target.value); setFromDate(""); setToDate(""); }}
            className="border border-[#E5E5E5] px-2 py-1 text-xs bg-white"
            data-testid="fy-select"
          >
            <option value="all">— All time —</option>
            {fyOptions.map((o) => (
              <option key={o.label} value={o.label}>{`FY ${o.label}${o.is_current ? " (current)" : ""}`}</option>
            ))}
          </select>
          <span className="text-[#9A9A9A]">or</span>
          <input
            type="date" value={fromDate}
            onChange={(e) => { setFromDate(e.target.value); setFy(""); }}
            className="border border-[#E5E5E5] px-2 py-1 text-xs"
            data-testid="from-date"
          />
          <span className="text-[#9A9A9A]">→</span>
          <input
            type="date" value={toDate}
            onChange={(e) => { setToDate(e.target.value); setFy(""); }}
            className="border border-[#E5E5E5] px-2 py-1 text-xs"
            data-testid="to-date"
          />
          {(fromDate || toDate || fy) && (
            <button
              className="btn-ghost text-xs"
              onClick={() => {
                setFy(fyOptions.find((o) => o.is_current)?.label || "");
                setFromDate(""); setToDate("");
              }}
              data-testid="clear-period"
            >Reset</button>
          )}
        </div>
      )}

      {tab === "dashboard" && (
        <>
          <FavoriteAccountsStrip onOpen={setLedgerAccount} />
          {dashboard && <Dashboard d={dashboard} onRefresh={loadDashboard} />}
        </>
      )}

      {tab === "income" && (
        <TxnList
          kind="income" showForm={showForm} setShowForm={setShowForm}
          accounts={accounts} banks={banks} txnAccs={incomeAccs}
          clients={clients} projects={projects} vendors={vendors} employees={employees}
          journal={journal} page={journalPage}
          onPage={(offset) => loadJournal("income", offset)}
          onSubmit={async (payload) => {
            await api.post("/accounting/income", payload);
            setShowForm(false); loadJournal("income", 0); loadDashboard();
          }}
        />
      )}

      {tab === "expense" && (
        <TxnList
          kind="expense" showForm={showForm} setShowForm={setShowForm}
          accounts={accounts} banks={banks} txnAccs={expenseAccs}
          clients={clients} projects={projects} vendors={vendors} employees={employees}
          journal={journal} page={journalPage}
          onPage={(offset) => loadJournal("expense", offset)}
          onSubmit={async (payload) => {
            await api.post("/accounting/expense", payload);
            setShowForm(false); loadJournal("expense", 0); loadDashboard();
          }}
        />
      )}

      {tab === "receivables" && (
        <CollectionsDue
          banks={banks}
          incomeAccounts={incomeAccs}
          onSaved={() => { loadDashboard(); loadCommon(); }}
        />
      )}

      {tab === "daybook" && (
        <Daybook
          accounts={accounts} clients={clients} vendors={vendors}
          projects={projects} employees={employees}
        />
      )}

      {tab === "coa" && (
        <ChartOfAccounts accounts={accounts} onReload={loadCommon} meta={meta} onOpenAccount={setLedgerAccount} />
      )}

      {tab === "reports" && (
        <Reports pl={pl} tb={tb} onReload={loadReports} onDownload={downloadCsv} periodQs={periodQs()} />
      )}

      {tab === "balance" && (
        <BalanceSheetView
          bs={bs}
          onDownload={downloadCsv}
          periodQs={periodQs()}
        />
      )}

      {tab === "cashflow" && (
        <CashFlowView cf={cf} onDownload={downloadCsv} periodQs={periodQs()} />
      )}

      {tab === "commissions" && (
        <CommissionsDashboard data={commissions} onDownload={downloadCsv} />
      )}

      {tab === "recurring" && (
        <RecurringExpenses accounts={accounts} vendors={vendors}
          projects={projects} clients={clients}
          onChanged={() => { loadDashboard(); }} />
      )}

      {tab === "bank" && (
        <BankReconciliation accounts={accounts} />
      )}

      {tab === "ledgers" && (
        <LedgersView
          clients={clients} vendors={vendors}
          employees={employees} projects={projects}
          fy={fy} fromDate={fromDate} toDate={toDate}
        />
      )}

      {tab === "validation" && (
        <ValidationReport data={validation} />
      )}

      {ledgerAccount && (
        <AccountLedgerPanel account={ledgerAccount} accounts={accounts}
          clients={clients} projects={projects} vendors={vendors}
          onClose={() => setLedgerAccount(null)} />
      )}
    </div>
  );
}

// ================================================================
function OwnerWithdrawalForm({ accounts, banks, onClose, onSaved }) {
  const drawings = accounts.find((a) => a.name?.trim().toLowerCase() === "owner drawings" && a.active !== false);
  const [form, setForm] = useState({
    date: new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
    amount: "",
    paid_from_account_id: banks[0]?.id || "",
    reference: "",
    narration: "Personal withdrawal by owner",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    const amount = Number(form.amount);
    if (!drawings) return setError("Owner Drawings account is unavailable. Open Chart of Accounts and refresh once.");
    if (!form.paid_from_account_id) return setError("Select the cash or bank account used.");
    if (!Number.isFinite(amount) || amount <= 0) return setError("Enter an amount greater than zero.");
    setBusy(true); setError("");
    try {
      await api.post("/accounting/non-operating", {
        kind: "owner_withdrawal",
        date: form.date,
        amount,
        bank_account_id: form.paid_from_account_id,
        reference: form.reference.trim() || null,
        notes: form.narration.trim() === "Personal withdrawal by owner" ? null : form.narration.trim(),
      });
      toast.success("Owner withdrawal recorded");
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not record the withdrawal.");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="border-y border-[#E5E5E5] py-4 space-y-3" data-testid="owner-withdrawal-form">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="overline">OWNER WITHDRAWAL</div>
          <div className="text-xs text-[#5C5C5C] mt-1">Debit Owner Drawings and credit the selected cash or bank account.</div>
        </div>
        <button type="button" className="btn-icon" onClick={onClose} aria-label="Close owner withdrawal form"><X size={14} /></button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        <label className="block"><span className="text-xs text-[#5C5C5C]">Date</span>
          <input required type="date" className="input-flat w-full mt-1" value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Amount</span>
          <input required type="number" min="0.01" step="0.01" className="input-flat w-full mt-1" value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="owner-withdrawal-amount" /></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Paid from</span>
          <select required className="input-flat w-full mt-1" value={form.paid_from_account_id}
            onChange={(e) => setForm({ ...form, paid_from_account_id: e.target.value })}>
            <option value="">Select cash or bank</option>
            {banks.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Reference</span>
          <input className="input-flat w-full mt-1" value={form.reference}
            onChange={(e) => setForm({ ...form, reference: e.target.value })} placeholder="Optional" /></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Narration</span>
          <input required className="input-flat w-full mt-1" value={form.narration}
            onChange={(e) => setForm({ ...form, narration: e.target.value })} /></label>
      </div>
      {error && <div className="text-xs text-[#B4001C]" role="alert">{error}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || !drawings} data-testid="owner-withdrawal-submit">
          <HandCoins size={14} /> {busy ? "Recording..." : "Record withdrawal"}
        </button>
      </div>
    </form>
  );
}

const TRANSFER_TYPES = [
  ["owner_investment", "Owner adds capital"],
  ["gold_purchase", "Buy gold investment"],
  ["money_given", "Give money to a person"],
  ["repayment_received", "Receive repayment from a person"],
  ["money_received", "Receive money from a person"],
  ["repayment_paid", "Repay money to a person"],
];

function CapitalTransfersForm({ banks, onClose, onSaved }) {
  const [form, setForm] = useState({
    kind: "owner_investment",
    date: new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
    amount: "",
    bank_account_id: banks[0]?.id || "",
    party_name: "",
    reference: "",
    notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const needsParty = ["money_given", "repayment_received", "money_received", "repayment_paid"].includes(form.kind);

  useEffect(() => {
    if (!form.bank_account_id && banks[0]?.id) {
      setForm((current) => ({ ...current, bank_account_id: banks[0].id }));
    }
  }, [banks, form.bank_account_id]);

  const submit = async (event) => {
    event.preventDefault();
    const amount = Number(form.amount);
    if (!form.bank_account_id) return setError("Select the cash or bank account used.");
    if (!Number.isFinite(amount) || amount <= 0) return setError("Enter an amount greater than zero.");
    if (needsParty && form.party_name.trim().length < 2) return setError("Enter the person or party name.");
    setBusy(true); setError("");
    try {
      await api.post("/accounting/non-operating", {
        ...form,
        amount,
        party_name: needsParty ? form.party_name.trim() : null,
        reference: form.reference.trim() || null,
        notes: form.notes.trim() || null,
      });
      toast.success("Transaction recorded in the correct ledgers");
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not record the transaction.");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="border-y border-[#E5E5E5] py-4 space-y-3" data-testid="capital-transfers-form">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="overline">CAPITAL, INVESTMENTS &amp; PARTY MONEY</div>
          <div className="text-xs text-[#5C5C5C] mt-1">Balance-sheet transactions that should not be recorded as income or expense.</div>
        </div>
        <button type="button" className="btn-icon" onClick={onClose} aria-label="Close capital and transfers form"><X size={14} /></button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="block"><span className="text-xs text-[#5C5C5C]">Transaction</span>
          <select className="input-flat w-full mt-1" value={form.kind}
            onChange={(event) => setForm({ ...form, kind: event.target.value })} data-testid="transfer-kind">
            {TRANSFER_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Date</span>
          <input required type="date" className="input-flat w-full mt-1" value={form.date}
            onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Amount</span>
          <input required type="number" min="0.01" step="0.01" className="input-flat w-full mt-1" value={form.amount}
            onChange={(event) => setForm({ ...form, amount: event.target.value })} data-testid="transfer-amount" /></label>
        <label className="block"><span className="text-xs text-[#5C5C5C]">Cash / Bank</span>
          <select required className="input-flat w-full mt-1" value={form.bank_account_id}
            onChange={(event) => setForm({ ...form, bank_account_id: event.target.value })}>
            <option value="">Select cash or bank</option>
            {banks.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select></label>
        {needsParty && <label className="block"><span className="text-xs text-[#5C5C5C]">Person / party</span>
          <input required className="input-flat w-full mt-1" value={form.party_name}
            onChange={(event) => setForm({ ...form, party_name: event.target.value })}
            placeholder="e.g. Ritesh Soni" data-testid="transfer-party" /></label>}
        <label className="block"><span className="text-xs text-[#5C5C5C]">Reference</span>
          <input className="input-flat w-full mt-1" value={form.reference}
            onChange={(event) => setForm({ ...form, reference: event.target.value })} placeholder="Optional" /></label>
        <label className="block md:col-span-3"><span className="text-xs text-[#5C5C5C]">Notes</span>
          <input className="input-flat w-full mt-1" value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Optional details" /></label>
      </div>
      {error && <div className="text-xs text-[#B4001C]" role="alert">{error}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy} data-testid="transfer-submit">
          <ArrowsLeftRight size={14} /> {busy ? "Recording..." : "Record transaction"}
        </button>
      </div>
    </form>
  );
}

// ================================================================
function CommissionsDashboard({ data, onDownload }) {
  if (!data) return <div className="overline">LOADING COMMISSIONS…</div>;
  const t = data.totals;
  return (
    <div className="space-y-4" data-testid="commissions-dashboard-tab">
      <div className="flex items-center justify-between">
        <div>
          <div className="overline">VENDOR COMMISSION INCOME</div>
          <div className="text-xs text-[#5C5C5C] mt-0.5">Earned = expected from vendor bills · Received = cash posted to income · Unallocated = receipt not matched to a bill</div>
        </div>
        <button className="btn-ghost text-xs" onClick={() => onDownload("/commissions/report.csv", "commissions.csv")} data-testid="dl-cm-csv">
          <DownloadSimple size={12} /> CSV
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KPI label="Total earned" value={CURRENCY(t.total_earned)} Icon={Coins} tint="#8B7F6A" />
        <KPI label="Received" value={CURRENCY(t.total_received)} Icon={TrendUp} tint="#1D633E" />
        <KPI label="Pending" value={CURRENCY(t.pending)} Icon={TrendDown} tint={t.pending > 0 ? "#B22B22" : "#5C5C5C"} />
        <KPI label="Unallocated" value={CURRENCY(t.unallocated_received)} Icon={WarningCircle} tint={t.unallocated_received > 0 ? "#7A4E1A" : "#5C5C5C"} />
        <KPI label="This month" value={CURRENCY(t.this_month)} Icon={ChartLine} tint="#7A4E1A" />
      </div>

      <div className="card-flat" data-testid="commissions-vendor-table">
        <div className="overline mb-3">BY VENDOR · EARNED / RECEIVED / PENDING</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase text-[#9A9A9A]">
              <tr>
                <th className="p-2 text-left">Vendor</th>
                <th className="p-2 text-right">Earned</th>
                <th className="p-2 text-right">Received</th>
                <th className="p-2 text-right">Pending</th>
              </tr>
            </thead>
            <tbody>
              {(data.top_vendors || []).map((v) => {
                const pending = Math.max(0, (v.earned || 0) - (v.received || 0));
                return (
                  <tr key={v.vendor_id} className="border-t border-[#F0F0F0] hover:bg-[#FAFAF7]">
                    <td className="p-2">
                      <a href={`/vendors/${v.vendor_id}`} className="font-semibold hover:text-[#8B7F6A]">{v.vendor_name}</a>
                    </td>
                    <td className="p-2 text-right font-mono">{CURRENCY(v.earned)}</td>
                    <td className="p-2 text-right font-mono text-[#1D633E]">{CURRENCY(v.received)}</td>
                    <td className={`p-2 text-right font-mono font-semibold ${pending > 0 ? "text-[#B22B22]" : "text-[#5C5C5C]"}`}>{CURRENCY(pending)}</td>
                  </tr>
                );
              })}
              {(data.top_vendors || []).length === 0 && (
                <tr><td colSpan={4} className="p-6 text-center text-[#9A9A9A]">No commission data yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card-flat">
        <div className="overline mb-3">BY PROJECT</div>
        {(data.by_project || []).length === 0 && <div className="text-sm text-[#9A9A9A]">No project-linked commission yet.</div>}
        {(data.by_project || []).slice(0, 10).map((p) => (
          <div key={p.project_id} className="flex justify-between items-center border-b border-[#F5F5F5] py-2 text-sm">
            <a href={`/projects/${p.project_id}`} className="font-semibold hover:text-[#8B7F6A]">{p.project_name}</a>
            <div className="flex gap-4 font-mono">
              <span className="text-[#5C5C5C]">Received: {CURRENCY(p.received)}</span>
              <span className="font-bold">Earned: {CURRENCY(p.earned)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ================================================================
function BalanceSheetView({ bs, onDownload, periodQs }) {
  if (!bs) return <div className="overline">LOADING BALANCE SHEET…</div>;
  const Section = ({ title, rows, total, extraRow }) => (
    <div className="card-flat">
      <div className="overline mb-3">{title}</div>
      <div className="overflow-x-auto"><table className="w-full text-sm">
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
      </table></div>
    </div>
  );
  return (
    <div className="space-y-4" data-testid="balance-sheet-tab">
      <div className="flex items-center justify-between">
        <div className="overline">AS OF {bs.as_of || "TODAY"} · {bs.balanced ? "BALANCED ✓" : "MISMATCH"}</div>
        <button className="btn-ghost text-xs" onClick={() => onDownload(`/accounting/reports/balance-sheet.csv${periodQs}`, "balance-sheet.csv")} data-testid="dl-bs-csv">
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
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <span className="overline">RECONCILIATION</span> · Assets {CURRENCY(bs.total_assets)} = Liabilities + Equity {CURRENCY(bs.total_liabilities_and_equity)}
            {!bs.balanced && (
              <span className="ml-2 font-mono" data-testid="bs-delta">
                · Δ {CURRENCY(bs.delta)}
              </span>
            )}
          </div>
        </div>
        {Array.isArray(bs.unbalanced_journal_entries) && bs.unbalanced_journal_entries.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer overline">
              {bs.unbalanced_journal_entries.length} UNBALANCED JOURNAL ENTRIES
            </summary>
            <div className="overflow-x-auto"><table className="w-full text-xs mt-2">
              <thead className="text-[#5C5C5C] border-b border-[#EEE]">
                <tr><th className="text-left py-1">Date</th><th className="text-left py-1">Narration</th><th className="text-right py-1">Δ</th></tr>
              </thead>
              <tbody>
                {bs.unbalanced_journal_entries.slice(0, 10).map((e) => (
                  <tr key={e.id} className="border-b border-[#F5F5F5]">
                    <td className="py-1">{formatDate(e.date)}</td>
                    <td className="py-1">{e.narration}</td>
                    <td className="py-1 text-right font-mono">{CURRENCY(e.diff)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </details>
        )}
      </div>
    </div>
  );
}

// ================================================================
function CashFlowView({ cf, onDownload, periodQs }) {
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
          {cf.from ? `${formatDate(cf.from)} to ${cf.to ? formatDate(cf.to) : "today"}` : "ALL TIME"}
        </div>
        <button className="btn-ghost text-xs" onClick={() => onDownload(`/accounting/reports/cash-flow.csv${periodQs}`, "cash-flow.csv")} data-testid="dl-cf-csv">
          <DownloadSimple size={12} /> CSV
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <KPI label="Opening balance" value={CURRENCY(cf.opening_balance)} Icon={Wallet} tint="#5C5C5C" />
        <KPI label="Inflows" value={CURRENCY(cf.total_inflow)} Icon={TrendUp} tint="#1D633E" />
        <KPI label="Outflows" value={CURRENCY(cf.total_outflow)} Icon={TrendDown} tint="#B4001C" />
        <KPI label="Closing balance" value={CURRENCY(cf.closing_balance)} Icon={Wallet} tint={cf.closing_balance >= 0 ? "#8B7F6A" : "#B4001C"} />
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

      {cf.activities && (
        <div className="border border-[#E5E5E5] bg-white overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
              <tr><th className="p-3 text-left overline">ACTIVITY</th><th className="p-3 text-left overline">DETAIL</th><th className="p-3 text-right overline">INFLOW</th><th className="p-3 text-right overline">OUTFLOW</th><th className="p-3 text-right overline">NET</th></tr>
            </thead>
            <tbody>
              {Object.entries(cf.activities).flatMap(([activity, detail]) => (
                detail.lines?.length ? detail.lines.map((line, index) => (
                  <tr key={`${activity}-${line.label}`} className="border-b border-[#F0F0F0]">
                    <td className="p-3 font-semibold capitalize">{index === 0 ? activity : ""}</td>
                    <td className="p-3 text-[#5C5C5C]">{line.label}</td>
                    <td className="p-3 text-right font-mono text-[#1D633E]">{line.inflow ? CURRENCY(line.inflow) : "-"}</td>
                    <td className="p-3 text-right font-mono text-[#B4001C]">{line.outflow ? CURRENCY(line.outflow) : "-"}</td>
                    <td className="p-3 text-right font-mono font-semibold">{CURRENCY(line.net)}</td>
                  </tr>
                )) : [
                  <tr key={`${activity}-empty`} className="border-b border-[#F0F0F0]">
                    <td className="p-3 font-semibold capitalize">{activity}</td><td className="p-3 text-[#9A9A9A]">No movement</td><td className="p-3" colSpan="3" />
                  </tr>,
                ]
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Array.isArray(cf.cash_accounts) && cf.cash_accounts.length > 0 && (
        <div className="border border-[#E5E5E5] bg-white overflow-x-auto">
          <div className="p-3 border-b border-[#E5E5E5] overline">CASH & BANK RECONCILIATION</div>
          <table className="w-full min-w-[620px] text-sm">
            <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]"><tr><th className="p-3 text-left overline">ACCOUNT</th><th className="p-3 text-right overline">OPENING</th><th className="p-3 text-right overline">INFLOW</th><th className="p-3 text-right overline">OUTFLOW</th><th className="p-3 text-right overline">CLOSING</th></tr></thead>
            <tbody>{cf.cash_accounts.map((account) => (
              <tr key={account.account_id} className="border-b border-[#F0F0F0]"><td className="p-3 font-semibold">{account.name}</td><td className="p-3 text-right font-mono">{CURRENCY(account.opening_balance)}</td><td className="p-3 text-right font-mono text-[#1D633E]">{CURRENCY(account.inflow)}</td><td className="p-3 text-right font-mono text-[#B4001C]">{CURRENCY(account.outflow)}</td><td className="p-3 text-right font-mono font-semibold">{CURRENCY(account.closing_balance)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}

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
        <KPI label="Cash & Bank" value={CURRENCY(k.cash_bank)} Icon={Wallet} tint="#8B7F6A" testid="kpi-cash" />
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
          {k.cash_bank_by_account.map((b, i) => (
            <div key={b.account_id ?? i} className="flex items-center justify-between border-b border-[#F0F0F0] py-2 text-sm" data-testid={`bank-${b.account_id}`}>
              <div className="flex items-center gap-2"><Bank size={14} className="text-[#8B7F6A]" />{b.name}</div>
              <span className="font-mono font-semibold">{CURRENCY(b.balance)}</span>
            </div>
          ))}
        </div>

        <div className="card-flat">
          <div className="overline mb-3">UPCOMING PAYMENTS · next 30d</div>
          {d.upcoming_payments.length === 0 && <div className="text-center py-6 text-sm text-[#9A9A9A]">All clear.</div>}
          {d.upcoming_payments.slice(0, 8).map((m, i) => (
            <div key={m.id ?? i} className="flex items-center justify-between border-b border-[#F0F0F0] py-2 text-sm">
              <div>
                <div className="font-semibold">{m.name}</div>
                <div className="text-xs font-mono text-[#5C5C5C]">DUE · {formatDate(m.due_date)}</div>
              </div>
              <span className="font-mono font-semibold">{CURRENCY(m.amount)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card-flat">
        <div className="overline mb-3">RECENT TRANSACTIONS</div>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Narration</th><th className="p-2 text-left">Source</th><th className="p-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            {d.recent_transactions.map((t, i) => (
              <tr key={t.id ?? i} className="border-t border-[#F0F0F0]" data-testid={`recent-${t.id}`}>
                <td className="p-2 font-mono text-xs">{formatDate(t.date)}</td>
                <td className="p-2">{t.narration}</td>
                <td className="p-2 text-xs uppercase">{t.source}</td>
                <td className="p-2 text-right font-mono font-semibold">{CURRENCY(t.total)}</td>
              </tr>
            ))}
            {d.recent_transactions.length === 0 && <tr><td colSpan={4} className="p-8 text-center text-[#9A9A9A]">No transactions yet.</td></tr>}
          </tbody>
        </table></div>
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

function CollectionsDue({ banks, incomeAccounts, onSaved }) {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [collecting, setCollecting] = useState(null);
  const [saving, setSaving] = useState(false);
  const [receipt, setReceipt] = useState({
    date: new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
    bank_account_id: "", income_account_id: "", payment_method: "bank_transfer",
    reference: "", notes: "",
  });

  const load = () => api.get("/accounting/receivables")
      .then(({ data: result }) => setData(result))
      .catch((error) => toast.error(error?.response?.data?.detail || "Could not load collections"));
  useEffect(() => { load(); }, []);

  const openReceipt = (row) => {
    setCollecting(row);
    setReceipt((current) => ({
      ...current,
      bank_account_id: current.bank_account_id || banks[0]?.id || "",
      income_account_id: current.income_account_id || incomeAccounts[0]?.id || "",
      notes: `Milestone collection · ${row.name || row.project_name}`,
    }));
  };

  const saveReceipt = async (event) => {
    event.preventDefault();
    if (!collecting || saving) return;
    setSaving(true);
    try {
      await api.post("/accounting/income", {
        ...receipt,
        amount: collecting.outstanding,
        milestone_id: collecting.id,
        project_id: collecting.project_id,
        client_id: collecting.client_id || undefined,
      });
      toast.success("Milestone receipt recorded");
      setCollecting(null);
      await load();
      onSaved?.();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not record receipt");
    } finally {
      setSaving(false);
    }
  };

  if (!data) return <div className="overline">LOADING COLLECTIONS…</div>;
  const term = query.trim().toLowerCase();
  const rows = (data.rows || []).filter((row) => {
    if (filter !== "all" && row.bucket !== filter) return false;
    if (!term) return true;
    return `${row.project_name || ""} ${row.client_name || ""} ${row.name || ""}`
      .toLowerCase().includes(term);
  });
  const filters = [
    ["all", "All pending"],
    ["overdue", "Overdue"],
    ["due_30", "Next 30 days"],
    ["later", "Later"],
    ["no_due_date", "No due date"],
  ];

  return (
    <div className="space-y-4" data-testid="collections-due-tab">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="overline">PROJECT COLLECTIONS</div>
          <div className="text-xs text-[#5C5C5C] mt-1">As of {formatDate(data.as_of)} · next 30 days through {formatDate(data.horizon)}</div>
        </div>
        <input
          className="input-flat min-w-[260px]"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search project, client or milestone"
          data-testid="collections-search"
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Total pending" value={CURRENCY(data.totals?.all)} Icon={Money} tint="#0A0A0A" />
        <KPI label="Overdue" value={CURRENCY(data.totals?.overdue)} Icon={ArrowUp} tint="#B4001C" />
        <KPI label="Next 30 days" value={CURRENCY(data.totals?.due_30)} Icon={ArrowDown} tint="#7A4E1A" />
        <KPI label="Later" value={CURRENCY(data.totals?.later)} Icon={ChartLine} tint="#1D633E" />
      </div>

      <div className="flex gap-1.5 flex-wrap" data-testid="collections-filters">
        {filters.map(([id, label]) => (
          <button key={id} onClick={() => setFilter(id)}
            className={`px-3 py-1.5 text-xs border ${filter === id ? "bg-[#0A0A0A] text-white border-[#0A0A0A]" : "bg-white text-[#5C5C5C] border-[#E5E5E5]"}`}
            data-testid={`collections-filter-${id}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="border border-[#E5E5E5] overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase text-[#5C5C5C]">
            <tr>
              <th className="p-3 text-left">Due date</th>
              <th className="p-3 text-left">Project</th>
              <th className="p-3 text-left">Client</th>
              <th className="p-3 text-left">Milestone</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-right">To collect</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-[#F0F0F0] hover:bg-[#FAFAF7]">
                <td className="p-3 font-mono text-xs whitespace-nowrap">
                  <div>{formatDate(row.due_date)}</div>
                  {row.days_overdue > 0 && <div className="text-[10px] text-[#B4001C]">{row.days_overdue} days overdue</div>}
                </td>
                <td className="p-3 font-semibold">{row.project_name}</td>
                <td className="p-3 text-[#5C5C5C]">{row.client_name || "—"}</td>
                <td className="p-3">{row.name || "Payment milestone"}</td>
                <td className="p-3"><span className={`status-chip chip-${row.status}`}>{row.status}</span></td>
                <td className="p-3 text-right font-mono font-semibold">{CURRENCY(row.outstanding)}</td>
                <td className="p-3 text-right whitespace-nowrap">
                  <button type="button" className="btn-primary text-xs mr-2"
                    onClick={() => openReceipt(row)} disabled={!banks.length || !incomeAccounts.length}>
                    <Money size={12} /> Receive
                  </button>
                  {row.project_id && <a href={`/projects/${row.project_id}`} className="btn-ghost text-xs">Open <CaretRight size={12} /></a>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={7} className="p-10 text-center text-[#9A9A9A]">No collections match this view.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {collecting && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <form onSubmit={saveReceipt} className="bg-white border border-[#E5E5E5] w-full max-w-lg p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="overline">RECORD MILESTONE RECEIPT</div>
                <h3 className="font-display text-xl mt-1">{collecting.name || "Payment milestone"}</h3>
                <p className="text-sm text-[#5C5C5C] mt-1">{collecting.project_name} · {CURRENCY(collecting.outstanding)}</p>
              </div>
              <button type="button" className="btn-ghost" onClick={() => setCollecting(null)} aria-label="Close"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-xs">Receipt date<input required type="date" className="input-flat mt-1 w-full" value={receipt.date} onChange={(e) => setReceipt({ ...receipt, date: e.target.value })} /></label>
              <label className="text-xs">Payment method<select className="input-flat mt-1 w-full" value={receipt.payment_method} onChange={(e) => setReceipt({ ...receipt, payment_method: e.target.value })}><option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option><option value="cash">Cash</option><option value="cheque">Cheque</option><option value="online">Online</option><option value="other">Other</option></select></label>
              <label className="text-xs">Received into<select required className="input-flat mt-1 w-full" value={receipt.bank_account_id} onChange={(e) => setReceipt({ ...receipt, bank_account_id: e.target.value })}><option value="" disabled>Select cash / bank</option>{banks.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
              <label className="text-xs">Income account<select required className="input-flat mt-1 w-full" value={receipt.income_account_id} onChange={(e) => setReceipt({ ...receipt, income_account_id: e.target.value })}><option value="" disabled>Select income account</option>{incomeAccounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
              <label className="text-xs sm:col-span-2">Reference<input className="input-flat mt-1 w-full" value={receipt.reference} onChange={(e) => setReceipt({ ...receipt, reference: e.target.value })} placeholder="Bank / UPI / cheque reference" /></label>
            </div>
            <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={() => setCollecting(null)}>Cancel</button><button type="submit" className="btn-primary" disabled={saving}>{saving ? "Recording…" : "Record receipt"}</button></div>
          </form>
        </div>
      )}
    </div>
  );
}

// ================================================================
function TxnList({ kind, showForm, setShowForm, accounts, banks, txnAccs, clients, projects, vendors, employees, journal, page, onPage, onSubmit }) {
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState(() => ({
    date: new Date().toISOString().slice(0, 10), amount: "",
    ...(kind === "income" ? { income_account_id: "", bank_account_id: "", client_id: "", project_id: "", vendor_id: "", employee_id: "" }
                          : { expense_account_id: "", paid_from_account_id: "", vendor_id: "", project_id: "", client_id: "", employee_id: "", gst: "" }),
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
              <select className="input-flat" value={form.vendor_id || ""} onChange={(e) => setForm({ ...form, vendor_id: e.target.value })} data-testid="income-vendor-select">
                <option value="">— Vendor (optional) —</option>
                {(vendors || []).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
              <select className="input-flat" value={form.employee_id || ""} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="income-employee-select">
                <option value="">— Employee (optional) —</option>
                {(employees || []).map((emp) => <option key={emp.id} value={emp.id}>{emp.name}{emp.employee_id ? ` · ${emp.employee_id}` : ""}</option>)}
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
              <select className="input-flat" value={form.client_id || ""} onChange={(e) => setForm({ ...form, client_id: e.target.value })} data-testid="expense-client-select">
                <option value="">— Client (optional) —</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select className="input-flat" value={form.employee_id || ""} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="expense-employee-select">
                <option value="">— Employee (optional) —</option>
                {(employees || []).map((emp) => <option key={emp.id} value={emp.id}>{emp.name}{emp.employee_id ? ` · ${emp.employee_id}` : ""}</option>)}
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
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[#FAFAFA] text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Narration</th><th className="p-2 text-left">Account</th><th className="p-2 text-left">Reference</th><th className="p-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            {journal.map((j) => {
              const primary = j.lines?.find((l) => l.account_type === (kind === "income" ? "income" : "expense"));
              return (
                <tr key={j.id} onClick={() => setDetail(j)}
                  className="border-t border-[#F0F0F0] cursor-pointer hover:bg-[#FAFAF7]"
                  data-testid={`${kind}-row-${j.id}`}>
                  <td className="p-2 font-mono text-xs">{formatDate(j.date)}</td>
                  <td className="p-2">
                    {j.narration}
                    {j.source?.endsWith("_reversal") && (
                      <span className="ml-2 text-[10px] text-[#8B7F6A]">{j.undone ? "REVERSAL UNDONE" : "REVERSAL"}</span>
                    )}
                    {j.source?.endsWith("_reinstatement") && (
                      <span className="ml-2 text-[10px] text-[#1D633E]">REINSTATED</span>
                    )}
                  </td>
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
        </table></div>
      </div>
      {page?.total > page?.limit && (
        <div className="flex items-center justify-between text-xs text-[#5C5C5C]">
          <span>
            {page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of {page.total}
          </span>
          <div className="flex gap-2">
            <button className="btn-ghost text-xs" disabled={page.offset === 0}
              onClick={() => onPage(Math.max(0, page.offset - page.limit))}>Previous</button>
            <button className="btn-ghost text-xs" disabled={page.offset + page.limit >= page.total}
              onClick={() => onPage(page.offset + page.limit)}>Next</button>
          </div>
        </div>
      )}
      {detail && (
        <TransactionDetail entry={detail} onClose={() => setDetail(null)}
          onChanged={() => onPage(page?.offset || 0)} />
      )}
    </div>
  );
}

// ================================================================
function ChartOfAccounts({ accounts: baseAccounts, onReload, meta, onOpenAccount }) {
  const [showForm, setShowForm] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [accounts, setAccounts] = useState(baseAccounts);
  const [form, setForm] = useState({ name: "", type: "expense", code: "", is_bank: false, opening_balance: "" });
  const [editing, setEditing] = useState(null);
  const [favIds, setFavIds] = useState([]);
  useEffect(() => { setAccounts(baseAccounts); }, [baseAccounts]);
  useEffect(() => {
    api.get("/favorite-accounts").then(({ data }) => setFavIds(data.account_ids || [])).catch(() => {});
  }, []);
  useEffect(() => {
    const params = new URLSearchParams({ include_balances: "true" });
    if (showInactive) params.set("include_inactive", "true");
    api.get(`/accounts?${params.toString()}`)
       .then(({ data }) => setAccounts(data))
       .catch(() => {});
  }, [showInactive]);
  const grouped = accounts.reduce((acc, a) => {
    (acc[a.type] = acc[a.type] || []).push(a); return acc;
  }, {});
  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form, opening_balance: Number(form.opening_balance) || 0 };
    if (!payload.code) delete payload.code;
    try {
      if (editing) {
        await api.patch(`/accounts/${editing.id}`, { ...payload, active: editing.active !== false });
        toast.success("Account updated");
      } else {
        await api.post("/accounts", payload);
        toast.success("Account created");
      }
      setForm({ name: "", type: "expense", code: "", is_bank: false, opening_balance: "" });
      setEditing(null); setShowForm(false); onReload();
      const params = new URLSearchParams({ include_balances: "true" });
      if (showInactive) params.set("include_inactive", "true");
      setAccounts((await api.get(`/accounts?${params.toString()}`)).data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save account");
    }
  };
  const startEdit = (account, event) => {
    event.stopPropagation();
    setEditing(account);
    setForm({
      name: account.name || "", type: account.type || "asset", code: account.code || "",
      is_bank: Boolean(account.is_bank), opening_balance: account.opening_balance || "",
    });
    setShowForm(true);
  };
  const toggleActive = async (account, event) => {
    event.stopPropagation();
    if (account.active !== false && !window.confirm(`Deactivate “${account.name}”? Its history will remain available.`)) return;
    try {
      if (account.active === false) {
        await api.patch(`/accounts/${account.id}`, {
          name: account.name, type: account.type, code: account.code || null,
          is_bank: Boolean(account.is_bank), opening_balance: Number(account.opening_balance) || 0,
          active: true, notes: account.notes || null,
        });
        toast.success("Account restored");
      } else {
        await api.delete(`/accounts/${account.id}`);
        toast.success("Account deactivated");
      }
      const params = new URLSearchParams({ include_balances: "true" });
      if (showInactive) params.set("include_inactive", "true");
      setAccounts((await api.get(`/accounts?${params.toString()}`)).data);
      onReload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not update account");
    }
  };
  const toggleFav = async (a, e) => {
    e.stopPropagation();
    try {
      if (favIds.includes(a.id)) {
        const { data } = await api.delete(`/favorite-accounts/${a.id}`);
        setFavIds(data.account_ids || []);
        toast.success("Unpinned");
      } else {
        const { data } = await api.post("/favorite-accounts", { account_id: a.id });
        setFavIds(data.account_ids || []);
        toast.success("Pinned to Favourites");
      }
    } catch (err) { toast.error("Could not update favourites"); }
  };
  return (
    <div className="space-y-4" data-testid="coa-tab">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <label className="flex items-center gap-2 text-xs text-[#5C5C5C]">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)}
            data-testid="coa-show-inactive" />
          Show inactive accounts
        </label>
        <button onClick={() => {
          setEditing(null);
          setForm({ name: "", type: "expense", code: "", is_bank: false, opening_balance: "" });
          setShowForm(!showForm);
        }} className="btn-primary" data-testid="new-account-btn">
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
          <input className="input-flat" placeholder="Code (auto if blank)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          <input type="number" className="input-flat" placeholder="Opening balance" value={form.opening_balance}
            onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} />
          <label className="text-xs col-span-full flex items-center gap-2">
            <input type="checkbox" checked={form.is_bank} onChange={(e) => setForm({ ...form, is_bank: e.target.checked })} />
            Mark as bank / cash account
          </label>
          <button className="btn-primary md:col-span-5" data-testid="account-submit">{editing ? "Save account" : "Create account"}</button>
        </form>
      )}
      {Object.entries(grouped).map(([type, list]) => (
        <div key={type} className="card-flat" data-testid={`coa-group-${type}`}>
          <div className="overline mb-2">{type.toUpperCase()} · {list.length}</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-[10px] font-mono uppercase text-[#9A9A9A]">
              <tr><th className="p-2" /><th className="p-2 text-left">Code</th><th className="p-2 text-left">Account</th><th className="p-2 text-right">Current balance</th><th className="p-2 text-right">Actions</th></tr>
            </thead>
            <tbody>
              {list.map((a) => {
                const isFav = favIds.includes(a.id);
                return (
                  <tr key={a.id}
                    onClick={() => onOpenAccount && onOpenAccount(a)}
                    className={`border-b border-[#F0F0F0] cursor-pointer hover:bg-[#FAFAF7] transition-colors group ${a.active === false ? "opacity-50" : ""}`}
                    data-testid={`account-${a.id}`}>
                    <td className="p-2 w-8">
                      <button onClick={(e) => toggleFav(a, e)}
                        className={`transition-colors ${isFav ? "text-[#C9A84C]" : "text-[#C5C5C5] hover:text-[#8B7F6A]"}`}
                        title={isFav ? "Unpin from Favourites" : "Pin to Favourites"}
                        data-testid={`fav-toggle-${a.id}`}>
                        <Star size={14} weight={isFav ? "fill" : "regular"} />
                      </button>
                    </td>
                    <td className="p-2 font-mono text-xs w-20">{a.code || "—"}</td>
                    <td className="p-2 font-semibold group-hover:text-[#8B7F6A]">
                      {a.name}
                      {a.active === false && <span className="ml-2 text-[10px] text-[#B87500]">INACTIVE</span>}
                    </td>
                    <td className="p-2 text-right font-mono text-xs text-[#5C5C5C]">{CURRENCY(a.current_balance ?? a.opening_balance)}</td>
                    <td className="p-2 text-right w-32">
                      <span className="inline-flex items-center justify-end gap-1">
                        {a.is_bank && <Bank size={12} className="text-[#8B7F6A] mr-1" />}
                        <button type="button" className="btn-ghost p-1.5" title="Edit account"
                          onClick={(event) => startEdit(a, event)} data-testid={`account-edit-${a.id}`}>
                          <PencilSimple size={12} />
                        </button>
                        <button type="button" className="btn-ghost p-1.5"
                          title={a.active === false ? "Restore account" : "Deactivate account"}
                          onClick={(event) => toggleActive(a, event)} data-testid={`account-active-${a.id}`}>
                          {a.active === false ? <ArrowCounterClockwise size={12} /> : <Archive size={12} />}
                        </button>
                        <CaretRight size={12} className="text-[#9A9A9A]" />
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
        </div>
      ))}
    </div>
  );
}

// ================================================================
function Reports({ pl, tb, onReload, onDownload, periodQs }) {
  if (!pl || !tb) return <div className="text-center py-16 overline">LOADING…</div>;
  return (
    <div className="space-y-6" data-testid="reports-tab">
      <div className="flex justify-between items-center">
        <div className="overline">FINANCIAL REPORTS</div>
        <div className="flex items-center gap-2">
          <button onClick={() => onDownload(`/accounting/reports/pl.csv${periodQs}`, "profit-loss.csv")} className="btn-ghost text-xs" data-testid="dl-pl-csv">
            <DownloadSimple size={12} /> P&amp;L
          </button>
          <button onClick={() => onDownload(`/accounting/reports/trial-balance.csv${periodQs}`, "trial-balance.csv")} className="btn-ghost text-xs" data-testid="dl-tb-csv">
            <DownloadSimple size={12} /> Trial balance
          </button>
          <button onClick={() => onDownload(`/journal-entries.csv${periodQs}`, "journal.csv")} className="btn-ghost text-xs" data-testid="dl-journal-csv">
            <DownloadSimple size={12} /> Journal
          </button>
          <button onClick={onReload} className="btn-ghost text-xs" data-testid="reports-refresh"><ArrowsClockwise size={12} /> Refresh</button>
        </div>
      </div>

      <div className="card-flat" data-testid="pl-report">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="overline">PROFIT &amp; LOSS</div>
            <div className="text-xs text-[#5C5C5C] mt-0.5">{pl.period_label || "Selected period"}</div>
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
        <div className="overflow-x-auto"><table className="w-full text-sm">
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
        </table></div>
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

// ================================================================
// Ledgers View — Client / Vendor / Employee / Project ledgers with running balance
// ================================================================
const ENTITY_TYPES = [
  { id: "client",   label: "Client",   endpoint: "/accounting/ledger/client" },
  { id: "vendor",   label: "Vendor",   endpoint: "/accounting/ledger/vendor" },
  { id: "employee", label: "Employee", endpoint: "/accounting/ledger/employee" },
  { id: "project",  label: "Project",  endpoint: "/accounting/ledger/project" },
];

function LedgersView({ clients, vendors, employees, projects, fy, fromDate, toDate }) {
  const [entityType, setEntityType] = useState("client");
  const [entityId, setEntityId] = useState("");
  const [ledger, setLedger] = useState(null);
  const [loading, setLoading] = useState(false);

  const options = {
    client:   clients.map((c) => ({ id: c.id, label: c.name })),
    vendor:   vendors.map((v) => ({ id: v.id, label: v.name })),
    employee: employees.map((e) => ({ id: e.id, label: `${e.name || ""}${e.employee_id ? ` · ${e.employee_id}` : ""}` })),
    project:  projects.map((p) => ({ id: p.id, label: p.name })),
  }[entityType] || [];

  useEffect(() => { setEntityId(""); setLedger(null); }, [entityType]);

  useEffect(() => {
    if (!entityId) { setLedger(null); return; }
    const cfg = ENTITY_TYPES.find((e) => e.id === entityType);
    const params = new URLSearchParams();
    if (fromDate || toDate) {
      if (fromDate) params.set("from_date", fromDate);
      if (toDate)   params.set("to_date", toDate);
    } else if (fy) {
      params.set("fy", fy);
    }
    const qs = params.toString() ? `?${params.toString()}` : "";
    setLoading(true);
    api.get(`${cfg.endpoint}/${entityId}${qs}`)
      .then(({ data }) => setLedger(data))
      .finally(() => setLoading(false));
  }, [entityType, entityId, fy, fromDate, toDate]);

  return (
    <div className="space-y-4" data-testid="ledgers-tab">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="overline">LEDGER FOR</span>
        <div className="flex border border-[#E5E5E5] rounded-none overflow-hidden">
          {ENTITY_TYPES.map((e) => (
            <button
              key={e.id}
              onClick={() => setEntityType(e.id)}
              data-testid={`ledger-type-${e.id}`}
              className={`px-3 py-1.5 text-xs ${entityType === e.id ? "bg-[#8B7F6A] text-white" : "text-[#5C5C5C] hover:bg-[#F5F5F5]"}`}
            >{e.label}</button>
          ))}
        </div>
        <select
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          className="border border-[#E5E5E5] px-3 py-1.5 text-sm bg-white min-w-[280px]"
          data-testid="ledger-entity-select"
        >
          <option value="">Select {ENTITY_TYPES.find((e) => e.id === entityType)?.label}…</option>
          {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      </div>

      {loading && <div className="overline">LOADING LEDGER…</div>}
      {!loading && !ledger && entityId && <div className="text-sm text-[#9A9A9A]">No data.</div>}
      {!loading && ledger && (
        <div className="space-y-4" data-testid="ledger-body">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
            <div className="card-flat"><div className="overline">Opening</div>
              <div className="font-mono text-lg" data-testid="ledger-opening">{CURRENCY(ledger.opening_balance)}</div></div>
            <div className="card-flat"><div className="overline">Inflow</div>
              <div className="font-mono text-lg text-[#1D633E]" data-testid="ledger-inflow">{CURRENCY(ledger.inflow)}</div></div>
            <div className="card-flat"><div className="overline">Outflow</div>
              <div className="font-mono text-lg text-[#B22B22]" data-testid="ledger-outflow">{CURRENCY(ledger.outflow)}</div></div>
            <div className="card-flat"><div className="overline">Closing</div>
              <div className="font-mono text-lg" data-testid="ledger-closing">{CURRENCY(ledger.closing_balance)}</div></div>
          </div>

          {ledger.entity_type === "project" && (
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div className="card-flat"><div className="overline">Revenue</div>
                <div className="font-mono">{CURRENCY(ledger.revenue)}</div></div>
              <div className="card-flat"><div className="overline">Expense</div>
                <div className="font-mono">{CURRENCY(ledger.expense)}</div></div>
              <div className="card-flat"><div className="overline">Project Profit</div>
                <div className="font-mono">{CURRENCY(ledger.profit)}</div></div>
            </div>
          )}

          <div className="card-flat">
            <div className="overline mb-2">{ledger.period?.label || "PERIOD"} · {ledger.entries?.length || 0} ENTRIES</div>
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead className="text-[#5C5C5C] border-b border-[#EEE]">
                <tr>
                  <th className="text-left py-1.5">Date</th>
                  <th className="text-left py-1.5">Narration</th>
                  <th className="text-left py-1.5">Source</th>
                  <th className="text-right py-1.5">Inflow</th>
                  <th className="text-right py-1.5">Outflow</th>
                  <th className="text-right py-1.5">Balance</th>
                </tr>
              </thead>
              <tbody>
                {(ledger.entries || []).length === 0 && (
                  <tr><td colSpan="6" className="text-[#9A9A9A] py-3 italic">No transactions in period.</td></tr>
                )}
                {(ledger.entries || []).map((e) => (
                  <tr key={e.id} className="border-b border-[#F5F5F5]" data-testid="ledger-row">
                    <td className="py-1.5 font-mono text-xs">{formatDate(e.date)}</td>
                    <td className="py-1.5">{e.narration}</td>
                    <td className="py-1.5 text-xs text-[#5C5C5C]">{e.source || "-"}</td>
                    <td className="py-1.5 text-right font-mono text-[#1D633E]">{e.inflow ? CURRENCY(e.inflow) : "-"}</td>
                    <td className="py-1.5 text-right font-mono text-[#B22B22]">{e.outflow ? CURRENCY(e.outflow) : "-"}</td>
                    <td className="py-1.5 text-right font-mono font-semibold">{CURRENCY(e.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </div>
        </div>
      )}
    </div>
  );
}


// ================================================================
// Validation Report — Admin-only accounting vs legacy diff report
// ================================================================
function ValidationReport({ data }) {
  if (!data) return <div className="overline">LOADING VALIDATION REPORT…</div>;
  if (data.error) return <div className="card-flat text-[#B22B22]">{data.error}</div>;
  const passed = data.difference?.match_within_1pc;
  return (
    <div className="space-y-4" data-testid="validation-tab">
      <div className={`p-4 border ${passed ? "border-[#1D633E] bg-[#EFF7EF]" : "border-[#B22B22] bg-[#FCEEEC]"}`}>
        <div className="overline">{passed ? "PASS" : "REVIEW"}</div>
        <div className="text-sm mt-1">{data.recommendation}</div>
        <div className="text-xs text-[#5C5C5C] mt-2">{data.period?.label}</div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card-flat">
          <div className="overline mb-2">ACCOUNTING ENGINE (source of truth)</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <tbody>
              <tr><td>Income</td><td className="text-right font-mono">{CURRENCY(data.accounting?.income)}</td></tr>
              <tr><td>Expense</td><td className="text-right font-mono">{CURRENCY(data.accounting?.expense)}</td></tr>
              <tr className="border-t"><td className="font-semibold">Profit</td><td className="text-right font-mono font-semibold">{CURRENCY(data.accounting?.profit)}</td></tr>
              <tr><td>JE Count</td><td className="text-right font-mono text-xs">{data.accounting?.je_count}</td></tr>
            </tbody>
          </table></div>
        </div>
        <div className="card-flat">
          <div className="overline mb-2">LEGACY (invoices + milestones)</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <tbody>
              <tr><td>Revenue invoiced</td><td className="text-right font-mono">{CURRENCY(data.legacy?.revenue_invoiced)}</td></tr>
              <tr><td>Collected (milestones)</td><td className="text-right font-mono">{CURRENCY(data.legacy?.collected_via_milestones)}</td></tr>
              <tr><td>Outstanding</td><td className="text-right font-mono">{CURRENCY(data.legacy?.outstanding_via_milestones)}</td></tr>
              <tr><td>Invoices</td><td className="text-right font-mono text-xs">{data.legacy?.invoice_count}</td></tr>
            </tbody>
          </table></div>
        </div>
      </div>
      <div className="card-flat">
        <div className="overline mb-2">DELTA</div>
        <div className="text-lg font-mono" data-testid="validation-diff">
          Income vs Milestone Collections: {CURRENCY(data.difference?.income_vs_milestones)}
        </div>
      </div>
      {data.diagnostics?.orphan_paid_invoices?.length > 0 && (
        <div className="card-flat">
          <div className="overline mb-2">ORPHAN PAID INVOICES (missing journal entry)</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-[#5C5C5C] border-b border-[#EEE]">
              <tr><th className="text-left py-1">Invoice #</th><th className="text-left py-1">Date</th><th className="text-right py-1">Total</th></tr>
            </thead>
            <tbody>
              {data.diagnostics.orphan_paid_invoices.map((i) => (
                <tr key={i.id} className="border-b border-[#F5F5F5]">
                  <td className="py-1">{i.invoice_number}</td>
                  <td className="py-1 text-xs">{formatDate(i.issue_date)}</td>
                  <td className="py-1 text-right font-mono">{CURRENCY(i.total)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>
      )}
      {data.diagnostics?.orphan_income_je?.length > 0 && (
        <div className="card-flat">
          <div className="overline mb-2">INCOME JEs WITHOUT CLIENT/PROJECT LINK</div>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="text-[#5C5C5C] border-b border-[#EEE]">
              <tr><th className="text-left py-1">Date</th><th className="text-left py-1">Narration</th><th className="text-right py-1">Amount</th></tr>
            </thead>
            <tbody>
              {data.diagnostics.orphan_income_je.map((e) => (
                <tr key={e.id} className="border-b border-[#F5F5F5]">
                  <td className="py-1 text-xs">{formatDate(e.date)}</td>
                  <td className="py-1">{e.narration}</td>
                  <td className="py-1 text-right font-mono">{CURRENCY(e.total)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>
      )}
    </div>
  );
}

