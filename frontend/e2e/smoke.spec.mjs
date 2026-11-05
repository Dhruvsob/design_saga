// Every primary page and representative detail page must render without a
// runtime error. Catches blank-screen crashes (e.g. undefined identifiers)
// that lint/build and backend tests cannot see.
import { test, expect } from "@playwright/test";
import { api, json, authFile, uid } from "./helpers.mjs";

const ROUTES = [
  "/dashboard", "/crm", "/clients", "/quotations", "/projects", "/tasks", "/calendar",
  "/vendors", "/purchase-orders", "/invoices", "/accounting", "/expenses", "/loans",
  "/employees", "/attendance", "/holidays", "/settings/company", "/admin/rbac", "/settings/audit",
];

test.use({ storageState: authFile("admin") });

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  const phoneCheck = testInfo.titlePath.includes("phone layout");
  test.skip(!phoneCheck && testInfo.project.name !== "desktop", "crash smoke runs once");
});

async function expectRendersCleanly(page, path) {
  const errors = [];
  const onError = (e) => errors.push(String(e).slice(0, 300));
  page.on("pageerror", onError);
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  const main = page.locator("main");
  const rendered = await main.waitFor({ state: "visible", timeout: 20_000 }).then(() => true, () => false);
  page.off("pageerror", onError);
  expect(errors, `${path} has no runtime errors`).toEqual([]);
  expect(rendered, `${path} renders the application layout`).toBe(true);
  expect((await main.innerText()).trim().length, `${path} is not blank`).toBeGreaterThan(20);
}

test("primary pages render without runtime errors", async ({ page }) => {
  test.setTimeout(180_000);
  for (const path of ROUTES) await expectRendersCleanly(page, path);
});

test("detail pages render without runtime errors", async ({ page }) => {
  const ctx = await api("admin");
  const vendor = await json(ctx.post("/api/vendors", { data: { name: `Smoke Vendor ${uid()}` } }));
  const employee = await json(ctx.post("/api/employees", { data: { first_name: "Smoke", last_name: uid() } }));
  const client = await json(ctx.post("/api/clients", { data: { name: `Smoke Client ${uid()}` } }));
  await ctx.dispose();
  for (const path of [`/vendors/${vendor.id}`, `/employees/${employee.id}`, `/clients/${client.id}`]) {
    await expectRendersCleanly(page, path);
  }
  await page.goto(`/vendors/${vendor.id}`);
  for (const tab of ["commercial", "commissions", "projects", "documents"]) {
    const button = page.getByTestId(`vendor-tab-${tab}`);
    if (await button.count()) {
      await button.click();
      await expect(page.locator("main")).not.toBeEmpty();
    }
  }
});

test.describe("phone layout", () => {
  test.beforeEach(async ({ browserName }, testInfo) => {
    void browserName;
    test.skip(testInfo.project.name !== "mobile", "phone width only");
  });

  test("no page scrolls sideways on a phone", async ({ page }) => {
    test.setTimeout(180_000);
    const overflowing = [];
    for (const path of ROUTES) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
      const { sw, vw } = await page.evaluate(() => ({
        sw: document.documentElement.scrollWidth, vw: document.documentElement.clientWidth }));
      if (sw > vw + 1) overflowing.push(`${path} (${sw}px > ${vw}px)`);
    }
    expect(overflowing, "pages wider than the phone screen").toEqual([]);
  });
});
