// Phase 2 (07_PHASED_PLAN): Payroll as its own page, Attendance in five tabs,
// lighter task filters/cards, calendar legend chips as filters.
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile, today } from "./helpers.mjs";

test.use({ storageState: authFile("admin") });
test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
  for (const role of ["admin", "employee"]) await (await api(role)).dispose();
});

test("payroll page: pay a salary from the month list, edit it, see the slip, cancel it", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "one layout is enough for the money flow");
  const ctx = await api("admin");
  const emp = await json(ctx.post("/api/employees", { data: {
    first_name: "Payroll", last_name: `QA${uid()}`, salary: { basic: 18000 },
  } }));
  const month = "2026-09";

  await page.goto(`/payroll?month=${month}`);
  await expect(page.getByTestId("nav-payroll")).toHaveAttribute("aria-current", "page");
  const row = page.getByTestId(`payroll-row-${emp.id}`);
  await expect(row).toBeVisible();
  await expect(page.getByTestId(`payroll-status-${emp.id}`)).toContainText("To pay");

  // Pay from the list: the month is already chosen, so the form has no month picker.
  await page.getByTestId(`payroll-pay-${emp.id}`).click();
  const dialog = page.getByTestId("payroll-pay-dialog");
  await expect(dialog).toContainText("September 2026");
  await expect(dialog.getByLabel("Month")).toHaveCount(0);
  await expect(dialog.getByTestId("pay-from")).toBeVisible();            // first cash/bank account is chosen
  const payBtn = dialog.getByTestId("pay-salary-btn");
  await expect(payBtn).toBeEnabled();
  await payBtn.click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId(`payroll-status-${emp.id}`)).toContainText("Paid");

  const runs = await json(ctx.get(`/api/payroll/runs?employee_id=${emp.id}`));
  const run = runs.find((r) => r.status === "paid" && r.year === 2026 && r.month === 9);
  expect(run, "one live salary for September").toBeTruthy();

  // Edit what was paid; the list shows the corrected amount.
  await page.getByTestId(`payroll-actions-${emp.id}`).click();
  await page.getByTestId(`payroll-edit-${emp.id}`).click();
  await page.getByTestId("form-field-net").fill("15000");
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId(`net-${emp.id}`)).toContainText("15,000");

  // The slip opens in the in-app PDF preview.
  await page.getByTestId(`payroll-slip-${emp.id}`).click();
  await expect(page.getByTestId("pdf-preview")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("pdf-preview")).toHaveCount(0);

  // Cancel: the month can be paid again.
  await page.getByTestId(`payroll-actions-${emp.id}`).click();
  await page.getByTestId(`payroll-cancel-${emp.id}`).click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId(`payroll-status-${emp.id}`)).toContainText("To pay");
  await expect(page.getByTestId(`payroll-pay-${emp.id}`)).toBeVisible();

  // Filters: "Paid" hides the unpaid row.
  await page.getByTestId("payroll-show-paid").click();
  await expect(row).toHaveCount(0);
  await page.getByTestId("payroll-show-all").click();
  await page.getByTestId("payroll-search").fill(emp.last_name);
  await expect(page.locator('[data-testid^="payroll-row-"]')).toHaveCount(1);
  await ctx.dispose();
});

test("attendance has five tabs; old links still land in the right place", async ({ page }) => {
  await page.goto("/attendance");
  const tabs = page.getByRole("tablist", { name: "Attendance" }).getByRole("tab");
  await expect(tabs).toHaveText(["Today", "Monthly sheet", "Leaves", "Requests", "Settings"]);

  await page.getByTestId("tab-settings").click();
  await expect(page).toHaveURL(/tab=settings/);
  await expect(page.getByTestId("setup-tab")).toBeVisible();
  await page.getByTestId("settings-section-policy").click();
  await expect(page.getByTestId("geo-policy-tab")).toBeVisible();

  await page.getByTestId("tab-leaves").click();
  await expect(page.getByTestId("team-leaves")).toBeVisible();

  await page.goto("/attendance?tab=geo");                                 // old "Office & Leave Policy"
  await expect(page.getByTestId("geo-policy-tab")).toBeVisible();
  await page.goto("/attendance?tab=live");                                // old "Live Board"
  await expect(page.getByTestId("team-dashboard")).toBeVisible();
  await page.goto("/attendance?tab=payroll");                             // payroll moved to its own page
  await expect(page).toHaveURL(/\/payroll/);
  await expect(page.getByTestId("payroll-page")).toBeVisible();
});

test("tasks: search, project and member up front; the rest under More filters; cards drop the repeated status", async ({ page }) => {
  const ctx = await api("admin");
  const plain = await json(ctx.post("/api/tasks", { data: { title: `Plain ${uid()}`, status_detail: "Pending", priority: "medium" } }));
  const held = await json(ctx.post("/api/tasks", { data: { title: `Held ${uid()}`, status_detail: "On Hold", priority: "high" } }));
  await ctx.dispose();

  await page.goto("/tasks");
  await expect(page.getByTestId("task-search")).toBeVisible();
  await expect(page.getByTestId("filter-project")).toBeVisible();
  await expect(page.getByTestId("filter-member")).toBeVisible();
  await expect(page.getByTestId("filter-area")).toHaveCount(0);

  // "Pending" in To do only repeats the column; "On Hold" in Review says more.
  await expect(page.getByTestId(`task-${plain.id}`)).toBeVisible();
  await expect(page.getByTestId(`task-status-${plain.id}`)).toHaveCount(0);
  await expect(page.getByTestId(`task-status-${held.id}`)).toContainText("On Hold");

  await page.getByTestId("more-filters-btn").click();
  await page.getByTestId("filter-priority").selectOption("high");
  await expect(page.getByTestId("more-filters-count")).toHaveText("1");
  await expect(page.getByTestId(`task-${held.id}`)).toBeVisible();
  await expect(page.getByTestId(`task-${plain.id}`)).toHaveCount(0);
  await page.getByTestId("clear-filters").click();
  await expect(page.getByTestId(`task-${plain.id}`)).toBeVisible();
});

test("calendar legend chips filter the calendar", async ({ page }) => {
  const ctx = await api("admin");
  const day = today();
  const meet = `Legend meet ${uid()}`;
  const note = `Legend note ${uid()}`;
  await json(ctx.post("/api/calendar/events", { data: { title: meet, date: day, kind: "meeting", visibility: "org" } }));
  await json(ctx.post("/api/calendar/events", { data: { title: note, date: day, kind: "reminder", visibility: "org" } }));
  await ctx.dispose();

  await page.goto("/calendar");
  await page.getByTestId("view-agenda").click();
  await expect(page.getByText(meet).first()).toBeVisible();
  await expect(page.getByText(note).first()).toBeVisible();

  await page.getByTestId("filter-meeting").click();                       // only meetings
  await expect(page.getByTestId("filter-meeting")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(meet).first()).toBeVisible();
  await expect(page.getByText(note)).toHaveCount(0);

  await page.getByTestId("filter-reminder").click();                      // meetings + reminders
  await expect(page.getByText(note).first()).toBeVisible();

  await page.getByTestId("filter-all").click();                           // everything again
  await expect(page.getByTestId("filter-all")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("filter-meeting")).toHaveAttribute("aria-pressed", "false");
});
