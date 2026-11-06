import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { api } from "./helpers.mjs";

const auth = (role) => fileURLToPath(new URL(`./.auth/${role}.json`, import.meta.url));

// Long runs can exceed the 5-minute App PIN inactivity lock; unlock the
// stored sessions before each test so pages render instead of the PIN screen.
test.beforeEach(async () => {
  for (const role of ["admin", "employee"]) await (await api(role)).dispose();
});

async function openSidebar(page) {
  const menu = page.getByTestId("mobile-menu-btn");
  if (await menu.isVisible()) await menu.click();
  return page.getByTestId("app-sidebar");
}

test.describe("admin navigation", () => {
  test.use({ storageState: auth("admin") });

  test("shows workflow groups and group breadcrumb", async ({ page }) => {
    await page.goto("/invoices");
    const sidebar = await openSidebar(page);
    for (const g of ["sales", "projects", "procurement", "finance", "people", "admin"]) {
      await expect(sidebar.getByTestId(`nav-group-${g}`)).toBeVisible();
    }
    await expect(sidebar.getByTestId("nav-settings/audit")).toBeVisible();
    await expect(sidebar).not.toContainText("04b");
    const crumb = page.getByTestId("breadcrumb");
    if (await crumb.isVisible()) {
      await expect(crumb).toContainText("Finance");
      await expect(crumb).toContainText("Invoices");
    }
  });

  test("mobile drawer closes with its own button", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile only");
    await page.goto("/dashboard");
    await page.getByTestId("mobile-menu-btn").click();
    await page.getByTestId("mobile-menu-close").click();
    await expect(page.getByTestId("app-sidebar")).not.toBeInViewport();
  });

  test("sidebar has no horizontal overflow", async ({ page }) => {
    await page.goto("/dashboard");
    const sidebar = await openSidebar(page);
    const overflow = await sidebar.evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});

test.describe("employee navigation", () => {
  test.use({ storageState: auth("employee") });

  test("hides groups and links the role cannot open", async ({ page }) => {
    await page.goto("/dashboard");
    const sidebar = await openSidebar(page);
    await expect(sidebar.getByTestId("nav-group-projects")).toBeVisible();
    await expect(sidebar.getByTestId("nav-group-admin")).toHaveCount(0);
    for (const link of ["nav-accounting", "nav-invoices", "nav-loans", "nav-employees", "nav-quotations"]) {
      await expect(sidebar.getByTestId(link)).toHaveCount(0);
    }
  });
});

test.describe("getting started checklist", () => {
  test("admin sees setup steps that link to the right screens and can hide them", async ({ browser }) => {
    const page = await (await browser.newContext({ storageState: auth("admin") })).newPage();
    // Other suites fill in the QA company profile; once every step is done the
    // checklist correctly hides itself, so start from a known-incomplete step.
    const ctx = await api("admin");
    const org = await (await ctx.get("/api/org/current")).json();
    const complete = Boolean(org.branding?.logo_url && org.address?.line1 && org.gstin
      && (org.bank_details?.account || org.bank_details?.upi));
    await ctx.dispose();
    await page.goto("/dashboard");
    const card = page.getByTestId("getting-started");
    if (complete) {
      await page.locator("main").waitFor();
      await expect(card).toHaveCount(0);
      return;
    }
    await expect(card).toBeVisible();
    await expect(card.getByTestId("setup-step-logo")).toHaveAttribute("href", "/settings/company");
    await expect(card.getByTestId("setup-step-project")).toHaveAttribute("href", "/projects");
    await card.getByTestId("getting-started-dismiss").click();
    await expect(page.getByTestId("getting-started")).toHaveCount(0);
  });

  test("employees never see the admin setup checklist", async ({ browser }) => {
    const page = await (await browser.newContext({ storageState: auth("employee") })).newPage();
    await page.goto("/dashboard");
    await page.locator("main").waitFor();
    await expect(page.getByTestId("getting-started")).toHaveCount(0);
  });
});
