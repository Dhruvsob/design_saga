import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";

const auth = (role) => fileURLToPath(new URL(`./.auth/${role}.json`, import.meta.url));

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
