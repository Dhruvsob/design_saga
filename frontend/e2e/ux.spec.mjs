// UX batch (DS-088..DS-090): collections queue vs history, styled confirms,
// leave privacy and salary working.
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile, accounts, today } from "./helpers.mjs";

test.use({ storageState: authFile("admin") });
test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
  for (const role of ["admin", "employee"]) await (await api(role)).dispose();
});

async function openCollections(page) {
  const select = page.getByTestId("accounting-section-select");
  await page.locator('[data-testid="accounting-section-select"]:visible, [data-testid="tab-receivables"]:visible')
    .first().waitFor();
  if (await select.isVisible()) await select.selectOption("receivables");
  else await page.getByTestId("tab-receivables").click();
}

test("a fully received collection leaves the active queue and shows in Received history", async ({ page }) => {
  const ctx = await api("admin");
  const { bank, rows } = await accounts(ctx);
  const income = rows.find((a) => a.type === "income");
  const name = `Commission Dhrumil ${uid()}`;
  const due = await json(ctx.post("/api/accounting/receivables", {
    data: { name, amount: 5000, due_date: today(), income_account_id: income.id },
  }));
  const receive = (amount) => ctx.post("/api/accounting/collections/receive", {
    headers: { "Idempotency-Key": `ux-${uid()}` },
    data: { source_type: "other_receivable", source_id: due.id, amount, date: today(),
            bank_account_id: bank.id, income_account_id: income.id, payment_method: "bank_transfer" },
  });
  await json(receive(2000));

  await page.goto("/accounting");
  await openCollections(page);
  await page.getByTestId("collections-search").fill(name);
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row).toContainText("3,000");
  await expect(row).toContainText(/partially received/i);

  await json(receive(3000));
  await page.reload();
  await openCollections(page);
  await page.getByTestId("collections-search").fill(name);
  await expect(page.getByRole("row", { name: new RegExp(name) })).toHaveCount(0);
  await page.getByTestId("collections-filter-history").click();
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText("5,000");
  await ctx.dispose();
});

test("deleting asks in a styled dialog; Cancel keeps the record", async ({ page }) => {
  const ctx = await api("admin");
  const q = await json(ctx.post("/api/quotations-adv", { data: { type: "turnkey", project_title: `Confirm ${uid()}` } }));
  await page.goto("/quotations");
  const row = page.getByTestId(`q-row-${q.id}`);
  await page.getByTestId(`q-actions-${q.id}`).click();
  await page.getByTestId(`q-delete-${q.id}`).click();
  const dialog = page.getByTestId("confirm-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Delete quotation?");
  await page.getByTestId("confirm-cancel").click();
  await expect(dialog).toHaveCount(0);
  await expect(row).toBeVisible();
  await page.getByTestId(`q-actions-${q.id}`).click();
  await page.getByTestId(`q-delete-${q.id}`).click();
  await page.getByTestId("confirm-ok").click();
  await expect(row).toHaveCount(0);
  await ctx.dispose();
});

test("employees never see maternity/paternity or the HR leave table", async () => {
  const emp = await api("employee");
  const meta = await json(emp.get("/api/attendance/meta"));
  expect(meta.leave_types).not.toContain("maternity");
  expect(meta.leave_types).not.toContain("paternity");
  expect(meta.default_allowance).toEqual({});
  const res = await emp.post("/api/leaves", { data: { leave_type: "maternity", from_date: "2026-12-01", to_date: "2026-12-02" } });
  expect(res.status()).toBe(403);
  await emp.dispose();
  const admin = await api("admin");
  expect((await json(admin.get("/api/attendance/meta"))).leave_types).toContain("maternity");
  await admin.dispose();
});

test("lock sits beside the bell; project overview shows facts and attention without duplicates", async ({ page }) => {
  const ctx = await api("admin");
  const proj = await json(ctx.post("/api/projects", { data: { name: `Hub ${uid()}`, engagement_type: "consultancy" } }));
  await ctx.post("/api/tasks", { data: { title: "Late drawing", project_id: proj.id, due_date: "2026-01-05" } });
  await ctx.dispose();
  await page.goto(`/projects/${proj.id}`);
  await expect(page.getByTestId("header-lock-btn")).toBeVisible();
  await expect(page.getByRole("button", { name: /^App lock$/ })).toHaveCount(0);
  await expect(page.getByTestId("project-facts")).toBeVisible();
  await expect(page.getByTestId("project-facts")).not.toContainText("Stage");
  await expect(page.getByTestId("project-hub")).toHaveCount(0);
  const attention = page.getByTestId("project-attention");
  await expect(attention).toContainText("past due");
  await attention.getByTestId("attention-Tasks").click();
  await expect(page.getByTestId("tab-Tasks")).toHaveClass(/border-\[var\(--accent\)\]/);
});

test("ended subscription makes the workspace read-only but viewable", async ({ browser }) => {
  const { session, ensurePin } = await import("./global-setup.mjs");
  const { baseURL } = await import("./helpers.mjs");
  const password = process.env.QA_PASSWORD;
  const sa = await session(process.env.QA_SUPERADMIN_EMAIL, password);
  await ensurePin(sa);
  const stamp = uid();
  const email = `ro-${stamp}@qa.example.com`;
  const org = await json(sa.post("/api/platform/orgs", { data: {
    name: `RO Studio ${stamp}`, admin_email: email, admin_name: "RO Admin", admin_password: password, business_mode: "hybrid" } }));
  const orgId = org.org_id || org.org?.org_id || org.id;
  const admin = await session(email, password);
  await ensurePin(admin);
  await json(admin.post("/api/clients", { data: { name: "Before expiry" } }));

  const set = await json(sa.patch(`/api/platform/orgs/${orgId}/subscription`, { data: { status: "trial", trial_ends_on: "2026-01-01" } }));
  expect(set.state.read_only).toBe(true);
  const blocked = await admin.post("/api/clients", { data: { name: "After expiry" } });
  expect(blocked.status()).toBe(403);
  expect((await blocked.json()).detail).toContain("Read-only");
  expect((await admin.get("/api/clients")).status(), "viewing still works").toBe(200);
  const me = await json(admin.get("/api/org/current"));
  expect(me.subscription_state.read_only).toBe(true);

  const state = await admin.storageState();
  const page = await (await browser.newContext({ baseURL, storageState: state })).newPage();
  await page.goto("/dashboard");
  await expect(page.getByTestId("read-only-banner")).toContainText("Read-only mode");

  await json(sa.patch(`/api/platform/orgs/${orgId}/subscription`, { data: { status: "active" } }));
  await json(admin.post("/api/clients", { data: { name: "After renewal" } }));
  await sa.dispose();
  await admin.dispose();
});

test("sidebar groups stay open and the rail collapse is remembered", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "rail is a desktop control");
  await page.goto("/dashboard");
  await expect(page.getByTestId("nav-crm")).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId("nav-group-sales")).not.toHaveAttribute("aria-expanded", /.*/);
  await page.getByTestId("sidebar-collapse-btn").click();
  await expect(page.getByTestId("sidebar-brand-name")).toBeHidden();
  await expect(page.getByTestId("nav-accounting")).toHaveAttribute("title", "Accounting");
  await page.reload();
  await expect(page.getByTestId("sidebar-brand-name")).toBeHidden();
  await page.getByTestId("sidebar-collapse-btn").click();
  await expect(page.getByTestId("sidebar-brand-name")).toBeVisible();
});

test("calendar splits Studio and Project items from one feed; events link only to visible projects", async ({ page }) => {
  const ctx = await api("admin");
  const proj = await json(ctx.post("/api/projects", { data: { name: `Cal ${uid()}`, engagement_type: "consultancy" } }));
  const day = new Date().toISOString().slice(0, 10);
  const studio = `Studio meet ${uid()}`;
  const site = `Site visit ${uid()}`;
  await json(ctx.post("/api/calendar/events", { data: { title: studio, date: day, kind: "meeting", visibility: "org" } }));
  await json(ctx.post("/api/calendar/events", { data: { title: site, date: day, kind: "meeting", project_id: proj.id, visibility: "org" } }));
  const bad = await ctx.post("/api/calendar/events", { data: { title: "x", date: day, project_id: "proj_not_mine" } });
  expect(bad.status()).toBe(404);
  for (const link of [{ client_id: "cli_not_mine" }, { vendor_id: "ven_not_mine" }]) {
    const r = await ctx.post("/api/calendar/events", { data: { title: "x", date: day, ...link } });
    expect(r.status(), JSON.stringify(link)).toBe(404);
  }
  const feed = await json(ctx.get(`/api/calendar/feed?start=${day}&end=${day}`));
  const projectItem = feed.items.find((i) => i.title === site);
  expect(projectItem.scope).toBe("project");
  expect(projectItem.project_name).toBe(proj.name);
  expect(feed.items.find((i) => i.title === studio).scope).toBe("studio");
  await ctx.dispose();

  await page.goto("/calendar");
  await page.getByTestId("view-agenda").click();          // agenda lists every item
  await page.getByTestId("scope-studio").click();
  await expect(page.getByText(studio).first()).toBeVisible();
  await expect(page.getByText(site)).toHaveCount(0);
  await page.getByTestId("scope-project").click();
  await expect(page.getByText(site).first()).toBeVisible();
  await expect(page.getByText(studio)).toHaveCount(0);
});

test("work board: quick add, group by category, list and calendar show the same task", async ({ page }) => {
  const title = `Board task ${uid()}`;
  await page.goto("/tasks");
  await page.getByTestId("quick-add-todo").click();
  await page.getByTestId("quick-add-input-todo").fill(title);
  await page.getByTestId("quick-add-input-todo").press("Enter");
  await expect(page.getByTestId("col-todo")).toContainText(title);

  await page.getByTestId("board-group-by").selectOption("category");
  await expect(page.getByTestId("col-")).toContainText(title);       // "No category" lane

  await page.getByTestId("view-table-btn").click();
  await expect(page.getByText(title).first()).toBeVisible();
  await page.getByTestId("view-calendar-btn").click();
  await expect(page.getByTestId("task-unscheduled")).toContainText(title);
});

test("project card ⋮ pins to top and archives; employee forms use in-app dialogs", async ({ page }) => {
  const ctx = await api("admin");
  const a = await json(ctx.post("/api/projects", { data: { name: `Pin A ${uid()}`, engagement_type: "consultancy" } }));
  const b = await json(ctx.post("/api/projects", { data: { name: `Pin B ${uid()}`, engagement_type: "consultancy" } }));
  const emp = await json(ctx.post("/api/employees", { data: { first_name: "Dialog", last_name: `T${uid()}`, salary: { basic: 20000 } } }));
  await ctx.dispose();

  await page.goto("/projects");
  await page.getByTestId(`project-actions-${a.id}`).click();
  await page.getByTestId(`project-pin-${a.id}`).click();
  await expect(page.locator('[data-testid^="project-card-"]').first()).toHaveAttribute("data-testid", `project-card-${a.id}`);
  await page.getByTestId(`project-actions-${b.id}`).click();
  await page.getByTestId(`project-archive-${b.id}`).click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId(`project-card-${b.id}`)).toHaveCount(0);

  page.on("dialog", () => { throw new Error("native prompt() should not appear"); });
  await page.goto(`/employees/${emp.id}`);
  await page.getByTestId("emp-warning-btn").click();
  await expect(page.getByTestId("confirm-dialog")).toContainText("Add warning");
  await page.getByTestId("confirm-ok").click();                       // reason is required
  await expect(page.getByTestId("confirm-dialog")).toBeVisible();
  await page.getByTestId("form-field-reason").fill("Late to site");
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId("confirm-dialog")).toHaveCount(0);
  const check = await api("admin");
  await expect.poll(async () => JSON.stringify(await json(check.get(`/api/employees/${emp.id}`)))).toContain("Late to site");
  await check.dispose();
});

test("long lists page at 50 rows and every client is reachable", async ({ page }) => {
  const ctx = await api("admin");
  const tag = `Pg${uid()}`;
  for (let i = 1; i <= 52; i += 1) {
    await json(ctx.post("/api/clients", { data: { name: `${tag} client ${String(i).padStart(2, "0")}` } }));
  }
  const all = await json(ctx.get("/api/clients"));
  expect(all.filter((c) => c.name.startsWith(tag))).toHaveLength(52);
  await ctx.dispose();

  await page.goto("/clients");
  await page.getByTestId("clients-search").fill(tag);
  await expect(page.getByTestId("pager-clients-range")).toHaveText(/Showing 1–50 of 52/);
  await page.getByTestId("pager-clients-next").click();
  await expect(page.getByTestId("pager-clients-range")).toHaveText(/Showing 51–52 of 52/);
  await page.getByTestId("clients-search").fill(`${tag} client 01`);
  await expect(page.getByTestId("pager-clients")).toHaveCount(0);       // short list: no pager
});

test("accounting sections are grouped by what you are doing", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "grouped grid is the desktop layout; mobile uses the grouped select");
  await page.goto("/accounting");
  const groups = { overview: ["dashboard", "validation"], in: ["income", "receivables", "commissions"],
    out: ["expense", "recurring"], books: ["daybook", "ledgers", "bank"], reports: ["reports", "balance", "cashflow"], setup: ["coa"] };
  for (const [g, tabs] of Object.entries(groups)) {
    for (const t of tabs) await expect(page.getByTestId(`acc-group-${g}`).getByTestId(`tab-${t}`)).toBeVisible();
  }
  await page.getByTestId("tab-balance").click();
  await expect(page.getByTestId("tab-balance")).toHaveAttribute("aria-current", "page");
});
