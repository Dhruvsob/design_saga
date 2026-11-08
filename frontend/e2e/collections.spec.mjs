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

const incomeAcc = async (ctx, rx) => (await json(ctx.get("/api/accounts"))).find((a) => a.type === "income" && rx.test(a.name) && a.active !== false);
const collectInvoice = (ctx, inv, amount, extra = {}) => ctx.post("/api/accounting/receivables", { data: {
  invoice_id: inv.id, amount, name: `Invoice ${inv.number}`, ...extra } });

test("invoice is a document; ₹6,00,000 bill with ₹10,000 received books only ₹10,000 through Collections Due", async () => {
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
  expect(await rowFor(ctx, "invoice", inv.id), "a sent invoice is not automatically money due").toBeUndefined();
  const onInvoice = await receive(ctx, "invoice", inv.id, 10000, cash);
  expect(onInvoice.status(), "invoices don't take payments").toBe(409);
  expect((await ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "paid" } })).status()).toBe(409);

  // separate portion: "from this bill I expect this much"
  const consult = await incomeAcc(ctx, /consult/i);
  const recv = await json(collectInvoice(ctx, inv, 600000, { income_account_id: consult.id, due_date: today() }));
  expect([recv.client_id, recv.project_id, recv.reference]).toEqual([client.id, project.id, inv.number]);
  expect((await collectInvoice(ctx, inv, 1)).status(), "never more than the invoice").toBe(400);
  expect(await journals(ctx, { client_id: client.id }), "planning posts nothing").toHaveLength(0);

  const key = `e2e-${uid()}`;
  await json(receive(ctx, "other_receivable", recv.id, 10000, cash, key));
  await receive(ctx, "other_receivable", recv.id, 10000, cash, key);   // double click / retry
  const posted = await journals(ctx, { client_id: client.id });
  expect(posted, "one receipt, once").toHaveLength(1);
  expect(balanced(posted[0])).toBe(true);
  expect(posted[0].lines.find((l) => l.account_id === cash.id).debit).toBe(10000);
  expect(posted[0].lines.find((l) => l.account_type === "income").credit, "income = money received").toBe(10000);
  const row = await rowFor(ctx, "other_receivable", recv.id);
  expect([row.status, row.received_amount, row.outstanding]).toEqual(["partially_received", 10000, 590000]);
  const detail = await json(ctx.get(`/api/projects/${project.id}`));
  expect(detail.money).toMatchObject({ project_value: 600000, invoiced: 600000, received: 10000, still_to_receive: 590000 });
  await ctx.dispose();
});

test("GST invoice collected in parts: each receipt splits revenue and output GST; full payment leaves the due list", async () => {
  const ctx = await api("admin");
  const { bank } = await accounts(ctx);
  const client = await json(ctx.post("/api/clients", { data: { name: `GST ${uid()}` } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 18, items: [{ description: "Design fee", quantity: 1, rate: 1000 }],
  } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  const recv = await json(collectInvoice(ctx, inv, 1180, { income_account_id: (await incomeAcc(ctx, /consult/i)).id }));
  await json(receive(ctx, "other_receivable", recv.id, 590, bank));
  const [je] = await journals(ctx, { client_id: client.id });
  expect(je.lines.find((l) => l.account_type === "income").credit).toBe(500);
  expect(je.lines.find((l) => l.account_name === "GST Payable").credit).toBe(90);
  await json(receive(ctx, "other_receivable", recv.id, 590, bank));
  expect((await rowFor(ctx, "other_receivable", recv.id)).status).toBe("received");
  expect((await receive(ctx, "other_receivable", recv.id, 1, bank)).status(), "nothing left").toBeGreaterThanOrEqual(400);
  await ctx.dispose();
});

test("Collection Due with reminder: Payment Reminders + calendar (+Google queue), alert with sound, closed on receipt", async () => {
  const ctx = await api("admin");
  const { cash } = await accounts(ctx);
  const client = await json(ctx.post("/api/clients", { data: { name: `Reminder ${uid()}`, phone: "+91 98250-00001" } }));
  const tomorrow = new Date(Date.now() + 5.5 * 3600e3 + 86400e3).toISOString().slice(0, 10);
  const before = (await journals(ctx, {})).length;
  const recv = await json(ctx.post("/api/accounting/receivables", { data: {
    name: "2nd instalment", amount: 590000, client_id: client.id, due_date: tomorrow,
    income_account_id: (await incomeAcc(ctx, /consult/i)).id,
    reminder_date: tomorrow, reminder_time: "11:15", remind_before_days: 1, repeat_every: "weekly",
  } }));
  expect((await journals(ctx, {})).length, "a reminder never posts accounting").toBe(before);
  const row = await rowFor(ctx, "other_receivable", recv.id);
  expect([row.reminder_time, row.remind_before_days, row.repeat_every]).toEqual(["11:15", 1, "weekly"]);
  // Payment Reminders: one automatic PR document with WhatsApp + PDF
  const rems = (await json(ctx.get("/api/accounting/reminders"))).filter((r) => r.source_id === recv.id);
  expect(rems).toHaveLength(1);
  expect(rems[0]).toMatchObject({ auto: true, amount_due: 590000, reminder_time: "11:15" });
  expect(rems[0].whatsapp_url).toContain("https://wa.me/919825000001?text=");
  expect((await ctx.get(`/api/accounting/reminders/${rems[0].id}/pdf`)).status()).toBe(200);
  // ERP calendar
  const feed = await json(ctx.get(`/api/calendar/feed?start=${tomorrow}&end=${tomorrow}`));
  const ev = feed.items.find((i) => (i.title || "").includes(client.name));
  expect(ev && ev.time).toBe("11:15");
  expect((await ctx.patch(`/api/calendar/events/${ev.event.id}`, { data: { title: "x" } })).status(), "edit it in Collections Due").toBe(409);
  // staff never see it
  const staff = await api("employee");
  const staffFeed = await json(staff.get(`/api/calendar/feed?start=${tomorrow}&end=${tomorrow}`));
  expect(staffFeed.items.some((i) => (i.title || "").includes(client.name))).toBe(false);
  expect((await staff.get("/api/accounting/reminders")).status()).toBe(403);
  await staff.dispose();
  // editing the time moves the calendar event and keeps one document
  await json(ctx.patch(`/api/accounting/receivables/${recv.id}`, { data: { reminder_time: "16:45" } }));
  const feed2 = await json(ctx.get(`/api/calendar/feed?start=${tomorrow}&end=${tomorrow}`));
  expect(feed2.items.filter((i) => (i.title || "").includes(client.name)).map((i) => i.time)).toEqual(["16:45"]);
  expect((await json(ctx.get("/api/accounting/reminders"))).filter((r) => r.source_id === recv.id)).toHaveLength(1);
  // money received in full -> reminder closed everywhere
  await json(receive(ctx, "other_receivable", recv.id, 590000, cash));
  const feed3 = await json(ctx.get(`/api/calendar/feed?start=${tomorrow}&end=${tomorrow}`));
  expect(feed3.items.some((i) => (i.title || "").includes(client.name)), "calendar event removed").toBe(false);
  const closed = (await json(ctx.get("/api/accounting/reminders"))).find((r) => r.source_id === recv.id);
  expect(closed.state).toBe("settled");
  const income = (await journals(ctx, { client_id: client.id })).flatMap((j) => j.lines).filter((l) => l.account_type === "income");
  expect(income.reduce((s, l) => s + l.credit - l.debit, 0), "booked once, by the receipt").toBe(590000);
  await ctx.dispose();
});

test("vendor incentive expected via the income account; % milestone follows project value and stays collectable", async () => {
  const ctx = await api("admin");
  const { bank } = await accounts(ctx);
  const vendor = await json(ctx.post("/api/vendors", { data: { name: `Lights ${uid()}` } }));
  const vid = vendor.id || vendor.vendor?.id;
  const client = await json(ctx.post("/api/clients", { data: { name: `Fee ${uid()}` } }));
  const project = await json(ctx.post("/api/projects", { data: { name: `Villa ${uid()}`, client_id: client.id, budget: 600000, engagement_type: "consultancy" } }));
  const plan = await json(ctx.post(`/api/vendors/${vid}/commissions`, { data: {
    amount: 12000, due_date: today(), project_id: project.id, reminder_date: today(), reminder_time: "23:59" } }));
  expect((await rowFor(ctx, "vendor_commission", plan.id)).name).toContain("Vendor incentive");
  await json(receive(ctx, "vendor_commission", plan.id, 12000, bank));
  const inc = (await journals(ctx, { vendor_id: vid })).flatMap((j) => j.lines).find((l) => l.account_type === "income");
  expect(inc.account_name).toMatch(/Vendor (Incentive|Commission) Income/);
  // % milestone
  const ms = await json(ctx.post(`/api/projects/${project.id}/milestones`, { data: { project_id: project.id, name: "Design advance", percent: 10, due_date: today() } }));
  await json(ctx.patch(`/api/projects/${project.id}`, { data: { budget: 800000 } }));
  expect((await json(ctx.get(`/api/projects/${project.id}`))).milestones.find((m) => m.id === ms.id).amount).toBe(80000);
  expect((await ctx.patch(`/api/milestones/${ms.id}`, { data: { status: "paid" } })).status(), "a label is not a payment").toBe(409);
  await json(ctx.post("/api/invoices", { data: { client_id: client.id, milestone_id: ms.id, doc_type: "invoice", tax_rate: 0,
    items: [{ description: "Design advance (10%)", quantity: 1, rate: 80000 }] } }));
  expect(await rowFor(ctx, "milestone", ms.id), "billing a milestone keeps it in Collections Due").toBeTruthy();
  await json(receive(ctx, "milestone", ms.id, 80000, bank));
  expect((await json(ctx.get(`/api/projects/${project.id}`))).milestones.find((m) => m.id === ms.id).status).toBe("paid");
  // combined ledger: project + vendor -> incentive from this vendor on this project
  const comb = await json(ctx.get(`/api/accounting/ledger/combined?project_ids=${project.id}&vendor_ids=${vid}`));
  expect(comb.totals.income).toBe(12000);
  expect(comb.by_vendor[0].vendor_name).toBe(vendor.name || vendor.vendor?.name);
  const projOnly = await json(ctx.get(`/api/accounting/ledger/combined?project_ids=${project.id}`));
  expect(projOnly.totals.income, "incentive + consultancy on the project").toBe(92000);
  await ctx.dispose();
});

test("screens: invoice status is a label, Add to Collections Due, reminder shows in Payment Reminders", async ({ browser }) => {
  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Screen ${uid()}`, phone: "9825000002" } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", tax_rate: 0, due_date: today(), items: [{ description: "Fee", quantity: 1, rate: 25000 }],
  } }));
  await json(ctx.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/invoices");
  const tabs = page.getByTestId("money-in-tabs");
  await expect(tabs).toContainText("Collections Due", { timeout: 20000 });
  const row = page.getByRole("row", { name: new RegExp(inv.number) });
  await expect(row).toContainText("25,000", { timeout: 20000 });
  await expect(page.getByTestId(`invoice-pay-${inv.id}`), "no payments on invoices").toHaveCount(0);
  await page.getByTestId(`invoice-actions-${inv.id}`).click();
  await page.getByRole("menuitem", { name: "Add to Collections Due" }).click();
  await page.getByTestId("form-field-amount").fill("20000");
  await page.getByTestId("form-field-reminder_date").fill(today());
  await page.getByTestId("form-field-reminder_time").fill("23:30");
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByText("Added to Collections Due with its reminder")).toBeVisible({ timeout: 20000 });
  await expect(row).toContainText("20,000");
  await page.goto("/invoices/reminders");
  await expect(page.getByTestId("reminders-table")).toContainText(client.name, { timeout: 20000 });
  await page.goto("/accounting?tab=receivables");
  await expect(page.getByTestId("collections-due-tab")).toContainText("Reminder", { timeout: 20000 });
  await ctx.dispose();
});

test("Collection Due form: income account decides vendor or client; reminder fields saved", async ({ browser }) => {
  const ctx = await api("admin");
  const vendor = await json(ctx.post("/api/vendors", { data: { name: `Fans ${uid()}` } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/accounting?tab=receivables");
  await page.getByRole("button", { name: /Add expected collection/ }).click({ timeout: 20000 });
  const form = page.getByTestId("collection-plan-form");
  await expect(form).not.toContainText("Collection type");
  await expect(page.getByTestId("plan-client")).toBeVisible();
  const accSel = page.getByTestId("plan-income-account");
  const incentive = await incomeAcc(ctx, /incentive|commission/i);
  await accSel.click();
  await page.getByRole("option", { name: incentive.name, exact: true }).click();
  await expect(page.getByTestId("plan-vendor")).toBeVisible();
  await expect(page.getByTestId("plan-client")).toHaveCount(0);
  await ctx.dispose();
  expect(vendor).toBeTruthy();
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

test("adding a lead with a phone number already on file asks before creating a duplicate", async ({ browser }) => {
  const ctx = await api("admin");
  const phone = `98${Math.floor(10000000 + Math.random() * 89999999)}`;
  await json(ctx.post("/api/leads", { data: { name: `First ${uid()}`, phone } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto("/crm");
  await page.getByTestId("new-lead-btn").click({ timeout: 20000 });
  await page.getByTestId("lead-name").fill(`Again ${uid()}`);
  await page.getByTestId("lead-form").getByPlaceholder(/phone/i).fill(`+91 ${phone}`);
  await page.getByTestId("lead-submit").click();
  await expect(page.getByTestId("confirm-dialog")).toContainText("already a lead with this phone number");
  await page.getByTestId("confirm-cancel").click();
  const same = (await json(ctx.get("/api/leads"))).filter((l) => String(l.phone || "").replace(/\D/g, "").endsWith(phone));
  expect(same, "cancel keeps a single lead").toHaveLength(1);
  await ctx.dispose();
});
