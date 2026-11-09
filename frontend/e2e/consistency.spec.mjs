// BR-010: the same money shows the same number on every screen for the same period.
import { test, expect } from "@playwright/test";
import { api, json, accounts, today, uid } from "./helpers.mjs";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "report logic is viewport independent");
});

const r2 = (n) => Math.round(Number(n || 0) * 100) / 100;
const monthRange = () => {
  const d = new Date(Date.now() + 5.5 * 3600e3);
  const y = d.getUTCFullYear(), m = d.getUTCMonth();
  const pad = (n) => String(n).padStart(2, "0");
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return { from: `${y}-${pad(m + 1)}-01`, to: `${y}-${pad(m + 1)}-${pad(last)}` };
};

async function daybook(ctx, params) {
  const out = [];
  for (let offset = 0; ; offset += 500) {
    const page = await json(ctx.get(`/api/journal-entries?${new URLSearchParams({ ...params, limit: "500", offset: String(offset) })}`));
    const items = Array.isArray(page) ? page : page.items;
    out.push(...items);
    if (items.length < 500) break;
  }
  return out;
}

test("dashboards, Collections Due, Daybook, P&L and trial balance agree", async () => {
  const ctx = await api("admin");
  const { bank } = await accounts(ctx);
  const consult = (await json(ctx.get("/api/accounts"))).find((a) => a.type === "income" && /consult/i.test(a.name));
  const client = await json(ctx.post("/api/clients", { data: { name: `Agree ${uid()}` } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 0, due_date: today(), items: [{ description: "Fee", quantity: 1, rate: 100000 }] } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));

  const dash0 = await json(ctx.get("/api/accounting/dashboard"));
  expect(dash0.kpis.unplanned_invoices.count, "a sent invoice outside Collections Due is flagged").toBeGreaterThanOrEqual(1);

  const recv = await json(ctx.post("/api/accounting/receivables", { data: {
    invoice_id: inv.id, amount: 100000, name: `Invoice ${inv.number}`, due_date: today(), income_account_id: consult.id } }));
  await json(ctx.post("/api/accounting/collections/receive", {
    headers: { "Idempotency-Key": `e2e-${uid()}` },
    data: { source_type: "other_receivable", source_id: recv.id, amount: 40000, date: today(),
            bank_account_id: bank.id, payment_method: "bank_transfer" } }));

  // one "money still to collect" everywhere
  const due = await json(ctx.get("/api/accounting/receivables"));
  const dash = await json(ctx.get("/api/accounting/dashboard"));
  const home = await json(ctx.get("/api/dashboard/stats"));
  expect(r2(dash.kpis.outstanding)).toBe(r2(due.totals.all));
  expect(r2(dash.kpis.overdue)).toBe(r2(due.totals.overdue));
  expect(r2(home.kpis.collection_due)).toBe(r2(due.totals.all));
  expect(due.rows.find((r) => r.id === recv.id).outstanding, "60,000 left, not the whole invoice").toBe(60000);

  // this month: dashboard = P&L = Daybook
  const { from, to } = monthRange();
  const pl = await json(ctx.get(`/api/accounting/reports/pl?from_date=${from}&to_date=${to}`));
  expect(r2(dash.kpis.income_month)).toBe(r2(pl.total_income));
  expect(r2(dash.kpis.expense_month)).toBe(r2(pl.total_expense));
  const month = await daybook(ctx, { from_date: from, to_date: to });
  const sum = (rows, type, sign) => r2(rows.flatMap((j) => j.lines).filter((l) => l.account_type === type)
    .reduce((s, l) => s + sign * (l.credit - l.debit), 0));
  expect(sum(month, "income", 1)).toBe(r2(pl.total_income));
  expect(sum(month, "expense", -1)).toBe(r2(pl.total_expense));

  // all time really is all time, and the books balance
  const all = await json(ctx.get("/api/accounting/reports/pl?fy=all"));
  const everything = await daybook(ctx, { fy: "all" });
  expect(sum(everything, "income", 1)).toBe(r2(all.total_income));
  const tb = await json(ctx.get("/api/accounting/reports/trial-balance?fy=all"));
  const rows = tb.rows || tb.accounts || tb.items || [];
  const dr = r2(rows.reduce((s, r) => s + Number(r.debit || 0), 0));
  const cr = r2(rows.reduce((s, r) => s + Number(r.credit || 0), 0));
  expect(dr, "trial balance debits = credits").toBe(cr);
  for (const je of everything) {
    const d = r2(je.lines.reduce((s, l) => s + l.debit, 0)), c = r2(je.lines.reduce((s, l) => s + l.credit, 0));
    expect(d, `entry ${je.id} balances`).toBe(c);
  }
  // the bank ledger matches the dashboard balance for that account
  const ledger = await json(ctx.get(`/api/accounting/ledger/account/${bank.id}?fy=all`));
  const dashBank = dash.kpis.cash_bank_by_account.find((b) => b.account_id === bank.id);
  const closing = ledger.closing_balance ?? ledger.closing ?? ledger.balance;
  expect(r2(closing)).toBe(r2(dashBank.balance));
  await ctx.dispose();
});
