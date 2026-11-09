import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import { Daybook } from "../components/Daybook";
import { AccountLedgerPanel } from "../components/AccountLedgerPanel";
import { TransactionDetail } from "../components/TransactionDetail";
import { DataChecks } from "../components/DataChecks";
import PeriodClose from "../components/PeriodClose";
import CollectionEntries from "../components/CollectionEntries";
import { useAuth } from "../context/AuthContext";
import { RecurringExpenses, BankReconciliation, FavoriteAccountsStrip } from "../components/FinanceExtras";
import { toast } from "sonner";
import { dateForInput, empName, formatDate } from "../lib/format";
import { compatibleAccount, methodForAccount } from "../lib/cashbank";
import {
  Bank, TrendUp, TrendDown, Wallet, ChartLine, ArrowsClockwise,
  Plus, X, ArrowDown, ArrowUp, Coins, ListDashes, Money, Receipt,
  Scales, Waves, DownloadSimple, Notebook, CaretRight, Repeat, Star,
  HandCoins, ArrowsLeftRight, PencilSimple, Archive, ArrowCounterClockwise, WarningCircle, Trash,
} from "@phosphor-icons/react";
import SearchSelect from "../components/SearchSelect";
import { askForm, confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";
import { MoneyInTabs, useReminderFlow } from "../components/MoneyIn";
import { BellRinging, LockSimple } from "@phosphor-icons/react";

// Journal "source" codes in plain words for the dashboard.
const SOURCE_LABELS = {
  invoice_issue: "Invoice raised", invoice_payment: "Invoice payment", milestone_payment: "Fee instalment received",
  other_receivable_income: "Collection received", commission_income: "Vendor incentive", payroll: "Salary",
  payroll_reversal: "Salary reversed", employee_advance: "Staff advance", recurring_expense: "Recurring expense",
  vendor_payment: "Vendor payment", vendor_bill: "Vendor bill", expense: "Expense", income: "Income",
  expense_reimbursement: "Expense claim paid", loan_emi: "Loan EMI", loan_disbursement: "Loan received",
  capital: "Capital", owner_withdrawal: "Owner withdrawal", transfer: "Transfer", manual: "Manual entry",
  opening_balance: "Opening balance",
};
const sourceLabel = (code) => {
  if (!code) return "—";
  const key = String(code).toLowerCase();
  if (SOURCE_LABELS[key]) return SOURCE_LABELS[key];
  const words = key.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const CURRENCY = (n) => {
  const v = Number(n) || 0;   // negatives read "−₹5,000", not "₹-5,000"
  return `${v < 0 ? "−" : ""}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
};

const TABS = [
  { id: "dashboard", label: "Dashboard", Icon: ChartLine, group: "overview" },
  { id: "validation", label: "Health check", Icon: ArrowsClockwise, group: "overview" },
  { id: "income",    label: "Income",    Icon: ArrowDown, group: "in" },
  { id: "receivables", label: "Collections Due", Icon: Money, group: "in" },
  { id: "commissions", label: "Vendor incentives", Icon: Coins, group: "in" },
  { id: "expense",   label: "Expense",   Icon: ArrowUp, group: "out" },
  { id: "recurring", label: "Recurring", Icon: Repeat, group: "out" },
  { id: "daybook",   label: "Daybook",   Icon: Notebook, group: "books" },
  { id: "ledgers",   label: "Ledgers",   Icon: Bank, group: "books" },
  { id: "bank",      label: "Bank Reconciliation", Icon: Bank, group: "books" },
  { id: "reports",   label: "P&L · Trial Balance", Icon: Receipt, group: "reports" },
  { id: "balance",   label: "Balance Sheet", Icon: Scales, group: "reports" },
  { id: "cashflow",  label: "Cash Flow", Icon: Waves, group: "reports" },
  { id: "coa",       label: "Chart of Accounts", Icon: ListDashes, group: "setup" },
  { id: "close",     label: "Close & export", Icon: LockSimple, group: "setup" },
];

// Sections grouped by what the user is doing, not by accounting jargon.
const TAB_GROUPS = [
  { id: "overview", label: "Overview" },
  { id: "in",       label: "Money in" },
  { id: "out",      label: "Money out" },
  { id: "books",    label: "Books" },
  { id: "reports",  label: "Reports" },
  { id: "setup",    label: "Setup" },
];

export default function Accounting() {
  const { hasPerm } = useAuth();
  // Deep links such as /accounting?tab=receivables (from Invoices > Collections Due).
  const [tab, setTab] = useState(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab");
    return TABS.some((t) => t.id === wanted) ? wanted : "dashboard";
  });
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
        title="Accounting"
        kicker="Double-entry bookkeeping wired into projects, clients, and payroll. For staff reimbursement claims, use the Expenses module."
      >
        <button onClick={() => { setShowForm({ kind: "income" }); setTab("income"); }}
          className="btn-primary bg-[var(--success)]" data-testid="quick-income-btn">
          <ArrowDown size={14} /> Record income
        </button>
        <button onClick={() => { setShowForm({ kind: "expense" }); setTab("expense"); }}
          className="btn-primary bg-[var(--danger)]" data-testid="quick-expense-btn">
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

      <nav className="border border-[var(--line)] bg-white p-3 md:p-4" aria-label="Accounting sections" data-testid="accounting-tabs">
        <div className="flex items-center justify-between gap-3 mb-3 sm:hidden">
          <div className="overline">SECTION</div>
          <select
            value={tab}
            onChange={(event) => setTab(event.target.value)}
            className="input-flat min-w-[180px]"
            aria-label="Accounting section"
            data-testid="accounting-section-select"
          >
            {TAB_GROUPS.map((g) => (
              <optgroup key={g.id} label={g.label}>
                {TABS.filter((t) => t.group === g.id).map(({ id, label }) => <option key={id} value={id}>{label}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        <div className="hidden sm:grid sm:grid-cols-3 lg:grid-cols-6 gap-x-3 gap-y-4">
          {TAB_GROUPS.map((g) => (
            <div key={g.id} role="group" aria-labelledby={`acc-group-${g.id}`} data-testid={`acc-group-${g.id}`}>
              <div id={`acc-group-${g.id}`} className="text-[10px] font-semibold uppercase tracking-wider text-[var(--ink-3)] mb-1.5 px-1">{g.label}</div>
              <div className="flex flex-col gap-1">
                {TABS.filter((t) => t.group === g.id).map(({ id, label, Icon }) => (
                  <button key={id} onClick={() => setTab(id)} data-testid={`tab-${id}`}
                    aria-current={tab === id ? "page" : undefined}
                    className={`min-h-10 px-2.5 py-1.5 text-left text-xs flex items-center gap-2 rounded-md border transition ${tab === id
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[#5B4E3A] font-semibold"
                      : "border-transparent text-[var(--ink-2)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]"}`}>
                    <Icon size={15} className="shrink-0" /> <span>{label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </nav>

      {/* Shared financial period selector. "All time" is sent explicitly. */}
      {["income", "expense", "reports", "balance", "cashflow", "ledgers", "validation"].includes(tab) && (
        <div className="flex items-center gap-3 flex-wrap text-xs" data-testid="fy-bar">
          <span className="overline">FINANCIAL PERIOD</span>
          <select aria-label="Fy"
            value={fy}
            onChange={(e) => { setFy(e.target.value); setFromDate(""); setToDate(""); }}
            className="border border-[var(--line)] px-2 py-1 text-xs bg-white"
            data-testid="fy-select"
          >
            <option value="all">— All time —</option>
            {fyOptions.map((o) => (
              <option key={o.label} value={o.label}>{`FY ${o.label}${o.is_current ? " (current)" : ""}`}</option>
            ))}
          </select>
          <span className="text-[var(--ink-3)]">or</span>
          <input
            type="date" value={fromDate}
            onChange={(e) => { setFromDate(e.target.value); setFy(""); }}
            className="border border-[var(--line)] px-2 py-1 text-xs"
            data-testid="from-date"
          />
          <span className="text-[var(--ink-3)]">→</span>
          <input
            type="date" value={toDate}
            onChange={(e) => { setToDate(e.target.value); setFy(""); }}
            className="border border-[var(--line)] px-2 py-1 text-xs"
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
          clients={clients}
          projects={projects}
          vendors={vendors}
          onSaved={() => { loadDashboard(); loadCommon(); }}
        />
      )}

      {tab === "daybook" && (
        <Daybook
          accounts={accounts} clients={clients} vendors={vendors}
          projects={projects} employees={employees}
        />
      )}

      {tab === "close" && (
        <PeriodClose isAdmin={hasPerm("*.*")} currentFy={fyOptions.find((o) => o.is_current)?.label}
          fyChoices={fyOptions.filter((o) => o.from <= new Date().toISOString().slice(0, 10)).map((o) => o.label).reverse()} />
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
          clients={clients} vendors={vendors} accounts={accounts}
          employees={employees} projects={projects}
          fy={fy} fromDate={fromDate} toDate={toDate}
        />
      )}

      {tab === "validation" && (
        <>
          {hasPerm("*.*") && <DataChecks />}
          <ValidationReport data={validation} />
        </>
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
    <form onSubmit={submit} className="border-y border-[var(--line)] py-4 space-y-3" data-testid="owner-withdrawal-form">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="overline">OWNER WITHDRAWAL</div>
          <div className="text-xs text-[var(--ink-2)] mt-1">Debit Owner Drawings and credit the selected cash or bank account.</div>
        </div>
        <button type="button" className="btn-icon" onClick={onClose} aria-label="Close owner withdrawal form"><X size={14} /></button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Date</span>
          <input required type="date" className="input-flat w-full mt-1" value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Amount</span>
          <input required type="number" min="0.01" step="0.01" className="input-flat w-full mt-1" value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="owner-withdrawal-amount" /></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Paid from</span>
          <SearchSelect required className="input-flat w-full mt-1" value={form.paid_from_account_id}
            onChange={(e) => setForm({ ...form, paid_from_account_id: e.target.value })}>
            <option value="">Select cash or bank</option>
            {banks.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </SearchSelect></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Reference</span>
          <input className="input-flat w-full mt-1" value={form.reference}
            onChange={(e) => setForm({ ...form, reference: e.target.value })} placeholder="Optional" /></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Narration</span>
          <input required className="input-flat w-full mt-1" value={form.narration}
            onChange={(e) => setForm({ ...form, narration: e.target.value })} /></label>
      </div>
      {error && <div className="text-xs text-[var(--danger)]" role="alert">{error}</div>}
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
    <form onSubmit={submit} className="border-y border-[var(--line)] py-4 space-y-3" data-testid="capital-transfers-form">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="overline">CAPITAL, INVESTMENTS &amp; PARTY MONEY</div>
          <div className="text-xs text-[var(--ink-2)] mt-1">Balance-sheet transactions that should not be recorded as income or expense.</div>
        </div>
        <button type="button" className="btn-icon" onClick={onClose} aria-label="Close capital and transfers form"><X size={14} /></button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Transaction</span>
          <select aria-label="Transaction type" className="input-flat w-full mt-1" value={form.kind}
            onChange={(event) => setForm({ ...form, kind: event.target.value })} data-testid="transfer-kind">
            {TRANSFER_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Date</span>
          <input required type="date" className="input-flat w-full mt-1" value={form.date}
            onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Amount</span>
          <input required type="number" min="0.01" step="0.01" className="input-flat w-full mt-1" value={form.amount}
            onChange={(event) => setForm({ ...form, amount: event.target.value })} data-testid="transfer-amount" /></label>
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Cash / Bank</span>
          <SearchSelect required className="input-flat w-full mt-1" value={form.bank_account_id}
            onChange={(event) => setForm({ ...form, bank_account_id: event.target.value })}>
            <option value="">Select cash or bank</option>
            {banks.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </SearchSelect></label>
        {needsParty && <label className="block"><span className="text-xs text-[var(--ink-2)]">Person / party</span>
          <input required className="input-flat w-full mt-1" value={form.party_name}
            onChange={(event) => setForm({ ...form, party_name: event.target.value })}
            placeholder="e.g. Ritesh Soni" data-testid="transfer-party" /></label>}
        <label className="block"><span className="text-xs text-[var(--ink-2)]">Reference</span>
          <input className="input-flat w-full mt-1" value={form.reference}
            onChange={(event) => setForm({ ...form, reference: event.target.value })} placeholder="Optional" /></label>
        <label className="block md:col-span-3"><span className="text-xs text-[var(--ink-2)]">Notes</span>
          <input className="input-flat w-full mt-1" value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Optional details" /></label>
      </div>
      {error && <div className="text-xs text-[var(--danger)]" role="alert">{error}</div>}
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
          <div className="text-xs text-[var(--ink-2)] mt-0.5">Earned = expected from vendor bills · Received = cash posted to income · Unallocated = receipt not matched to a bill</div>
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
            <thead className="text-[10px] font-mono uppercase text-[var(--ink-3)]">
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
                  <tr key={v.vendor_id} className="border-t border-[var(--line-soft)] hover:bg-[var(--surface-2)]">
                    <td className="p-2">
                      <a href={`/vendors/${v.vendor_id}`} className="font-semibold hover:text-[var(--accent-strong)]">{v.vendor_name}</a>
                    </td>
                    <td className="p-2 text-right font-mono">{CURRENCY(v.earned)}</td>
                    <td className="p-2 text-right font-mono text-[var(--success)]">{CURRENCY(v.received)}</td>
                    <td className={`p-2 text-right font-mono font-semibold ${pending > 0 ? "text-[var(--danger)]" : "text-[var(--ink-2)]"}`}>{CURRENCY(pending)}</td>
                  </tr>
                );
              })}
              {(data.top_vendors || []).length === 0 && (
                <tr><td colSpan={4} className="p-6 text-center text-[var(--ink-3)]">No vendor incentive data yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card-flat">
        <div className="overline mb-3">BY PROJECT</div>
        {(data.by_project || []).length === 0 && <div className="text-sm text-[var(--ink-3)]">No project-linked vendor incentive yet.</div>}
        {(data.by_project || []).slice(0, 10).map((p) => (
          <div key={p.project_id} className="flex justify-between items-center border-b border-[var(--hover)] py-2 text-sm">
            <a href={`/projects/${p.project_id}`} className="font-semibold hover:text-[var(--accent-strong)]">{p.project_name}</a>
            <div className="flex gap-4 font-mono">
              <span className="text-[var(--ink-2)]">Received: {CURRENCY(p.received)}</span>
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
          {rows.length === 0 && <tr><td className="text-[var(--ink-3)] py-2">No entries.</td></tr>}
          {rows.map((r) => (
            <tr key={r.account_id} className="border-b border-[var(--hover)]">
              <td className="py-1.5">{r.name}</td>
              <td className="py-1.5 text-right font-mono">{CURRENCY(r.balance)}</td>
            </tr>
          ))}
          {extraRow}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-[var(--ink)]">
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
              <tr className="border-b border-[var(--hover)] italic text-[var(--ink-2)]">
                <td className="py-1.5">Net Income (period)</td>
                <td className="py-1.5 text-right font-mono">{CURRENCY(bs.equity.net_income)}</td>
              </tr>
            }
          />
        </div>
      </div>
      <div className={`p-4 border text-sm ${bs.balanced ? "border-[var(--success)] bg-[var(--success-soft)] text-[var(--success)]" : "border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
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
              <thead className="text-[var(--ink-2)] border-b border-[var(--line-soft)]">
                <tr><th className="text-left py-1">Date</th><th className="text-left py-1">Narration</th><th className="text-right py-1">Δ</th></tr>
              </thead>
              <tbody>
                {bs.unbalanced_journal_entries.slice(0, 10).map((e) => (
                  <tr key={e.id} className="border-b border-[var(--hover)]">
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
    <div className="flex justify-between border-b border-[var(--hover)] py-1.5 text-sm">
      <span className="text-[var(--ink-2)] capitalize">{label.replace(/_/g, " ")}</span>
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
        <KPI label="Outflows" value={CURRENCY(cf.total_outflow)} Icon={TrendDown} tint="#B22B22" />
        <KPI label="Closing balance" value={CURRENCY(cf.closing_balance)} Icon={Wallet} tint={cf.closing_balance >= 0 ? "#8B7F6A" : "#B22B22"} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card-flat">
          <div className="overline mb-3">INFLOWS</div>
          {Object.entries(cf.inflows).map(([k, v]) => (
            <Row key={k} label={k} value={v} tint="text-[var(--success)]" />
          ))}
          <div className="flex justify-between pt-3 mt-2 border-t-2 border-[var(--ink)]">
            <span className="overline">TOTAL</span>
            <span className="font-mono font-bold">{CURRENCY(cf.total_inflow)}</span>
          </div>
        </div>
        <div className="card-flat">
          <div className="overline mb-3">OUTFLOWS</div>
          {Object.entries(cf.outflows).map(([k, v]) => (
            <Row key={k} label={k} value={v} tint="text-[var(--danger)]" />
          ))}
          <div className="flex justify-between pt-3 mt-2 border-t-2 border-[var(--ink)]">
            <span className="overline">TOTAL</span>
            <span className="font-mono font-bold">{CURRENCY(cf.total_outflow)}</span>
          </div>
        </div>
      </div>

      {cf.activities && (
        <div className="border border-[var(--line)] bg-white overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
              <tr><th className="p-3 text-left overline">ACTIVITY</th><th className="p-3 text-left overline">DETAIL</th><th className="p-3 text-right overline">INFLOW</th><th className="p-3 text-right overline">OUTFLOW</th><th className="p-3 text-right overline">NET</th></tr>
            </thead>
            <tbody>
              {Object.entries(cf.activities).flatMap(([activity, detail]) => (
                detail.lines?.length ? detail.lines.map((line, index) => (
                  <tr key={`${activity}-${line.label}`} className="border-b border-[var(--line-soft)]">
                    <td className="p-3 font-semibold capitalize">{index === 0 ? activity : ""}</td>
                    <td className="p-3 text-[var(--ink-2)]">{line.label}</td>
                    <td className="p-3 text-right font-mono text-[var(--success)]">{line.inflow ? CURRENCY(line.inflow) : "-"}</td>
                    <td className="p-3 text-right font-mono text-[var(--danger)]">{line.outflow ? CURRENCY(line.outflow) : "-"}</td>
                    <td className="p-3 text-right font-mono font-semibold">{CURRENCY(line.net)}</td>
                  </tr>
                )) : [
                  <tr key={`${activity}-empty`} className="border-b border-[var(--line-soft)]">
                    <td className="p-3 font-semibold capitalize">{activity}</td><td className="p-3 text-[var(--ink-3)]">No movement</td><td className="p-3" colSpan="3" />
                  </tr>,
                ]
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Array.isArray(cf.cash_accounts) && cf.cash_accounts.length > 0 && (
        <div className="border border-[var(--line)] bg-white overflow-x-auto">
          <div className="p-3 border-b border-[var(--line)] overline">CASH & BANK RECONCILIATION</div>
          <table className="w-full min-w-[620px] text-sm">
            <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]"><tr><th className="p-3 text-left overline">ACCOUNT</th><th className="p-3 text-right overline">OPENING</th><th className="p-3 text-right overline">INFLOW</th><th className="p-3 text-right overline">OUTFLOW</th><th className="p-3 text-right overline">CLOSING</th></tr></thead>
            <tbody>{cf.cash_accounts.map((account) => (
              <tr key={account.account_id} className="border-b border-[var(--line-soft)]"><td className="p-3 font-semibold">{account.name}</td><td className="p-3 text-right font-mono">{CURRENCY(account.opening_balance)}</td><td className="p-3 text-right font-mono text-[var(--success)]">{CURRENCY(account.inflow)}</td><td className="p-3 text-right font-mono text-[var(--danger)]">{CURRENCY(account.outflow)}</td><td className="p-3 text-right font-mono font-semibold">{CURRENCY(account.closing_balance)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}

      <div className={`p-4 border text-sm ${cf.net_change >= 0 ? "border-[var(--success)] bg-[var(--success-soft)] text-[var(--success)]" : "border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
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
        <KPI label="This month P&L" value={CURRENCY(k.profit_month)} Icon={ChartLine} tint={k.profit_month >= 0 ? "#1D633E" : "#B22B22"} testid="kpi-profit" />
        <KPI label="Outstanding" value={CURRENCY(k.outstanding)} Icon={TrendDown} tint="#A86400" testid="kpi-outstanding" />
        <KPI label="Overdue" value={CURRENCY(k.overdue)} Icon={TrendDown} tint="#B22B22" testid="kpi-overdue" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SubKPI label="Income (month)" value={CURRENCY(k.income_month)} tint="#1D633E" />
        <SubKPI label="Expense (month)" value={CURRENCY(k.expense_month)} tint="#B22B22" />
        {k.salary_period ? (
          <SubKPI label={`Salary · ${k.salary_period.label}`} value={CURRENCY(k.salary_period.total)} tint="#2B5299"
            sub={`${k.salary_period.count} ${k.salary_period.count === 1 ? "person" : "people"} paid`} testid="kpi-salary-period" />
        ) : (
          <SubKPI label="Salary (month)" value={CURRENCY(k.salary_month)} tint="#2B5299" />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-flat">
          <div className="flex items-center justify-between mb-3">
            <div className="overline">CASH & BANK ACCOUNTS</div>
            <button onClick={onRefresh} className="btn-ghost text-xs"><ArrowsClockwise size={12} /> Refresh</button>
          </div>
          {k.cash_bank_by_account.map((b, i) => (
            <div key={b.account_id ?? i} className="flex items-center justify-between border-b border-[var(--line-soft)] py-2 text-sm" data-testid={`bank-${b.account_id}`}>
              <div className="flex items-center gap-2"><Bank size={14} className="text-[var(--accent-strong)]" />{b.name}</div>
              <span className="font-mono font-semibold">{CURRENCY(b.balance)}</span>
            </div>
          ))}
        </div>

        <div className="card-flat">
          <div className="overline mb-3">DUE TO COLLECT · next 30 days</div>
          {d.upcoming_payments.length === 0 && <div className="text-center py-6 text-sm text-[var(--ink-3)]">Nothing due from clients in the next 30 days.</div>}
          {d.upcoming_payments.slice(0, 8).map((m, i) => (
            <div key={m.id ?? i} className="flex items-center justify-between gap-3 border-b border-[var(--line-soft)] py-2 text-sm">
              <div className="min-w-0">
                <div className="font-semibold truncate">{m.name}</div>
                <div className="text-xs text-[var(--ink-2)] truncate">
                  {m.project_name ? `${m.project_name} · ` : ""}due {formatDate(m.due_date)}
                </div>
              </div>
              <span className="font-mono font-semibold text-[var(--success)] shrink-0">{CURRENCY(m.outstanding ?? m.amount)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card-flat">
        <div className="overline mb-3">RECENT TRANSACTIONS</div>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-2)]">
            <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Narration</th><th className="p-2 text-left">Source</th><th className="p-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            {d.recent_transactions.map((t, i) => (
              <tr key={t.id ?? i} className="border-t border-[var(--line-soft)]" data-testid={`recent-${t.id}`}>
                <td className="p-2 font-mono text-xs">{formatDate(t.date)}</td>
                <td className="p-2">{t.narration}</td>
                <td className="p-2 text-xs text-[var(--ink-2)]">{sourceLabel(t.source)}</td>
                <td className="p-2 text-right font-mono font-semibold">{CURRENCY(t.total)}</td>
              </tr>
            ))}
            {d.recent_transactions.length === 0 && <tr><td colSpan={4} className="p-8 text-center text-[var(--ink-3)]">No transactions yet.</td></tr>}
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

function SubKPI({ label, value, tint, sub, testid }) {
  return (
    <div className="card-flat" data-testid={testid}>
      <div className="overline">{label}</div>
      <div className="font-display font-bold text-2xl mt-1" style={{ color: tint }}>{value}</div>
      {sub && <div className="text-xs text-[var(--ink-3)] mt-1">{sub}</div>}
    </div>
  );
}

function CollectionsDue({ banks, incomeAccounts, clients, projects, vendors, onSaved }) {
  // The income account the money will land in decides the form: the vendor
  // incentive account asks for a vendor; anything else asks for a client.
  const isIncentiveAccount = (id) => /incentive|commission/i.test(incomeAccounts.find((a) => a.id === id)?.name || "");
  const defaultIncomeId = (incomeAccounts.find((a) => /consult/i.test(a.name)) || incomeAccounts[0])?.id || "";
  const emptyPlan = {
    name: "", amount: "", due_date: "",
    vendor_id: "", client_id: "", project_id: "", recognition: "planned",
    income_account_id: defaultIncomeId, reference: "", reminder_date: "", reminder_time: "10:00",
    remind_before_days: "0", repeat_every: "none", notes: "",
  };
  const [data, setData] = useState(null);
  const [startReminder, reminderModal] = useReminderFlow();
  const [filter, setFilter] = useState("active");
  const [category, setCategory] = useState("all");
  const [age, setAge] = useState(null);       // receivable aging bucket filter
  const [query, setQuery] = useState("");
  const [collecting, setCollecting] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showPlan, setShowPlan] = useState(false);
  const [editingRow, setEditingRow] = useState(null);
  const [entriesFor, setEntriesFor] = useState(null);
  const navigate = useNavigate();
  const [plan, setPlan] = useState(emptyPlan);
  const [receipt, setReceipt] = useState({
    date: new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
    amount: "",
    bank_account_id: "", income_account_id: "", payment_method: "bank_transfer",
    reference: "", notes: "",
    request_key: "",
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
      income_account_id: row.income_account_id || current.income_account_id || incomeAccounts[0]?.id || "",
      amount: row.outstanding,
      request_key: crypto.randomUUID(),
      notes: `Collection · ${row.name || row.project_name || row.vendor_name}`,
    }));
  };

  const saveReceipt = async (event) => {
    event.preventDefault();
    if (!collecting || saving) return;
    setSaving(true);
    try {
      const { request_key, ...receiptPayload } = receipt;
      await api.post("/accounting/collections/receive", {
        ...receiptPayload, amount: Number(receipt.amount),
        source_type: collecting.source_type,
        source_id: collecting.id,
      }, { headers: { "Idempotency-Key": request_key } });
      toast.success("Collection receipt recorded");
      setCollecting(null);
      await load();
      onSaved?.();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not record receipt");
    } finally {
      setSaving(false);
    }
  };

  const savePlan = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const common = {
        amount: Number(plan.amount), due_date: plan.due_date || undefined,
        project_id: plan.project_id || undefined, reference: plan.reference || undefined,
        reminder_date: plan.reminder_date || undefined, notes: plan.notes || undefined,
        reminder_time: plan.reminder_date ? (plan.reminder_time || "10:00") : undefined,
        remind_before_days: plan.reminder_date ? Number(plan.remind_before_days || 0) : undefined,
        repeat_every: plan.reminder_date ? (plan.repeat_every || "none") : undefined,
      };
      const incentive = editingRow ? editingRow.source_type === "vendor_commission" : isIncentiveAccount(plan.income_account_id);
      if (incentive) {
        const path = `/vendors/${plan.vendor_id}/commissions${editingRow ? `/${editingRow.id}` : ""}`;
        await api[editingRow ? "patch" : "post"](path, {
          ...common, recognition: plan.recognition,
        });
      } else {
        const path = `/accounting/receivables${editingRow ? `/${editingRow.id}` : ""}`;
        const accountName = incomeAccounts.find((a) => a.id === plan.income_account_id)?.name;
        const party = clients.find((c) => c.id === plan.client_id)?.name || vendors.find((v) => v.id === plan.vendor_id)?.name;
        await api[editingRow ? "patch" : "post"](path, {
          ...common, name: plan.name || [accountName, party].filter(Boolean).join(" · ") || "Expected collection",
          client_id: plan.client_id || undefined,
          vendor_id: plan.vendor_id || undefined,
          income_account_id: plan.income_account_id || undefined,
        });
      }
      toast.success(plan.reminder_date
        ? "Saved. The reminder is on the calendar and in Payment Reminders. Nothing posted to accounts."
        : "Saved to Collections Due. Nothing posted to accounts.");
      setShowPlan(false);
      setEditingRow(null);
      setPlan(emptyPlan);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not add collection reminder");
    } finally { setSaving(false); }
  };

  const editPlan = (row) => {
    setEditingRow(row);
    setPlan({
      name: row.source_type === "vendor_commission" ? "" : (row.name || ""), amount: row.amount,
      due_date: row.due_date || "", vendor_id: row.vendor_id || "",
      client_id: row.client_id || "", project_id: row.project_id || "",
      recognition: row.recognition === "earned" ? "earned" : "planned",
      income_account_id: row.source_type === "vendor_commission"
        ? (incomeAccounts.find((a) => /incentive|commission/i.test(a.name))?.id || "")
        : (row.income_account_id || defaultIncomeId),
      reference: row.reference || "", reminder_date: row.reminder_date || "",
      reminder_time: row.reminder_time || "10:00", remind_before_days: String(row.remind_before_days || 0),
      repeat_every: row.repeat_every || "none", notes: row.notes || "",
    });
    setShowPlan(true);
  };

  const cancelPlan = async (row) => {
    if (!await confirmAction("Cancel this expected collection? No accounting entry will be deleted.")) return;
    try {
      const path = row.source_type === "vendor_commission"
        ? `/vendors/${row.vendor_id}/commissions/${row.id}`
        : `/accounting/receivables/${row.id}`;
      await api.delete(path);
      toast.success("Expected collection cancelled");
      await load();
    } catch (error) { toast.error(error?.response?.data?.detail || "Could not cancel collection"); }
  };

  if (!data) return <div className="overline">LOADING COLLECTIONS…</div>;
  const term = query.trim().toLowerCase();
  // Active queue = anything with money still to collect. Fully received items
  // move to Received history instead of lingering in the queue at Rs. 0.
  const CATEGORY_OF = { invoice: "client", milestone: "client", vendor_commission: "vendor_commission",
                        other_receivable: "other_receivable" };
  const inCategory = (row) => category === "all" || CATEGORY_OF[row.source_type] === category;
  const matchesFilter = (row, id) => {
    if (id === "active") return row.status !== "received" && row.outstanding > 0;
    if (id === "history") return row.received_amount > 0;
    return row.bucket === id && row.status !== "received";
  };
  const isHistory = filter === "history";
  // Receivable aging: how long money has been overdue (India business date).
  const todayIso = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
  const ageOf = (row) => {
    if (!row.due_date) return "none";
    const days = Math.round((Date.parse(todayIso) - Date.parse(row.due_date)) / 86400e3);
    return days <= 0 ? "current" : days <= 30 ? "d30" : days <= 60 ? "d60" : days <= 90 ? "d90" : "d90p";
  };
  const AGES = [["current", "Not yet due"], ["d30", "1–30 days late"], ["d60", "31–60"], ["d90", "61–90"], ["d90p", "Over 90"], ["none", "No due date"]];
  const open = (data.rows || []).filter((row) => row.status !== "received" && row.outstanding > 0 && inCategory(row));
  const aging = AGES.map(([id, label]) => {
    const inBucket = open.filter((row) => ageOf(row) === id);
    return { id, label, count: inBucket.length, amount: inBucket.reduce((sum, row) => sum + Number(row.outstanding || 0), 0) };
  });
  const rows = (data.rows || []).filter((row) => {
    if (!matchesFilter(row, filter) || !inCategory(row)) return false;
    if (age && !isHistory && ageOf(row) !== age) return false;
    if (!term) return true;
    return `${row.project_name || ""} ${row.client_name || ""} ${row.vendor_name || ""} ${row.name || ""} ${row.reference || ""} ${row.source_type || ""}`
      .toLowerCase().includes(term);
  });
  const countFor = (id) => (data.rows || []).filter((row) => matchesFilter(row, id) && inCategory(row)).length;
  const filters = [
    ["active", "Active"],
    ["overdue", "Overdue"],
    ["due_today", "Due today"],
    ["upcoming", "Upcoming"],
    ["partially_received", "Partially received"],
    ["later", "Later"],
    ["no_due_date", "No due date"],
    ["history", "Received history"],
  ];
  const categories = [
    ["all", "All money in"], ["client", "Client payments"],
    ["vendor_commission", "Vendor incentive"], ["other_receivable", "Other receivables"],
  ];

  return (
    <div className="space-y-4" data-testid="collections-due-tab">
      <MoneyInTabs />
      {reminderModal}
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <div className="overline">MONEY IN / COLLECTIONS DUE</div>
          <div className="text-xs text-[var(--ink-2)] mt-1">Invoices, project milestones, vendor incentives and other receivables · as of {formatDate(data.as_of)}</div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <input className="input-flat min-w-[260px]" value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search person, project, invoice or reference"
            data-testid="collections-search" />
          <button type="button" className="btn-primary" onClick={() => {
            setShowPlan(!showPlan); setEditingRow(null); setPlan(emptyPlan);
          }}>
            <Plus size={13} /> {showPlan ? "Cancel" : "Add expected collection"}
          </button>
        </div>
      </div>

      {showPlan && (
        <form onSubmit={savePlan} className="card-flat space-y-3" data-testid="collection-plan-form">
          <div className="overline">{editingRow ? "EDIT EXPECTED COLLECTION" : "EXPECTED COLLECTION · NOTHING IS POSTED UNTIL YOU RECORD THE PAYMENT"}</div>
          {(() => {
            const incentive = editingRow ? editingRow.source_type === "vendor_commission" : isIncentiveAccount(plan.income_account_id);
            return (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <label className="text-xs">Income account on receipt<SearchSelect required disabled={Boolean(editingRow)} className="input-flat mt-1 w-full" value={plan.income_account_id}
                  onChange={(e) => setPlan({ ...plan, income_account_id: e.target.value, vendor_id: "", client_id: "" })} data-testid="plan-income-account">
                  <option value="" disabled>Select income account</option>
                  {incomeAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </SearchSelect></label>
                {incentive ? (
                  <label className="text-xs">Vendor<SearchSelect required className="input-flat mt-1 w-full" value={plan.vendor_id} onChange={(e) => setPlan({ ...plan, vendor_id: e.target.value })} data-testid="plan-vendor"><option value="">Select vendor</option>{vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</SearchSelect></label>
                ) : (
                  <label className="text-xs">Client<SearchSelect className="input-flat mt-1 w-full" value={plan.client_id} onChange={(e) => setPlan({ ...plan, client_id: e.target.value })} data-testid="plan-client"><option value="">No client</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</SearchSelect></label>
                )}
                <label className="text-xs">Project<SearchSelect className="input-flat mt-1 w-full" value={plan.project_id} onChange={(e) => setPlan({ ...plan, project_id: e.target.value })}><option value="">No project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</SearchSelect></label>
                <label className="text-xs">Expected amount<input required min="0.01" step="0.01" type="number" className="input-flat mt-1 w-full" value={plan.amount} onChange={(e) => setPlan({ ...plan, amount: e.target.value })} data-testid="plan-amount" /></label>
                {!incentive && <label className="text-xs">What is due? (optional)<input className="input-flat mt-1 w-full" value={plan.name} onChange={(e) => setPlan({ ...plan, name: e.target.value })} placeholder="e.g. 2nd instalment, referral fee" /></label>}
                <label className="text-xs">Due date<input type="date" className="input-flat mt-1 w-full" value={plan.due_date} onChange={(e) => setPlan({ ...plan, due_date: e.target.value })} data-testid="plan-due" /></label>
                <label className="text-xs">Reference<input className="input-flat mt-1 w-full" value={plan.reference} onChange={(e) => setPlan({ ...plan, reference: e.target.value })} /></label>
              </div>
            );
          })()}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-[var(--line-soft)] pt-3" data-testid="plan-reminder">
            <label className="text-xs">Reminder date<input type="date" className="input-flat mt-1 w-full" value={plan.reminder_date} onChange={(e) => setPlan({ ...plan, reminder_date: e.target.value })} data-testid="plan-reminder-date" /></label>
            <label className="text-xs">Reminder time<input type="time" disabled={!plan.reminder_date} className="input-flat mt-1 w-full" value={plan.reminder_time} onChange={(e) => setPlan({ ...plan, reminder_time: e.target.value })} data-testid="plan-reminder-time" /></label>
            <label className="text-xs">Also remind before<select disabled={!plan.reminder_date} className="input-flat mt-1 w-full" value={plan.remind_before_days} onChange={(e) => setPlan({ ...plan, remind_before_days: e.target.value })} data-testid="plan-remind-before">
              <option value="0">No advance reminder</option><option value="1">1 day before</option><option value="2">2 days before</option><option value="3">3 days before</option><option value="7">1 week before</option>
            </select></label>
            <label className="text-xs">Repeat until received<select disabled={!plan.reminder_date} className="input-flat mt-1 w-full" value={plan.repeat_every} onChange={(e) => setPlan({ ...plan, repeat_every: e.target.value })} data-testid="plan-repeat">
              <option value="none">Don't repeat</option><option value="daily">Every day</option><option value="weekly">Every week</option>
            </select></label>
            {plan.reminder_date && <p className="col-span-2 md:col-span-4 text-[11px] text-[var(--ink-3)]">The reminder goes to the calendar (and your connected Google Calendar), Invoices &gt; Payment Reminders, and rings in the ERP at that time. It stops by itself once the money is recorded.</p>}
          </div>
          <textarea className="input-flat w-full" value={plan.notes} onChange={(e) => setPlan({ ...plan, notes: e.target.value })} placeholder="Notes" />
          <button className="btn-primary" disabled={saving} data-testid="plan-save">{saving ? "Saving…" : editingRow ? "Save changes" : "Save to Collections Due"}</button>
        </form>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Pending collection" value={CURRENCY(data.totals?.all)} Icon={Money} tint="#0A0A0A" />
        <KPI label="Overdue" value={CURRENCY(data.totals?.overdue)} Icon={ArrowUp} tint="#B22B22" />
        <KPI label="Due today / upcoming" value={CURRENCY((data.totals?.due_today || 0) + (data.totals?.upcoming || 0))} Icon={ArrowDown} tint="#7A4E1A" />
        <KPI label="Received" value={CURRENCY(data.totals?.received)} Icon={ChartLine} tint="#1D633E" />
      </div>

      {open.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 border border-[var(--line)] divide-x divide-y lg:divide-y-0 divide-[var(--line-soft)]"
             role="group" aria-label="Money due by age" data-testid="collections-aging">
          {aging.map((b) => (
            <button key={b.id} type="button" disabled={!b.count} aria-pressed={age === b.id}
              onClick={() => { setAge(age === b.id ? null : b.id); if (isHistory) setFilter("active"); }}
              className={`text-left px-3 py-2 transition ${age === b.id ? "bg-[var(--ink)] text-white" : "bg-white hover:bg-[var(--hover)]"} disabled:opacity-50 disabled:cursor-default`}
              data-testid={`aging-${b.id}`}>
              <div className={`text-[10px] uppercase tracking-wider ${age === b.id ? "text-white/70" : ["d60", "d90", "d90p"].includes(b.id) && b.count ? "text-[var(--danger)]" : "text-[var(--ink-3)]"}`}>{b.label}</div>
              <div className="font-semibold tabular-nums text-sm">{CURRENCY(b.amount)}</div>
              <div className={`text-[10px] ${age === b.id ? "text-white/70" : "text-[var(--ink-3)]"}`}>{b.count} {b.count === 1 ? "item" : "items"}</div>
            </button>
          ))}
        </div>
      )}
      {age && !isHistory && (
        <div className="text-xs text-[var(--ink-2)] -mt-2">Showing {AGES.find(([id]) => id === age)?.[1].toLowerCase()} only · <button type="button" className="underline" onClick={() => setAge(null)}>show all</button></div>
      )}

      <div className="flex flex-col gap-2">
        <div className="flex gap-1.5 flex-wrap" role="tablist" aria-label="Collection status" data-testid="collections-filters">
          {filters.map(([id, label]) => {
            const n = countFor(id);
            return (
              <button key={id} type="button" role="tab" aria-selected={filter === id} onClick={() => setFilter(id)}
                className={`px-3 py-1.5 text-xs border rounded-full transition ${filter === id ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--line)] hover:border-[var(--accent-strong)]"} ${id === "history" ? "sm:ml-auto" : ""}`}
                data-testid={`collections-filter-${id}`}>
                {label}{n > 0 && <span className={`ml-1.5 ${filter === id ? "text-white/70" : "text-[var(--ink-3)]"}`}>{n}</span>}
              </button>
            );
          })}
        </div>
        <div className="flex gap-1.5 flex-wrap" aria-label="Collection category" data-testid="collections-categories">
          {categories.map(([id, label]) => (
            <button key={id} type="button" aria-pressed={category === id} onClick={() => setCategory(id)}
              className={`px-2.5 py-1 text-[11px] rounded ${category === id ? "bg-[var(--hover)] text-[var(--ink)] font-semibold" : "text-[var(--ink-2)] hover:bg-[var(--hover)]"}`}
              data-testid={`collections-category-${id}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="border border-[var(--line)] overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] text-[10px] font-mono uppercase text-[var(--ink-2)]">
            <tr>
              <th className="p-3 text-left">Due date</th>
              <th className="p-3 text-left">Source</th>
              <th className="p-3 text-left">Party / project</th>
              <th className="p-3 text-left">Collection</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-right">{isHistory ? "Received" : "To collect"}</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-[var(--line-soft)] hover:bg-[var(--surface-2)]">
                <td className="p-3 font-mono text-xs whitespace-nowrap">
                  <div>{formatDate(row.due_date)}</div>
                  {row.days_overdue > 0 && <div className="text-[10px] text-[var(--danger)]">{row.days_overdue} days overdue</div>}
                </td>
                <td className="p-3"><span className="status-chip chip-medium">{{ vendor_commission: "Vendor incentive", other_receivable: "Expected", invoice: "Invoice", milestone: "Milestone" }[row.source_type] || row.source_type}</span></td>
                <td className="p-3"><div className="font-semibold">{row.vendor_name || row.client_name || "—"}</div><div className="text-xs text-[var(--ink-2)]">{row.project_name || "No project"}</div></td>
                <td className="p-3"><div>{row.name || "Collection"}</div>
                  {row.reminder_date && row.status !== "received" && <div className="text-[10px] text-[var(--ink-3)]" data-testid={`collection-reminder-${row.id}`}>Reminder {formatDate(row.reminder_date)} {row.reminder_time || "10:00"}{row.repeat_every && row.repeat_every !== "none" ? ` · repeats ${row.repeat_every}` : ""}</div>}</td>
                <td className="p-3"><span className={`status-chip chip-${row.status}`}>{(row.status || "").replaceAll("_", " ")}</span></td>
                <td className="p-3 text-right font-mono font-semibold">
                  {isHistory ? (
                    <>
                      <div className="text-[var(--success)]">{CURRENCY(row.received_amount)}</div>
                      {row.outstanding > 0 && <div className="text-[10px] font-normal text-[var(--warning)]">{CURRENCY(row.outstanding)} still due</div>}
                    </>
                  ) : (
                    <>
                      <div>{CURRENCY(row.outstanding)}</div>
                      {row.received_amount > 0 && <div className="text-[10px] font-normal text-[var(--ink-3)]">of {CURRENCY(row.amount)}</div>}
                    </>
                  )}
                </td>
                <td className="p-3 text-right whitespace-nowrap">
                  {row.outstanding > 0 && <button type="button" className="btn-primary text-xs mr-2"
                    onClick={() => openReceipt(row)} disabled={!banks.length || !incomeAccounts.length}>
                    <Money size={12} /> Receive
                  </button>}
                  {row.outstanding > 0 && (
                    <button type="button" className="btn-ghost text-xs mr-2" data-testid={`collection-remind-${row.id}`}
                      title="Payment reminder PDF + WhatsApp (posts nothing)"
                      onClick={() => startReminder({ source_type: row.source_type, source_id: row.id,
                        party: row.vendor_name || row.client_name, outstanding: row.outstanding,
                        due_by: row.due_date && row.status !== "overdue" ? row.due_date : undefined })}>
                      <BellRinging size={12} /> Remind
                    </button>
                  )}
                  <RowActions label={row.name || "collection"} testid={`collection-actions-${row.id}`} actions={[
                    { label: "Receipts & entries", icon: Notebook, hidden: !(row.received_amount > 0),
                      onSelect: () => setEntriesFor(row), testid: `collection-entries-${row.id}` },
                    { label: "Open vendor", icon: CaretRight, hidden: !row.vendor_id, onSelect: () => navigate(`/vendors/${row.vendor_id}`) },
                    { label: "Open project", icon: CaretRight, hidden: row.vendor_id || !row.project_id, onSelect: () => navigate(`/projects/${row.project_id}`) },
                    { label: "Edit", icon: PencilSimple, hidden: !(row.origin === "manual_expected" && row.received_amount <= 0), onSelect: () => editPlan(row) },
                    { label: "Cancel this collection", icon: Trash, danger: true, divider: true,
                      hidden: !(row.origin === "manual_expected" && row.received_amount <= 0), onSelect: () => cancelPlan(row) },
                  ]} />
                </td>
              </tr>
            ))}
            {entriesFor && <CollectionEntries row={entriesFor} onClose={() => setEntriesFor(null)} onChanged={() => { load(); onSaved && onSaved(); }} />}
            {rows.length === 0 && (
              <tr><td colSpan={7} className="p-10 text-center text-[var(--ink-3)]">
                {isHistory ? "Nothing received yet in this view." : filter === "active" && !term
                  ? "Nothing left to collect. Every expected payment has been received."
                  : "No collections match this view."}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {collecting && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <form onSubmit={saveReceipt} className="bg-white border border-[var(--line)] w-full max-w-lg p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="overline">RECORD COLLECTION RECEIPT</div>
                <h3 className="font-display text-xl mt-1">{collecting.name || "Collection"}</h3>
                <p className="text-sm text-[var(--ink-2)] mt-1">{collecting.vendor_name || collecting.client_name || collecting.project_name || "Other receivable"} · {CURRENCY(collecting.outstanding)} pending</p>
              </div>
              <button type="button" className="btn-ghost" onClick={() => setCollecting(null)} aria-label="Close"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-xs">Receipt date<input required type="date" className="input-flat mt-1 w-full" value={receipt.date} onChange={(e) => setReceipt({ ...receipt, date: e.target.value })} /></label>
              <label className="text-xs">Amount received<input required min="0.01" max={collecting.outstanding} step="0.01" type="number" className="input-flat mt-1 w-full" value={receipt.amount} onChange={(e) => setReceipt({ ...receipt, amount: e.target.value })} /></label>
              <label className="text-xs">Payment method<select className="input-flat mt-1 w-full" value={receipt.payment_method} onChange={(e) => { const method = e.target.value; const compatible = compatibleAccount(banks, method); setReceipt({ ...receipt, payment_method: method, bank_account_id: compatible?.id || receipt.bank_account_id }); }}><option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option><option value="cash">Cash</option><option value="cheque">Cheque</option><option value="online">Online</option><option value="other">Other</option></select></label>
              <label className="text-xs">Received into<SearchSelect required className="input-flat mt-1 w-full" value={receipt.bank_account_id} onChange={(e) => { const account = banks.find((a) => a.id === e.target.value); setReceipt({ ...receipt, bank_account_id: e.target.value, payment_method: methodForAccount(account) }); }}><option value="" disabled>Select cash / bank</option>{banks.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</SearchSelect></label>
              <label className="text-xs">Income account<SearchSelect required className="input-flat mt-1 w-full" value={receipt.income_account_id} onChange={(e) => setReceipt({ ...receipt, income_account_id: e.target.value })}><option value="" disabled>Select income account</option>{incomeAccounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</SearchSelect></label>
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
    date: dateForInput(new Date()), amount: "",
    ...(kind === "income" ? { income_account_id: "", bank_account_id: "", client_id: "", project_id: "", vendor_id: "", employee_id: "" }
                          : { expense_account_id: "", paid_from_account_id: "", vendor_id: "", project_id: "", client_id: "", employee_id: "", gst: "" }),
    payment_method: "bank_transfer", reference: "", notes: "",
  }));

  useEffect(() => {
    if (banks.length && !form.bank_account_id && !form.paid_from_account_id) {
      const method = methodForAccount(banks[0]);
      if (kind === "income") setForm((s) => ({ ...s, bank_account_id: banks[0].id, payment_method: method }));
      else setForm((s) => ({ ...s, paid_from_account_id: banks[0].id, payment_method: method }));
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
          className={`btn-primary ${kind === "income" ? "bg-[var(--success)]" : "bg-[var(--danger)]"}`} data-testid={`${kind}-new-btn`}>
          <Plus size={14} /> {showForm && showForm.kind === kind ? "Cancel" : `New ${kind}`}
        </button>
      </div>

      {showForm && showForm.kind === kind && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3" data-testid={`${kind}-form`}>
          <input type="date" required className="input-flat" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <input type="number" min="0" required step="0.01" className="input-flat" placeholder="Amount"
            value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid={`${kind}-amount`} />
          <SearchSelect className="input-flat" value={kind === "income" ? form.income_account_id : form.expense_account_id}
            onChange={(e) => setForm({ ...form, [kind === "income" ? "income_account_id" : "expense_account_id"]: e.target.value })}
            data-testid={`${kind}-acc`}>
            <option value="" disabled>Select {kind} account</option>
            {txnAccs.filter((a) => kind !== "expense" || a.name?.trim().toLowerCase() !== "employee salary")
              .map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </SearchSelect>
          <SearchSelect className="input-flat" value={kind === "income" ? form.bank_account_id : form.paid_from_account_id}
            onChange={(e) => { const account = banks.find((a) => a.id === e.target.value); setForm({ ...form, [kind === "income" ? "bank_account_id" : "paid_from_account_id"]: e.target.value, payment_method: methodForAccount(account) }); }}
            data-testid={`${kind}-bank`}>
            <option value="" disabled>Cash / Bank</option>
            {banks.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </SearchSelect>

          {kind === "income" && (
            <>
              <SearchSelect className="input-flat" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
                <option value="">— Client (optional) —</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">— Project (optional) —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.vendor_id || ""} onChange={(e) => setForm({ ...form, vendor_id: e.target.value })} data-testid="income-vendor-select">
                <option value="">— Vendor (optional) —</option>
                {(vendors || []).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.employee_id || ""} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="income-employee-select">
                <option value="">— Employee (optional) —</option>
                {(employees || []).map((emp) => <option key={emp.id} value={emp.id}>{empName(emp)}{emp.employee_id ? ` · ${emp.employee_id}` : ""}</option>)}
              </SearchSelect>
            </>
          )}

          {kind === "expense" && (
            <>
              <div className="md:col-span-3 text-xs text-[var(--ink-2)] border-l-2 border-[var(--accent)] pl-3">
                Employee salary is paid from Employee → Salary &amp; Bank → Run Payroll so attendance, employee history and Accounting use one transaction.
              </div>
              <SearchSelect
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
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">— Project (optional) —</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.client_id || ""} onChange={(e) => setForm({ ...form, client_id: e.target.value })} data-testid="expense-client-select">
                <option value="">— Client (optional) —</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </SearchSelect>
              <SearchSelect className="input-flat" value={form.employee_id || ""} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="expense-employee-select">
                <option value="">— Employee (optional) —</option>
                {(employees || []).map((emp) => <option key={emp.id} value={emp.id}>{empName(emp)}{emp.employee_id ? ` · ${emp.employee_id}` : ""}</option>)}
              </SearchSelect>
              <input type="number" min="0" step="0.01" className="input-flat" placeholder="GST amount (optional)" value={form.gst || ""} onChange={(e) => setForm({ ...form, gst: e.target.value })} />
            </>
          )}

          <select aria-label="Payment method" className="input-flat" value={form.payment_method} onChange={(e) => { const method = e.target.value; const compatible = compatibleAccount(banks, method); setForm({ ...form, payment_method: method, [kind === "income" ? "bank_account_id" : "paid_from_account_id"]: compatible?.id || (kind === "income" ? form.bank_account_id : form.paid_from_account_id) }); }}>
            {["cash", "bank_transfer", "upi", "cheque", "credit_card", "online", "other"].map((m) => <option key={m}>{m}</option>)}
          </select>
          <input className="input-flat" placeholder="Reference no." value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
          <input className="input-flat md:col-span-3" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <button className="btn-primary md:col-span-3" data-testid={`${kind}-submit`}>Save {kind}</button>
        </form>
      )}

      <div className="border border-[var(--line)] overflow-x-auto">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)] text-[10px] font-mono uppercase tracking-wider text-[var(--ink-2)]">
            <tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">Narration</th><th className="p-2 text-left">Account</th><th className="p-2 text-left">Reference</th><th className="p-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            {journal.map((j) => {
              const primary = j.lines?.find((l) => l.account_type === (kind === "income" ? "income" : "expense"));
              return (
                <tr key={j.id} onClick={() => setDetail(j)}
                  className="border-t border-[var(--line-soft)] cursor-pointer hover:bg-[var(--surface-2)]"
                  data-testid={`${kind}-row-${j.id}`}>
                  <td className="p-2 font-mono text-xs">{formatDate(j.date)}</td>
                  <td className="p-2">
                    {j.narration}
                    {j.source?.endsWith("_reversal") && (
                      <span className="ml-2 text-[10px] text-[var(--accent-strong)]">{j.undone ? "REVERSAL UNDONE" : "REVERSAL"}</span>
                    )}
                    {j.source?.endsWith("_reinstatement") && (
                      <span className="ml-2 text-[10px] text-[var(--success)]">REINSTATED</span>
                    )}
                  </td>
                  <td className="p-2 text-xs">{primary?.account_name || "—"}</td>
                  <td className="p-2 font-mono text-xs">{j.reference || "—"}</td>
                  <td className={`p-2 text-right font-mono font-semibold ${kind === "income" ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                    {CURRENCY(j.total)}
                  </td>
                </tr>
              );
            })}
            {journal.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-[var(--ink-3)]">No {kind} entries yet.</td></tr>}
          </tbody>
        </table></div>
      </div>
      {page?.total > page?.limit && (
        <div className="flex items-center justify-between text-xs text-[var(--ink-2)]">
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
    if (account.active !== false && !await confirmAction(`Deactivate “${account.name}”? Its history will remain available.`)) return;
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
  // Opening money for an account that already has entries (the field itself
  // locks once there is activity): posts a dated adjustment journal.
  const addOpening = async (account) => {
    const values = await askForm({
      title: `Opening balance — ${account.name}`,
      body: "Money the account already held before you started recording it here. It is dated before the account's first entry unless you pick a date, and can be reversed from the ledger.",
      fields: [
        { name: "amount", label: "Amount (₹)", type: "number", required: true, placeholder: "e.g. 10336" },
        { name: "date", label: "As on date (optional)", type: "date" },
        { name: "note", label: "Note (optional)", placeholder: "e.g. balance per bank statement" },
      ],
      confirmLabel: "Add opening balance",
    });
    if (!values) return;
    try {
      await api.post(`/accounts/${account.id}/opening-adjustment`, {
        amount: Number(values.amount), date: values.date || null, note: values.note || null,
      });
      toast.success(`Opening balance added to ${account.name}`);
      const params = new URLSearchParams({ include_balances: "true" });
      if (showInactive) params.set("include_inactive", "true");
      setAccounts((await api.get(`/accounts?${params.toString()}`)).data);
      onReload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not add opening balance");
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
        <label className="flex items-center gap-2 text-xs text-[var(--ink-2)]">
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
          <select aria-label="Account type" className="input-flat" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
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
            <thead className="text-[10px] font-mono uppercase text-[var(--ink-3)]">
              <tr><th className="p-2" /><th className="p-2 text-left">Code</th><th className="p-2 text-left">Account</th><th className="p-2 text-right">Current balance</th><th className="p-2 text-right">Actions</th></tr>
            </thead>
            <tbody>
              {list.map((a) => {
                const isFav = favIds.includes(a.id);
                return (
                  <tr key={a.id}
                    onClick={() => onOpenAccount && onOpenAccount(a)}
                    className={`border-b border-[var(--line-soft)] cursor-pointer hover:bg-[var(--surface-2)] transition-colors group ${a.active === false ? "opacity-50" : ""}`}
                    data-testid={`account-${a.id}`}>
                    <td className="p-2 w-8">
                      <button onClick={(e) => toggleFav(a, e)}
                        className={`transition-colors ${isFav ? "text-[var(--accent)]" : "text-[var(--line-strong)] hover:text-[var(--accent-strong)]"}`}
                        title={isFav ? "Unpin from Favourites" : "Pin to Favourites"}
                        data-testid={`fav-toggle-${a.id}`}>
                        <Star size={14} weight={isFav ? "fill" : "regular"} />
                      </button>
                    </td>
                    <td className="p-2 font-mono text-xs w-20">{a.code || "—"}</td>
                    <td className="p-2 font-semibold group-hover:text-[var(--accent-strong)]">
                      {a.name}
                      {a.active === false && <span className="ml-2 text-[10px] text-[var(--warning)]">INACTIVE</span>}
                    </td>
                    <td className="p-2 text-right font-mono text-xs text-[var(--ink-2)]">{CURRENCY(a.current_balance ?? a.opening_balance)}</td>
                    <td className="p-2 text-right w-32">
                      <span className="inline-flex items-center justify-end gap-1">
                        {a.is_bank && <Bank size={12} className="text-[var(--accent-strong)] mr-1" />}
                        <RowActions label={a.name} testid={`account-actions-${a.id}`} actions={[
                          { label: "Edit account", icon: PencilSimple, onSelect: () => startEdit(a, { stopPropagation() {}, preventDefault() {} }), testid: `account-edit-${a.id}` },
                          { label: "Add opening balance", icon: Plus, hidden: a.active === false || a.type === "income" || a.type === "expense",
                            onSelect: () => addOpening(a), testid: `account-opening-${a.id}` },
                          { label: a.active === false ? "Restore account" : "Deactivate account", icon: a.active === false ? ArrowCounterClockwise : Archive,
                            danger: a.active !== false, onSelect: () => toggleActive(a, { stopPropagation() {}, preventDefault() {} }), testid: `account-active-${a.id}` },
                        ]} />
                        <CaretRight size={12} className="text-[var(--ink-3)]" />
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
      <div className="flex flex-wrap justify-between items-center gap-2">
        <div className="overline">FINANCIAL REPORTS</div>
        <div className="flex flex-wrap items-center gap-2">
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
            <div className="text-xs text-[var(--ink-2)] mt-0.5">{pl.period_label || "Selected period"}</div>
          </div>
          <div className="text-right">
            <div className="overline">NET</div>
            <div className={`font-display font-bold text-3xl ${pl.net_profit >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
              {CURRENCY(pl.net_profit)}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ReportBlock title="INCOME" rows={pl.income} total={pl.total_income} tint="#1D633E" testid="pl-income" />
          <ReportBlock title="EXPENSE" rows={pl.expense} total={pl.total_expense} tint="#B22B22" testid="pl-expense" />
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
          <thead className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-2)]">
            <tr><th className="p-2 text-left">Account</th><th className="p-2 text-left">Type</th><th className="p-2 text-right">Debit</th><th className="p-2 text-right">Credit</th><th className="p-2 text-right">Balance</th></tr>
          </thead>
          <tbody>
            {tb.rows.map((r) => (
              <tr key={r.account_id} className="border-t border-[var(--line-soft)]">
                <td className="p-2">{r.account_name}</td>
                <td className="p-2 text-xs uppercase text-[var(--ink-2)]">{r.account_type}</td>
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
      {rows.length === 0 && <div className="text-xs text-[var(--ink-3)]">No entries.</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center justify-between text-sm border-b border-[var(--line-soft)] py-1.5">
          <span>{r.name}</span>
          <span className="font-mono">{CURRENCY(r.amount)}</span>
        </div>
      ))}
      <div className="flex items-center justify-between text-sm font-semibold pt-2 mt-2 border-t-2 border-[var(--ink)]">
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

// Several things at once: e.g. one project + its lighting, fan and ceiling vendors
// -> how much vendor incentive and consultancy income came from each.
function MultiPick({ label, options, value, onChange, testid }) {
  const left = options.filter((o) => !value.includes(o.id));
  return (
    <div className="space-y-1" data-testid={testid}>
      <select className="input-flat w-full text-sm" value="" aria-label={`Add ${label}`}
        onChange={(e) => e.target.value && onChange([...value, e.target.value])}>
        <option value="">+ {label}</option>
        {left.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
      <div className="flex flex-wrap gap-1">
        {value.map((id) => (
          <button key={id} type="button" onClick={() => onChange(value.filter((x) => x !== id))}
            className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--hover)] text-[var(--ink)] hover:bg-[var(--danger-soft)]" title="Remove">
            {options.find((o) => o.id === id)?.label || id} ×
          </button>
        ))}
      </div>
    </div>
  );
}

function CombinedLedger({ clients, vendors, projects, accounts, fy, fromDate, toDate }) {
  const [sel, setSel] = useState({ project_ids: [], vendor_ids: [], client_ids: [], account_ids: [] });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const any = Object.values(sel).some((v) => v.length);
  useEffect(() => {
    if (!any) { setData(null); return; }
    const p = new URLSearchParams();
    Object.entries(sel).forEach(([k, v]) => v.length && p.set(k, v.join(",")));
    if (fromDate || toDate) { if (fromDate) p.set("from_date", fromDate); if (toDate) p.set("to_date", toDate); }
    else if (fy) p.set("fy", fy);
    setLoading(true);
    api.get(`/accounting/ledger/combined?${p.toString()}`).then(({ data: d }) => setData(d))
      .catch((e) => toast.error(e?.response?.data?.detail || "Could not load the ledger"))
      .finally(() => setLoading(false));
  }, [sel, fy, fromDate, toDate]);   // eslint-disable-line react-hooks/exhaustive-deps
  const accountCols = data ? [...new Set(data.by_vendor.flatMap((v) => Object.keys(v.accounts)))] : [];
  const set = (k) => (v) => setSel((s0) => ({ ...s0, [k]: v }));
  return (
    <div className="space-y-4" data-testid="combined-ledger">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <MultiPick label="Project" testid="combined-projects" value={sel.project_ids} onChange={set("project_ids")} options={projects.map((x) => ({ id: x.id, label: x.name }))} />
        <MultiPick label="Vendor" testid="combined-vendors" value={sel.vendor_ids} onChange={set("vendor_ids")} options={vendors.map((x) => ({ id: x.id, label: x.name }))} />
        <MultiPick label="Client" testid="combined-clients" value={sel.client_ids} onChange={set("client_ids")} options={clients.map((x) => ({ id: x.id, label: x.name }))} />
        <MultiPick label="Account" testid="combined-accounts" value={sel.account_ids} onChange={set("account_ids")}
          options={accounts.filter((a) => ["income", "expense"].includes(a.type) && a.active !== false).map((a) => ({ id: a.id, label: a.name }))} />
      </div>
      <p className="text-[11px] text-[var(--ink-3)]">Pick any mix: a project plus several vendors shows what each vendor brought in on that project. Choices of the same kind are added together; different kinds narrow the result.</p>
      {!any && <div className="text-sm text-[var(--ink-3)] py-6 text-center border border-dashed border-[var(--line)]">Choose at least one project, vendor, client or account.</div>}
      {loading && <div className="overline">LOADING…</div>}
      {data && !loading && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <KPI label="Income" value={CURRENCY(data.totals.income)} Icon={ArrowDown} tint="#1D633E" />
            <KPI label="Expense" value={CURRENCY(data.totals.expense)} Icon={ArrowUp} tint="#B22B22" />
            <KPI label="Net" value={CURRENCY(data.totals.net)} Icon={ChartLine} tint="#0A0A0A" />
          </div>
          {data.by_vendor.length > 0 && (
            <div className="border border-[var(--line)] overflow-x-auto">
              <table className="w-full text-sm" data-testid="combined-by-vendor">
                <thead className="bg-[var(--surface-2)]"><tr className="overline text-left">
                  <th className="p-2">By vendor</th>{accountCols.map((c) => <th key={c} className="p-2 text-right">{c}</th>)}<th className="p-2 text-right">Income</th><th className="p-2 text-right">Expense</th>
                </tr></thead>
                <tbody>{data.by_vendor.map((v) => (
                  <tr key={v.vendor_id || "none"} className="border-t border-[var(--line-soft)]">
                    <td className="p-2 font-semibold">{v.vendor_name}</td>
                    {accountCols.map((c) => <td key={c} className="p-2 text-right tabular-nums">{v.accounts[c] ? CURRENCY(v.accounts[c]) : "—"}</td>)}
                    <td className="p-2 text-right tabular-nums text-[var(--success)]">{CURRENCY(v.income)}</td>
                    <td className="p-2 text-right tabular-nums">{v.expense ? CURRENCY(v.expense) : "—"}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="border border-[var(--line)]"><table className="w-full text-sm" data-testid="combined-by-project">
              <thead className="bg-[var(--surface-2)]"><tr className="overline text-left"><th className="p-2">By project</th><th className="p-2 text-right">Income</th><th className="p-2 text-right">Expense</th></tr></thead>
              <tbody>{data.by_project.map((x) => <tr key={x.project_id || "none"} className="border-t border-[var(--line-soft)]"><td className="p-2">{x.project_name}</td><td className="p-2 text-right tabular-nums">{CURRENCY(x.income)}</td><td className="p-2 text-right tabular-nums">{x.expense ? CURRENCY(x.expense) : "—"}</td></tr>)}</tbody>
            </table></div>
            <div className="border border-[var(--line)]"><table className="w-full text-sm" data-testid="combined-by-account">
              <thead className="bg-[var(--surface-2)]"><tr className="overline text-left"><th className="p-2">By account</th><th className="p-2 text-right">Amount</th></tr></thead>
              <tbody>{data.by_account.map((x) => <tr key={x.account_id} className="border-t border-[var(--line-soft)]"><td className="p-2">{x.account_name}<span className="text-[10px] text-[var(--ink-3)] ml-1">{x.type}</span></td><td className="p-2 text-right tabular-nums">{CURRENCY(x.amount)}</td></tr>)}</tbody>
            </table></div>
          </div>
          <div className="border border-[var(--line)] overflow-x-auto"><table className="w-full text-sm min-w-[720px]">
            <thead className="bg-[var(--surface-2)]"><tr className="overline text-left"><th className="p-2">Date</th><th className="p-2">Entry</th><th className="p-2">Project</th><th className="p-2">Vendor / client</th><th className="p-2 text-right">Income</th><th className="p-2 text-right">Expense</th></tr></thead>
            <tbody>{data.entries.map((e) => (
              <tr key={e.id} className="border-t border-[var(--line-soft)]">
                <td className="p-2 text-xs whitespace-nowrap">{formatDate(e.date)}</td>
                <td className="p-2"><div>{e.narration}</div><div className="text-[10px] text-[var(--ink-3)]">{sourceLabel(e.source)}{e.share < 1 ? ` · ${Math.round(e.share * 100)}% of this receipt is for the chosen project(s)` : ""}</div></td>
                <td className="p-2 text-xs">{e.project || "—"}</td>
                <td className="p-2 text-xs">{e.vendor || e.client || "—"}</td>
                <td className="p-2 text-right tabular-nums">{e.income ? CURRENCY(e.income) : "—"}</td>
                <td className="p-2 text-right tabular-nums">{e.expense ? CURRENCY(e.expense) : "—"}</td>
              </tr>))}
              {data.entries.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-[var(--ink-3)]">Nothing booked for this selection in this period.</td></tr>}
            </tbody>
          </table></div>
        </>
      )}
    </div>
  );
}

function LedgersView({ clients, vendors, employees, projects, accounts = [], fy, fromDate, toDate }) {
  const [entityType, setEntityType] = useState("client");
  const [entityId, setEntityId] = useState("");
  const [ledger, setLedger] = useState(null);
  const [loading, setLoading] = useState(false);

  const options = {
    client:   clients.map((c) => ({ id: c.id, label: c.name })),
    vendor:   vendors.map((v) => ({ id: v.id, label: v.name })),
    employee: employees.map((e) => ({ id: e.id, label: `${empName(e)}${e.employee_id ? ` · ${e.employee_id}` : ""}` })),
    project:  projects.map((p) => ({ id: p.id, label: p.name })),
  }[entityType] || [];

  useEffect(() => { setEntityId(""); setLedger(null); }, [entityType]);

  useEffect(() => {
    if (!entityId || entityType === "combined") { setLedger(null); return; }
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
        <div className="flex border border-[var(--line)] rounded-none overflow-hidden">
          {ENTITY_TYPES.map((e) => (
            <button
              key={e.id}
              onClick={() => setEntityType(e.id)}
              data-testid={`ledger-type-${e.id}`}
              className={`px-3 py-1.5 text-xs ${entityType === e.id ? "bg-[var(--accent)] text-white" : "text-[var(--ink-2)] hover:bg-[var(--hover)]"}`}
            >{e.label}</button>
          ))}
          <button onClick={() => setEntityType("combined")} data-testid="ledger-type-combined"
            className={`px-3 py-1.5 text-xs ${entityType === "combined" ? "bg-[var(--accent)] text-white" : "text-[var(--ink-2)] hover:bg-[var(--hover)]"}`}>
            Combined
          </button>
        </div>
        {entityType !== "combined" && <select aria-label="Entity id"
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          className="border border-[var(--line)] px-3 py-1.5 text-sm bg-white min-w-[280px]"
          data-testid="ledger-entity-select"
        >
          <option value="">Select {ENTITY_TYPES.find((e) => e.id === entityType)?.label}…</option>
          {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>}
      </div>
      {entityType === "combined" && (
        <CombinedLedger clients={clients} vendors={vendors} projects={projects} accounts={accounts}
          fy={fy} fromDate={fromDate} toDate={toDate} />
      )}

      {loading && <div className="overline">LOADING LEDGER…</div>}
      {!loading && !ledger && entityId && <div className="text-sm text-[var(--ink-3)]">No data.</div>}
      {!loading && ledger && (
        <div className="space-y-4" data-testid="ledger-body">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
            <div className="card-flat"><div className="overline">Opening</div>
              <div className="font-mono text-lg" data-testid="ledger-opening">{CURRENCY(ledger.opening_balance)}</div></div>
            <div className="card-flat"><div className="overline">Inflow</div>
              <div className="font-mono text-lg text-[var(--success)]" data-testid="ledger-inflow">{CURRENCY(ledger.inflow)}</div></div>
            <div className="card-flat"><div className="overline">Outflow</div>
              <div className="font-mono text-lg text-[var(--danger)]" data-testid="ledger-outflow">{CURRENCY(ledger.outflow)}</div></div>
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
              <thead className="text-[var(--ink-2)] border-b border-[var(--line-soft)]">
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
                  <tr><td colSpan="6" className="text-[var(--ink-3)] py-3 italic">No transactions in period.</td></tr>
                )}
                {(ledger.entries || []).map((e) => (
                  <tr key={e.id} className="border-b border-[var(--hover)]" data-testid="ledger-row">
                    <td className="py-1.5 font-mono text-xs">{formatDate(e.date)}</td>
                    <td className="py-1.5">{e.narration}</td>
                    <td className="py-1.5 text-xs text-[var(--ink-2)]">{e.source || "-"}</td>
                    <td className="py-1.5 text-right font-mono text-[var(--success)]">{e.inflow ? CURRENCY(e.inflow) : "-"}</td>
                    <td className="py-1.5 text-right font-mono text-[var(--danger)]">{e.outflow ? CURRENCY(e.outflow) : "-"}</td>
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
  if (data.error) return <div className="card-flat text-[var(--danger)]">{data.error}</div>;
  const passed = data.difference?.match_within_1pc;
  return (
    <div className="space-y-4" data-testid="validation-tab">
      <div className={`p-4 border ${passed ? "border-[var(--success)] bg-[var(--success-soft)]" : "border-[var(--danger)] bg-[var(--danger-soft)]"}`}>
        <div className="overline">{passed ? "PASS" : "REVIEW"}</div>
        <div className="text-sm mt-1">{data.recommendation}</div>
        <div className="text-xs text-[var(--ink-2)] mt-2">{data.period?.label}</div>
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
            <thead className="text-[var(--ink-2)] border-b border-[var(--line-soft)]">
              <tr><th className="text-left py-1">Invoice #</th><th className="text-left py-1">Date</th><th className="text-right py-1">Total</th></tr>
            </thead>
            <tbody>
              {data.diagnostics.orphan_paid_invoices.map((i) => (
                <tr key={i.id} className="border-b border-[var(--hover)]">
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
            <thead className="text-[var(--ink-2)] border-b border-[var(--line-soft)]">
              <tr><th className="text-left py-1">Date</th><th className="text-left py-1">Narration</th><th className="text-right py-1">Amount</th></tr>
            </thead>
            <tbody>
              {data.diagnostics.orphan_income_je.map((e) => (
                <tr key={e.id} className="border-b border-[var(--hover)]">
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

