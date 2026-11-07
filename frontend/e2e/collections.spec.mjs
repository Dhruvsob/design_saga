// Invoices vs reminders vs collections vs accounting — the money-in workflow end to end.
import { test, expect } from "@playwright/test";
import { api, json, accounts, journals, balanced, today, uid, authFile, baseURL } from "./helpers.mjs";

test.describe.configure({ mode: "serial" });

const receive = (ctx, source_type, source_id, amount, account, key = `e2e-${uid()}`) =>
  ctx.post("/api/accounting/collections/receive", {
    headers: { "Idempotency-Key": key },
    data: { source_type, source_id, amount, date: today(), bank_account_id: account.id,
            payment_method: account.name === "Cash" ? "cash" : "bank_transfer", reference: "E2E" },
  });
const rowFor = async (ctx, type, id) =>
  (await json(ctx.get("/api/accounting/receivables"))).rows.find((r) => r.source_type === type && r.id === id);

test("₹6,00,000 invoice + ₹10,000 received books only ₹10,000; project keeps value, billed, received apart", async () => {
  const ctx = await api("admin");
  const { cash } = await accounts(ctx);
  const client = await json(ctx.post("/api/clients", { data: { name: `Krunal ${uid()}`, phone: "98250 12345" } }));
  const project = await json(ctx.post("/api/projects", { data: { name: `Cloud-9 ${uid()}`, client_id: client.id, budget: 600000, engagement_type: "consultancy" } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, project_id: project.id, doc_type: "invoice", tax_rate: 0, due_date: today(),
    items: [{ description: "Interior design – full project value", quantity: 1, rate: 600000 }],
  } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  expect(await journals(ctx, { client_id: client.id }), "sending posts nothing").toHaveLength(0);

  const paidLabel = await ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "paid" } });
  expect(paidLabel.status(), "a Paid label is not a payment").toBe(409);
  expect(await journals(ctx, { client_id: client.id })).toHaveLength(0);

  const key = `e2e-${uid()}`;
  await json(receive(ctx, "invoice", inv.id, 10000, cash, key));
  await receive(ctx, "invoice", inv.id, 10000, cash, key);   // double click / retry
  const posted = await journals(ctx, { client_id: client.id });
  expect(posted, "one receipt, once").toHaveLength(1);
  const je = posted[0];
  expect(balanced(je)).toBe(true);
  expect(je.total).toBe(10000);
  expect(je.lines.find((l) => l.account_id === cash.id).debit).toBe(10000);
  expect(je.lines.find((l) => l.account_type === "income").credit, "income = money received").toBe(10000);
  expect(je.lines.some((l) => l.account_name === "Accounts Receivable"), "no 6 lakh receivable").toBe(false);

  const row = await rowFor(ctx, "invoice", inv.id);
  expect(row.status).toBe("partially_received");
  expect(row.received_amount).toBe(10000);
  expect(row.outstanding).toBe(590000);

  const detail = await json(ctx.get(`/api/projects/${project.id}`));
  expect(detail.money).toMatchObject({ project_value: 600000, invoiced: 600000, received: 10000,
                                       billed_unpaid: 590000, still_to_receive: 590000 });

  const received = await json(ctx.get("/api/accounting/received-payments"));
  const mine = received.rows.filter((r) => r.client_id === client.id);
  expect(mine).toHaveLength(1);
  expect(mine[0]).toMatchObject({ amount: 10000, account: "Cash", source: "invoice_payment" });
  await ctx.dispose();
});

test("GST invoice paid in part: receipt splits revenue and output GST; full payment closes it", async () => {
  const ctx = await api("admin");
  const { bank } = await accounts(ctx);
  const client = await json(ctx.post("/api/clients", { data: { name: `GST ${uid()}` } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 18, items: [{ description: "Design fee", quantity: 1, rate: 1000 }],
  } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  await json(receive(ctx, "invoice", inv.id, 590, bank));
  const [je] = await journals(ctx, { client_id: client.id });
  expect(je.lines.find((l) => l.account_type === "income").credit).toBe(500);
  expect(je.lines.find((l) => l.account_name === "GST Payable").credit).toBe(90);
  await json(receive(ctx, "invoice", inv.id, 590, bank));
  expect((await rowFor(ctx, "invoice", inv.id)).status).toBe("received");
  const over = await receive(ctx, "invoice", inv.id, 1, bank);
  expect(over.status(), "nothing left to collect").toBeGreaterThanOrEqual(400);
  await ctx.dispose();
});

test("payment reminder: numbered PDF + WhatsApp, no journal; staff cannot read it", async () => {
  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Reminder ${uid()}`, phone: "+91 98250-00001" } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 0, items: [{ description: "Fee", quantity: 1, rate: 590000 }],
  } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  const before = (await journals(ctx, {})).length;
  const rem = await json(ctx.post("/api/accounting/reminders", { data: {
    source_type: "invoice", source_id: inv.id, due_by: today(), message: "Kindly clear before handover.",
  } }));
  expect(rem.number).toMatch(/^PR-\d{4}$/);
  expect(rem.amount_due).toBe(590000);
  expect(rem.whatsapp_url).toContain("https://wa.me/919825000001?text=");
  expect(decodeURIComponent(rem.whatsapp_url)).toContain("Rs. 5,90,000");
  expect((await journals(ctx, {})).length, "a reminder never posts accounting").toBe(before);

  const pdf = await ctx.get(`/api/accounting/reminders/${rem.id}/pdf`);
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
  expect((await json(ctx.get("/api/accounting/reminders"))).some((r) => r.id === rem.id && r.state !== "cancelled")).toBe(true);
  expect((await rowFor(ctx, "invoice", inv.id)).outstanding, "collection unchanged").toBe(590000);

  const staff = await api("employee");
  expect((await staff.get("/api/accounting/reminders")).status()).toBe(403);
  expect((await staff.get(`/api/accounting/reminders/${rem.id}/pdf`)).status()).toBe(403);
  expect((await staff.get("/api/accounting/received-payments")).status()).toBe(403);
  await staff.dispose();
  await ctx.dispose();
});

test("percentage milestone follows project value; invoiced milestone is collected once, through its invoice", async () => {
  const ctx = await api("admin");
  const { bank } = await accounts(ctx);
  const client = await json(ctx.post("/api/clients", { data: { name: `Fee ${uid()}` } }));
  const project = await json(ctx.post("/api/projects", { data: { name: `Villa ${uid()}`, client_id: client.id, budget: 600000, engagement_type: "consultancy" } }));
  const ms = await json(ctx.post(`/api/projects/${project.id}/milestones`, { data: { project_id: project.id, name: "Design advance", percent: 10, due_date: today() } }));
  expect(ms.amount).toBe(60000);
  await json(ctx.patch(`/api/projects/${project.id}`, { data: { budget: 800000 } }));
  let milestone = (await json(ctx.get(`/api/projects/${project.id}`))).milestones.find((m) => m.id === ms.id);
  expect(milestone.amount, "10% of the new project value").toBe(80000);

  const label = await ctx.patch(`/api/milestones/${ms.id}`, { data: { status: "paid" } });
  expect(label.status(), "milestone 'paid' label is not a payment").toBe(409);

  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, milestone_id: ms.id, doc_type: "invoice", tax_rate: 0,
    items: [{ description: "Design advance (10%)", quantity: 1, rate: 80000 }],
  } }));
  expect(inv.project_id).toBe(project.id);
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  expect(await rowFor(ctx, "milestone", ms.id), "milestone not listed twice").toBeUndefined();
  expect((await rowFor(ctx, "invoice", inv.id)).name).toContain("Design advance");
  const direct = await receive(ctx, "milestone", ms.id, 1000, bank);
  expect(direct.status(), "pay the invoice, not the milestone").toBe(409);

  const dupe = await ctx.post("/api/invoices", { data: {
    client_id: client.id, milestone_id: ms.id, doc_type: "invoice", items: [{ description: "again", quantity: 1, rate: 1 }],
  } });
  expect(dupe.status(), "one live invoice per milestone").toBe(409);

  await json(receive(ctx, "invoice", inv.id, 80000, bank));
  milestone = (await json(ctx.get(`/api/projects/${project.id}`))).milestones.find((m) => m.id === ms.id);
  expect(milestone.status).toBe("paid");
  expect(milestone.paid_amount).toBe(80000);
  const posted = await journals(ctx, { project_id: project.id });
  expect(posted, "money booked once").toHaveLength(1);
  await ctx.dispose();
});

test("screens: money-in tabs, reminder from Collections Due, received payments", async ({ browser }) => {
  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Screen ${uid()}`, phone: "9825000002" } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 0, due_date: today(), items: [{ description: "Fee", quantity: 1, rate: 25000 }],
  } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/invoices");
  const tabs = page.getByTestId("money-in-tabs");
  await expect(tabs).toContainText("Invoices", { timeout: 20000 });   // first page load on a cold test machine
  await expect(tabs).toContainText("Payment Reminders");
  await expect(tabs).toContainText("Collections Due");
  await expect(tabs).toContainText("Received Payments");
  await expect(page.getByRole("row", { name: new RegExp(inv.number) })).toContainText("25,000", { timeout: 20000 });

  await page.getByTestId(`invoice-actions-${inv.id}`).click();
  await page.getByRole("menuitem", { name: "Send payment reminder" }).click();
  await page.getByTestId("form-field-due_by").fill(today());
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId("reminder-ready")).toBeVisible();
  await expect(page.getByTestId("reminder-whatsapp")).toHaveAttribute("href", /wa\.me\/919825000002/);

  await page.goto("/invoices/reminders");
  await expect(page.getByTestId("reminders-table")).toContainText(client.name);
  await page.goto("/invoices/received");
  await expect(page.getByTestId("received-payments-page")).toBeVisible();
  await ctx.dispose();
});

test("restating an accrual-era ₹6,00,000 invoice on cash basis leaves only the ₹51,000 received as income", async ({ browser }) => {
  const ctx = await api("admin");
  const { cash } = await accounts(ctx);
  await json(ctx.patch("/api/org/current", { data: { accounting_basis: "accrual" } }));
  try {
    const client = await json(ctx.post("/api/clients", { data: { name: `Accrual ${uid()}` } }));
    const inv = await json(ctx.post("/api/invoices", { data: {
      client_id: client.id, doc_type: "invoice", tax_rate: 0, items: [{ description: "Project value", quantity: 1, rate: 600000 }],
    } }));
    await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
    await json(receive(ctx, "invoice", inv.id, 51000, cash));
    const incomeOf = async () => (await journals(ctx, { client_id: client.id }))
      .flatMap((j) => j.lines).filter((l) => l.account_type === "income")
      .reduce((s, l) => s + l.credit - l.debit, 0);
    expect(await incomeOf(), "accrual booked the full value").toBe(600000);

    await json(ctx.patch("/api/org/current", { data: { accounting_basis: "cash" } }));
    // the admin does it from the invoice's ⋮ menu
    const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
    await page.goto("/invoices");
    await page.getByTestId(`invoice-actions-${inv.id}`).click({ timeout: 20000 });
    await page.getByRole("menuitem", { name: "Restate on cash basis" }).click();
    await page.getByTestId("confirm-ok").click();
    await expect(page.getByText(/restated: income now equals the money received/)).toBeVisible({ timeout: 20000 });
    expect(await incomeOf(), "only money received is income").toBe(51000);
    const visible = await journals(ctx, { client_id: client.id });
    expect(visible.flatMap((j) => j.lines).some((l) => l.account_name === "Accounts Receivable")).toBe(false);
    expect(visible.every((j) => balanced(j))).toBe(true);
    const row = await rowFor(ctx, "invoice", inv.id);
    expect([row.received_amount, row.outstanding]).toEqual([51000, 549000]);
    const again = await ctx.post(`/api/accounting/invoices/${inv.id}/restate-cash-basis`);
    expect(again.status(), "runs once").toBe(409);
    const staff = await api("employee");
    expect((await staff.post(`/api/accounting/invoices/${inv.id}/restate-cash-basis`)).status()).toBe(403);
    await staff.dispose();
  } finally {
    await ctx.patch("/api/org/current", { data: { accounting_basis: "cash" } });
    await ctx.dispose();
  }
});

test("signature drawn on the pad prints on PDFs; staff cannot read or change it", async ({ browser }) => {
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/settings/company");
  await page.getByTestId("signature-draw").click();
  await page.getByTestId("signature-canvas").scrollIntoViewIfNeeded();
  const box = await page.getByTestId("signature-canvas").boundingBox();
  await page.mouse.move(box.x + 30, box.y + 110);
  await page.mouse.down();
  for (const [dx, dy] of [[80, 40], [130, 120], [190, 50], [260, 115], [340, 60], [420, 90]]) {
    await page.mouse.move(box.x + dx, box.y + dy, { steps: 6 });
  }
  await page.mouse.up();
  await page.getByTestId("signature-save").click();
  await expect(page.getByTestId("signature-msg")).toContainText("Signature saved");
  await expect(page.getByTestId("signature-preview")).toBeVisible();

  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Signed ${uid()}` } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 0, items: [{ description: "Fee", quantity: 1, rate: 5000 }] } }));
  const pdf = await (await ctx.get(`/api/invoices/${inv.id}/pdf`)).body();
  expect(pdf.toString("latin1")).toContain("/Subtype /Image");
  const org = await json(ctx.get("/api/org/current"));
  expect(org.has_signature).toBe(true);
  expect(JSON.stringify(org)).not.toContain("org-signatures");          // storage path never exposed
  const staff = await api("employee");
  expect((await staff.get("/api/org/current/signature")).status()).toBe(403);
  expect((await staff.delete("/api/org/current/signature")).status()).toBe(403);
  await staff.dispose();
  await ctx.dispose();
});

test("1st and 4th Saturdays are added as holidays in one go, without duplicates", async ({ browser }) => {
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/holidays");
  await page.getByTestId("holiday-saturdays").click();
  await page.getByTestId("confirm-ok").click();                       // defaults: 1, 4 from 1 Jan
  await expect(page.getByText(/Added \d+ Saturday holidays/)).toBeVisible({ timeout: 30000 });
  const ctx = await api("admin");
  const year = new Date().getFullYear();
  const list = (await json(ctx.get(`/api/holidays?year=${year}`))).holidays.filter((h) => /Saturday$/.test(h.name));
  expect(list.length).toBe(24);
  for (const h of list) expect(new Date(`${h.date}T00:00:00Z`).getUTCDay()).toBe(6);
  await page.getByTestId("holiday-saturdays").click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByText("Those Saturdays were already added")).toBeVisible({ timeout: 30000 });
  await ctx.dispose();
});
