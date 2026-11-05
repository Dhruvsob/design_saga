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
  const issue = await journals(ctx, { source: "invoice_issue", client_id: client.id });
  expect(issue).toHaveLength(1);
  expect(balanced(issue[0])).toBe(true);

  // A "bank transfer" must never be booked into the Cash ledger.
  const wrong = await ctx.post("/api/accounting/collections/receive", { data: {
    source_type: "invoice", source_id: inv.id, amount: 10, date: today(),
    bank_account_id: cash.id, payment_method: "bank_transfer",
  } });
  expect(wrong.status(), "bank_transfer into Cash is rejected").toBe(400);

  const pay = (amount, key) => ctx.post("/api/accounting/collections/receive", {
    headers: { "Idempotency-Key": key },
    data: { source_type: "invoice", source_id: inv.id, amount, date: today(),
            bank_account_id: bank.id, payment_method: "bank_transfer", reference: inv.number },
  });
  const key = `e2e-${uid()}`;
  await json(pay(50, key));
  await pay(50, key); // double-click / network retry with the same key
  let receipts = (await journals(ctx, { source: "invoice_payment", client_id: client.id }))
    .filter((j) => !j.reversed);
  expect(receipts, "retry with same key posts once").toHaveLength(1);

  let fresh = (await json(ctx.get("/api/invoices?doc_type=invoice"))).find((r) => r.id === inv.id);
  expect(fresh.status).toBe("partially_paid");
  expect(fresh.paid_amount).toBe(50);

  await json(pay(68.01, `e2e-${uid()}`));
  fresh = (await json(ctx.get("/api/invoices?doc_type=invoice"))).find((r) => r.id === inv.id);
  expect(fresh.status).toBe("paid");
  receipts = (await journals(ctx, { source: "invoice_payment", client_id: client.id }))
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

  // The invoice list shows the same status the books imply.
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/invoices");
  await expect(page.getByRole("row", { name: new RegExp(inv.number) })).toContainText(/paid/i);
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
