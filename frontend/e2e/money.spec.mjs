// Money journeys: one authoritative source record, posted once, visible
// consistently in every linked module (invoice/collections, payroll,
// vendor commissions). API-driven so each linked record can be asserted.
import { test, expect } from "@playwright/test";
import { api, json, accounts, journals, balanced, listOf, today, uid, authFile, baseURL } from "./helpers.mjs";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "money logic is viewport independent");
});

test("invoice: issue, partial + full collection, idempotent retry, Cash/Bank guard", async ({ browser }) => {
  const ctx = await api("admin");
  const { cash, bank } = await accounts(ctx);
  expect(bank, "Bank - Primary seeded").toBeTruthy();
  const client = await json(ctx.post("/api/clients", { data: { name: `Client ${uid()}` } }));

  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", status: "draft", tax_rate: 18,
    items: [{ description: "Design development", quantity: 3, rate: 33.335 }],
  } }));
  expect([inv.subtotal, inv.tax, inv.total]).toEqual([100.01, 18, 118.01]);

  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  // Cash basis (default): sending an invoice is a document event, not money.
  const issue = await journals(ctx, { source: "invoice_issue", client_id: client.id });
  expect(issue, "sending posts no journal").toHaveLength(0);

  // Invoices are client documents. Expected and received money is managed by
  // the one Collections Due workflow, not by a second invoice-payment engine.
  const direct = await ctx.post("/api/accounting/collections/receive", { data: {
    source_type: "invoice", source_id: inv.id, amount: 10, date: today(),
    bank_account_id: cash.id, payment_method: "cash",
  } });
  expect(direct.status(), "a new cash-basis invoice must first be added to Collections Due").toBe(409);
  const incomeAccount = (await json(ctx.get("/api/accounts")))
    .find((a) => a.type === "income" && /consult/i.test(a.name) && a.active !== false);
  expect(incomeAccount, "consultancy income account exists").toBeTruthy();
  const due = await json(ctx.post("/api/accounting/receivables", { data: {
    invoice_id: inv.id, name: `Invoice ${inv.number}`, amount: inv.total,
    due_date: today(), income_account_id: incomeAccount.id,
  } }));

  // A "bank transfer" must never be booked into the Cash ledger.
  const wrong = await ctx.post("/api/accounting/collections/receive", { data: {
    source_type: "other_receivable", source_id: due.id, amount: 10, date: today(),
    bank_account_id: cash.id, payment_method: "bank_transfer",
  } });
  expect(wrong.status(), "bank_transfer into Cash is rejected").toBe(400);

  const pay = (amount, key) => ctx.post("/api/accounting/collections/receive", {
    headers: { "Idempotency-Key": key },
    data: { source_type: "other_receivable", source_id: due.id, amount, date: today(),
            bank_account_id: bank.id, payment_method: "bank_transfer", reference: inv.number },
  });
  const key = `e2e-${uid()}`;
  await json(pay(50, key));
  await pay(50, key); // double-click / network retry with the same key
  let receipts = (await journals(ctx, { client_id: client.id }))
    .filter((j) => !j.reversed);
  expect(receipts, "retry with same key posts once").toHaveLength(1);

  let fresh = (await json(ctx.get("/api/accounting/receivables"))).rows
    .find((r) => r.source_type === "other_receivable" && r.id === due.id);
  expect([fresh.status, fresh.received_amount]).toEqual(["partially_received", 50]);

  await json(pay(68.01, `e2e-${uid()}`));
  fresh = (await json(ctx.get("/api/accounting/receivables"))).rows
    .find((r) => r.source_type === "other_receivable" && r.id === due.id);
  expect([fresh.status, fresh.received_amount, fresh.outstanding]).toEqual(["received", 118.01, 0]);
  receipts = (await journals(ctx, { client_id: client.id }))
    .filter((j) => !j.reversed);
  expect(receipts).toHaveLength(2);
  for (const je of receipts) {
    expect(balanced(je)).toBe(true);
    expect(je.lines.some((l) => l.account_id === bank.id && l.debit > 0), "bank debited").toBe(true);
    expect(je.lines.some((l) => l.account_id === cash.id), "cash untouched").toBe(false);
  }
  const total = receipts.reduce((s, j) => s + j.total, 0);
  expect(Math.round(total * 100)).toBe(11801);

  // Over-collection is refused once the invoice is settled.
  const over = await pay(1, `e2e-${uid()}`);
  expect(over.status()).toBeGreaterThanOrEqual(400);

  // The invoice list mirrors the amount received by its linked collection.
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/invoices");
  await expect(page.getByRole("row", { name: new RegExp(inv.number) })).toContainText("118.01");
  await ctx.dispose();
});

test("payroll: bank salary posts once to the chosen bank, with name, and can be reversed", async () => {
  const ctx = await api("admin");
  const { cash, bank } = await accounts(ctx);
  const emp = await json(ctx.post("/api/employees", { data: {
    first_name: "Rahul", last_name: `QA${uid()}`, salary: { basic: 20000 },
  } }));
  const period = { year: 2026, month: 10 };
  const pay = (data) => ctx.post(`/api/employees/${emp.id}/pay-salary`, { data: {
    ...period, apply_attendance_deductions: false, payment_date: today(), ...data } });

  const wrong = await pay({ paid_from_account_id: cash.id, payment_method: "bank_transfer" });
  expect(wrong.status(), "bank_transfer from Cash is rejected").toBe(400);

  const ok = await json(pay({ paid_from_account_id: bank.id, payment_method: "bank_transfer",
                              reference: "NEFT-QA-1" }));
  expect(ok.run.paid_from_account_id).toBe(bank.id);
  expect(ok.run.payment_method).toBe("bank_transfer");
  const dup = await pay({ paid_from_account_id: bank.id, payment_method: "bank_transfer" });
  expect(dup.status(), "no duplicate salary for the same period").toBe(400);

  const posted = (await journals(ctx, { source: "payroll", employee_id: emp.id })).filter((j) => !j.reversed);
  expect(posted).toHaveLength(1);
  expect(balanced(posted[0])).toBe(true);
  expect(posted[0].narration).toContain("Rahul");
  expect(posted[0].lines.find((l) => l.credit > 0).account_id).toBe(bank.id);

  const runs = listOf(await json(ctx.get(`/api/payroll/runs?employee_id=${emp.id}`)), "items", "runs");
  expect(runs.filter((r) => r.employee_id === emp.id && r.status === "paid")).toHaveLength(1);

  // Correction: reverse, then the period can be paid again correctly.
  await json(ctx.post(`/api/payroll/runs/${ok.run.id}/reverse`, { data: { reason: "E2E correction" } }));
  const active = (await journals(ctx, { source: "payroll", employee_id: emp.id })).filter((j) => !j.reversed);
  expect(active).toHaveLength(0);
  await json(pay({ paid_from_account_id: bank.id, payment_method: "bank_transfer", reference: "NEFT-QA-2" }));
  await ctx.dispose();
});

test("payroll: a paid salary is edited in place (bonus included) and the old entry leaves the books", async ({ browser }) => {
  const ctx = await api("admin");
  const { cash } = await accounts(ctx);
  const emp = await json(ctx.post("/api/employees", { data: {
    first_name: "Meet", last_name: `QA${uid()}`, salary: { basic: 12000 },
  } }));
  const paid = await json(ctx.post(`/api/employees/${emp.id}/pay-salary`, { data: {
    year: 2026, month: 10, apply_attendance_deductions: false, payment_date: "2026-10-28",
    paid_from_account_id: cash.id, payment_method: "cash",
  } }));
  expect(paid.run.net).toBe(12000);

  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto(`/employees/${emp.id}`);
  await page.getByRole("button", { name: "Salary & Bank" }).first().click();
  await page.getByTestId(`payment-actions-${paid.run.id}`).click();
  await page.getByRole("menuitem", { name: "Edit payment" }).click();
  await page.getByTestId("form-field-net").fill("15000");
  await page.getByTestId("form-field-bonus").fill("3000");
  await page.getByTestId("form-field-payment_date").fill("2026-10-31");
  await page.getByTestId("confirm-ok").click();
  const history = page.getByTestId("payment-history-table");
  await expect(history).toContainText("15,000");
  await expect(history).toContainText("bonus");
  await expect(history).not.toContainText("12,000");

  const live = await journals(ctx, { source: "payroll", employee_id: emp.id });
  expect(live, "only the corrected salary is in the books").toHaveLength(1);
  expect(live[0].date).toBe("2026-10-31");
  expect(live[0].total).toBe(15000);
  const reversals = await journals(ctx, { source: "payroll_reversal", employee_id: emp.id });
  expect(reversals, "no visible reversal line").toHaveLength(0);
  await ctx.dispose();
});

test("vendor commission: planned posts nothing, partial receipt posts once to bank", async ({ browser }) => {
  const ctx = await api("admin");
  const { cash, bank } = await accounts(ctx);
  const vendor = await json(ctx.post("/api/vendors", { data: { name: `Dhrumil QA ${uid()}` } }));
  const vid = vendor.id || vendor.vendor?.id;
  const planned = await json(ctx.post(`/api/vendors/${vid}/commissions`, { data: {
    amount: 5000, due_date: "2026-10-31", recognition: "planned", reference: "ABC Residence",
  } }));
  const cid = planned.id || planned.commission?.id;
  expect(cid).toBeTruthy();
  expect(await journals(ctx, { vendor_id: vid }), "planning never posts").toHaveLength(0);

  const receive = (amount, data = {}, key = `e2e-${uid()}`) => ctx.post("/api/accounting/collections/receive", {
    headers: { "Idempotency-Key": key },
    data: { source_type: "vendor_commission", source_id: cid, amount, date: today(),
            bank_account_id: bank.id, payment_method: "bank_transfer", ...data },
  });
  const wrong = await receive(100, { bank_account_id: cash.id });
  expect(wrong.status(), "bank_transfer into Cash rejected").toBe(400);

  const key = `e2e-${uid()}`;
  await json(receive(2000, {}, key));
  await receive(2000, {}, key);
  const posted = (await journals(ctx, { vendor_id: vid }))
    .filter((j) => !j.reversed && !String(j.source).endsWith("_reversal"));
  expect(posted, "retry posts once").toHaveLength(1);
  expect(balanced(posted[0])).toBe(true);
  expect(posted[0].lines.find((l) => l.debit > 0).account_id).toBe(bank.id);

  const rows = listOf(await json(ctx.get(`/api/vendors/${vid}/commissions`)), "items", "commissions", "rows");
  const row = rows.find((r) => r.id === cid);
  expect(row.received_amount).toBe(2000);
  // Stored key "invoiced" historically means "partly received"; users must see that wording.
  expect(row.status).toBe("invoiced");

  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto(`/vendors/${vid}`);
  await page.getByTestId("vendor-tab-commissions").click();
  await expect(page.getByTestId("commission-status").first()).toHaveText(/partially received/i);
  await ctx.dispose();
});

test("admin data check runs read-only and lists Cash/Bank mismatches", async ({ browser }) => {
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/accounting");
  await page.getByTestId("tab-validation").click();
  await page.getByTestId("run-data-check").click();
  await expect(page.getByTestId("check-method_account_mismatches")).toBeVisible();
  // Every journey above used matching method/account, so any listed row must
  // carry a correction instruction rather than being silently accepted.
  const table = page.getByTestId("mismatch-table");
  if (await table.count()) await expect(table).toContainText(/reverse|delete/i);
  expect(errors).toEqual([]);
});

test("employee advance: give 5,000 cash, recover 2,000 + 3,000 through payroll, reversal restores", async ({ browser }) => {
  const ctx = await api("admin");
  const { cash, bank, rows } = await accounts(ctx);
  const emp = await json(ctx.post("/api/employees", { data: {
    first_name: "Asha", last_name: `ADV${uid()}`, salary: { basic: 24000 },
  } }));
  const adv = await json(ctx.post(`/api/employees/${emp.id}/advances`, { data: {
    amount: 5000, date: today(), reason: "Medical emergency", bank_account_id: cash.id,
    payment_method: "cash", monthly_recovery: 2000,
  } }));
  expect(adv.outstanding).toBe(5000);
  const given = await journals(ctx, { source: "employee_advance", employee_id: emp.id });
  expect(given).toHaveLength(1);
  expect(balanced(given[0])).toBe(true);
  expect(given[0].lines.find((l) => l.credit > 0).account_id).toBe(cash.id);

  const pay = (month, recovered) => ctx.post(`/api/employees/${emp.id}/pay-salary`, { data: {
    year: 2026, month, apply_attendance_deductions: false, payment_date: today(),
    paid_from_account_id: bank.id, payment_method: "bank_transfer", advances_recovered: recovered } });

  const tooMuch = await pay(9, 6000);
  expect(tooMuch.status(), "cannot recover more than outstanding").toBe(400);

  const oct = await json(pay(9, 2000));
  expect(oct.run.net).toBe(22000);
  const je = oct.journal;
  expect(balanced(je)).toBe(true);
  const advAccount = rows.find((a) => a.name === "Employee Advances")
    || (await json(ctx.get("/api/accounts"))).find((a) => a.name === "Employee Advances");
  expect(je.lines.find((l) => l.account_id === advAccount.id).credit).toBe(2000);
  expect(je.lines.find((l) => l.account_id === bank.id).credit).toBe(22000);
  expect(je.lines.find((l) => l.debit > 0).debit, "salary expense is the full 24,000").toBe(24000);

  let list = await json(ctx.get(`/api/employees/${emp.id}/advances`));
  expect(list.outstanding).toBe(3000);
  const cancelBlocked = await ctx.post(`/api/employees/${emp.id}/advances/${adv.id}/cancel`);
  expect(cancelBlocked.status(), "partly recovered advance cannot be cancelled").toBe(409);

  const nov = await json(pay(10, 3000));
  list = await json(ctx.get(`/api/employees/${emp.id}/advances`));
  expect(list.outstanding).toBe(0);
  expect(list.items[0].status).toBe("closed");

  await json(ctx.post(`/api/payroll/runs/${nov.run.id}/reverse`, { data: { reason: "E2E" } }));
  list = await json(ctx.get(`/api/employees/${emp.id}/advances`));
  expect(list.outstanding, "reversal makes the recovered amount owed again").toBe(3000);

  // the employee page shows the outstanding balance
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto(`/employees/${emp.id}`);
  await page.getByTestId("emp-tab-Salary---Bank").click();
  await expect(page.getByTestId("advance-outstanding")).toContainText("3,000");
  await ctx.dispose();
});
