// Accessibility audit (WCAG 2 A/AA via axe-core) over every primary page and
// its main create form. AUDIT=1 prints a full report instead of asserting.
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { authFile } from "./helpers.mjs";

const ROUTES = [
  "/dashboard", "/crm", "/clients", "/quotations", "/projects", "/tasks", "/calendar",
  "/vendors", "/purchase-orders", "/invoices", "/accounting", "/expenses", "/loans",
  "/employees", "/attendance", "/holidays", "/settings/company", "/admin/rbac", "/settings/audit",
];
// Primary "create" buttons opened so their forms are audited too.
const CREATE = /^(\+\s*)?(new|add|create|record)\b/i;
const AUDIT = process.env.AUDIT === "1";
// Rules enforced as a release gate once fixed (others are reported only).
const ENFORCED = new Set([
  "button-name", "link-name", "label", "select-name", "image-alt", "aria-required-attr",
  "aria-valid-attr", "aria-valid-attr-value", "duplicate-id-aria", "nested-interactive",
  "color-contrast",
]);

test.use({ storageState: authFile("admin") });

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "accessibility audit runs once");
});

async function scan(page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .exclude(".sonner-toaster")
    .analyze();
  return result.violations;
}

test("primary pages and create forms meet WCAG A/AA basics", async ({ page }) => {
  test.setTimeout(420_000);
  const report = new Map();
  const add = (where, violations) => {
    for (const v of violations) {
      const key = `${v.id} [${v.impact}]`;
      const row = report.get(key) || { help: v.help, pages: new Set(), targets: new Set(), count: 0 };
      row.pages.add(where);
      v.nodes.slice(0, 3).forEach((n) => row.targets.add(n.target.join(" ")));
      row.count += v.nodes.length;
      report.set(key, row);
    }
  };
  for (const path of ROUTES) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
    add(path, await scan(page));
    const create = page.locator("main button").filter({ hasText: CREATE }).first();
    if (await create.count() && await create.isVisible()) {
      await create.click().catch(() => {});
      await page.waitForTimeout(500);
      add(`${path} (form)`, await scan(page));
    }
  }
  const lines = [...report.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .map(([rule, r]) => `${rule} x${r.count} :: ${r.help}\n   pages: ${[...r.pages].join(", ")}\n   e.g. ${[...r.targets].slice(0, 3).join(" | ")}`);
  if (AUDIT) {
    console.log(`\n=== ${report.size} rules violated ===\n${lines.join("\n")}`);
    return;
  }
  const enforced = [...report.keys()].filter((k) => ENFORCED.has(k.split(" ")[0]));
  expect(enforced, lines.filter((l) => ENFORCED.has(l.split(" ")[0])).join("\n")).toEqual([]);
});
