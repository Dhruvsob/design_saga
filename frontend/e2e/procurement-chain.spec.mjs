// Vendor -> project -> PO -> GRN -> bill -> payment -> journals -> vendor/project/accounting views.
import { test, expect } from "@playwright/test";
import { api, json, accounts, today, uid, closeExtraContexts } from "./helpers.mjs";

test.afterEach(closeExtraContexts);  // see helpers: forgotten windows lock the shared session

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "chain logic is viewport independent");
});

const r2 = (n) => Math.round(Number(n || 0) * 100) / 100;

test("procurement chain posts once and every module shows the same bill and payment", async () => {
  const ctx = await api("admin");
  const { bank } = await accounts(ctx);
  const vendor = await json(ctx.post("/api/vendors", { data: { name: `Kitchen ${uid()}` } }));
  const vid = vendor.id || vendor.vendor?.id;
  const client = await json(ctx.post("/api/clients", { data: { name: `Proc ${uid()}` } }));
  const project = await json(ctx.post("/api/projects", { data: { name: `Turnkey ${uid()}`, client_id: client.id, engagement_type: "turnkey" } }));

  const po = await json(ctx.post("/api/purchase-orders", { data: {
    vendor_id: vid, project_id: project.id, order_date: today(),
    lines: [{ item_name: "Modular kitchen", quantity: 1, unit: "set", unit_price: 80000 }] } }));
  await json(ctx.post(`/api/purchase-orders/${po.id}/send`));
  const full = await json(ctx.get(`/api/purchase-orders/${po.id}`));
  const line = (full.lines || full.po?.lines)[0];
  await json(ctx.post("/api/grns", { data: { po_id: po.id, received_date: today(),
    lines: [{ po_line_id: line.id || line.line_id, received_qty: 1 }] } }));

  const bill = await json(ctx.post("/api/vendor-bills", { data: {
    vendor_id: vid, project_id: project.id, po_id: po.id, bill_number: `KB-${uid()}`, bill_date: today(),
    items: [{ po_line_id: line.id || line.line_id, description: "Modular kitchen", quantity: 1, rate: 80000 }] } }));
  const billId = bill.id || bill.bill?.id;
  const match = await json(ctx.get(`/api/purchase-orders/${po.id}/match`));
  expect(JSON.stringify(match)).not.toMatch(/mismatch|over_billed/i);

  const key = `e2e-${uid()}`;
  const pay = (k) => ctx.post("/api/vendor-payments", { headers: { "Idempotency-Key": k }, data: {
    vendor_id: vid, amount: 30000, payment_date: today(), paid_from_account_id: bank.id,
    payment_method: "bank_transfer", project_id: project.id, bill_ids: [billId] } });
  await json(pay(key));
  await pay(key);                                            // double click
  const journals = (await json(ctx.get(`/api/journal-entries?vendor_id=${vid}&limit=500`)));
  const rows = (Array.isArray(journals) ? journals : journals.items).filter((j) => !j.voided_from_view);
  const bySource = (s) => rows.filter((j) => j.source === s && !j.reversed);
  expect(bySource("vendor_bill"), "bill posted once").toHaveLength(1);
  expect(bySource("vendor_payment"), "payment posted once").toHaveLength(1);
  for (const j of rows) expect(r2(j.lines.reduce((s, l) => s + l.debit - l.credit, 0))).toBe(0);
  const paidFrom = bySource("vendor_payment")[0].lines.find((l) => l.credit > 0);
  expect(paidFrom.account_id, "money left the chosen bank").toBe(bank.id);

  // the same bill/payment seen from vendor, project and accounting
  const vb = await json(ctx.get(`/api/vendor-bills/${billId}`));
  const b = vb.bill || vb;
  expect(r2(b.paid_amount)).toBe(30000);
  expect(r2(b.total - b.paid_amount)).toBe(50000);
  const vledger = await json(ctx.get(`/api/vendors/${vid}/ledger`));
  expect(JSON.stringify(vledger)).toContain(billId);
  const ledger = await json(ctx.get(`/api/accounting/ledger/vendor/${vid}?fy=all`));
  expect(JSON.stringify(ledger)).toContain(bySource("vendor_payment")[0].id);
  const projectJournals = await json(ctx.get(`/api/journal-entries?project_id=${project.id}&limit=500`));
  const pj = (Array.isArray(projectJournals) ? projectJournals : projectJournals.items).map((j) => j.id);
  expect(pj).toEqual(expect.arrayContaining([bySource("vendor_bill")[0].id]));
  await ctx.dispose();
});

test("Record vendor bill from a purchase order opens the vendor's bill form with the PO filled in", async ({ browser }) => {
  const { authFile, baseURL } = await import("./helpers.mjs");
  const ctx = await api("admin");
  const vendor = await json(ctx.post("/api/vendors", { data: { name: `Glass ${uid()}` } }));
  const vid = vendor.id || vendor.vendor?.id;
  const po = await json(ctx.post("/api/purchase-orders", { data: {
    vendor_id: vid, order_date: today(), lines: [{ item_name: "Toughened glass", quantity: 4, unit: "nos", unit_price: 2500 }] } }));
  await json(ctx.post(`/api/purchase-orders/${po.id}/send`));
  const sent = await json(ctx.get(`/api/purchase-orders/${po.id}`));
  const pl = (sent.lines || sent.po?.lines)[0];
  await json(ctx.post("/api/grns", { data: { po_id: po.id, received_date: today(), lines: [{ po_line_id: pl.id || pl.line_id, received_qty: 4 }] } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/purchase-orders");
  await page.getByTestId(`po-actions-${po.id}`).click({ timeout: 20000 });
  await page.getByRole("menuitem", { name: "Record vendor bill" }).click();
  await expect.poll(() => page.url()).toContain(`/vendors/${vid}?tab=bills&po=${po.id}`);
  await expect(page.getByLabel("Purchase order")).toHaveValue(po.id, { timeout: 20000 });
  await expect.poll(() => page.$$eval("form input", (els) => els.map((e) => e.value))).toContain("Toughened glass");
  await page.getByTestId("save-bill-btn").click();
  await expect(page.getByText("Vendor bill posted")).toBeVisible({ timeout: 20000 });
  const bills = await json(ctx.get(`/api/vendor-bills?vendor_id=${vid}`));
  const list = Array.isArray(bills) ? bills : bills.items || bills.bills;
  expect(list).toHaveLength(1);
  expect(list[0].po_id).toBe(po.id);
  expect(Math.round(list[0].total)).toBe(Math.round(10000 * 1.18));     // default 18% GST on the form
  await ctx.dispose();
});
