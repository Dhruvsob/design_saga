// Consultancy design proposal (DS-087): create, fill fees, save, PDF, type rules.
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { api, json, uid, authFile } from "./helpers.mjs";

test.use({ storageState: authFile("admin") });

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
  await (await api("admin")).dispose();
});

test("create a consultancy proposal, set the fee and get a branded PDF", async ({ page }, testInfo) => {
  const title = `4 BHK Apartment ${uid()}`;
  await page.goto("/quotations");
  await page.getByTestId("new-quotation-btn").click();
  await page.getByTestId("q-type-consultancy").click();
  await page.getByTestId("q-title").fill(title);
  await page.getByTestId("q-submit").click();

  await expect(page.getByTestId("proposal-editor")).toBeVisible();
  // the firm's standard scope is pre-filled and editable
  await expect(page.getByTestId("list-scope").getByRole("textbox")).toHaveCount(5);
  await page.getByTestId("add-scope").click();
  await page.getByTestId("list-scope").getByRole("textbox").last().fill("Landscape Design");
  await page.getByTestId("proposal-greeting").fill("Krunal Soni");
  await page.getByTestId("proposal-location").fill("Cloud 9, Near Shivranjani Cross Road");
  await page.getByTestId("proposal-sc-toggle").check();
  await page.getByTestId("proposal-sc-fee").fill("7500");

  await page.getByTestId("tab-Fees-&-schedule").click();
  await page.getByTestId("fee-total").fill("600000");
  await page.getByTestId("fee-advance").fill("50000");
  await page.getByTestId("fee-instalment").fill("30000");
  await page.getByTestId("fee-every").selectOption("2");
  await expect(page.getByTestId("fee-schedule").locator("tbody tr")).toHaveCount(20);
  await expect(page.getByTestId("fee-summary")).toContainText("19 instalments");

  await page.getByTestId("save-quotation-btn").click();
  await expect(page.getByTestId("save-quotation-btn")).toHaveText(/Saved/);
  await expect(page.getByTestId("builder-total")).toContainText("6,00,000");

  const id = page.url().split("/").pop();
  const ctx = await api("admin");
  const q = await json(ctx.get(`/api/quotations-adv/${id}`));
  expect(q.type).toBe("consultancy");
  expect(q.cost.grand_total).toBe(600000);
  expect(q.design_scope).toContain("Landscape Design");
  expect(q.proposal.site_coordinator).toMatchObject({ enabled: true, monthly_fee: 7500 });
  const pdf = await ctx.get(`/api/quotations-adv/${id}/pdf`);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  const bytes = await pdf.body();
  expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
  expect((bytes.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length).toBe(2);

  // invalid money is refused with a clear message, nothing saved
  const bad = await ctx.put(`/api/quotations-adv/${id}`, {
    data: { proposal: { fee: { total_fee: 1000, advance_amount: 5000 } } },
  });
  expect(bad.status()).toBe(400);

  if (testInfo.project.name === "desktop") {
    await page.getByTestId("tab-Proposal").click();
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"])
      .include('[data-testid="proposal-editor"]').analyze();
    expect(axe.violations.map((v) => v.id)).toEqual([]);
  }
  await ctx.dispose();
});

test("type is fixed once sent; turnkey quotations keep their own builder", async ({ page }) => {
  const ctx = await api("admin");
  const turnkey = await json(ctx.post("/api/quotations-adv", { data: { type: "turnkey", project_title: `Villa ${uid()}` } }));
  expect(turnkey.proposal).toBeNull();
  await page.goto(`/quotations/${turnkey.id}`);
  await expect(page.getByTestId("tab-BOQ-Builder")).toBeVisible();

  const consult = await json(ctx.post("/api/quotations-adv", { data: { type: "consultancy", project_title: `Flat ${uid()}` } }));
  await json(ctx.post(`/api/quotations-adv/${consult.id}/status`, { data: { status: "sent" } }));
  const change = await ctx.put(`/api/quotations-adv/${consult.id}`, { data: { type: "turnkey" } });
  expect(change.status()).toBe(409);
  await ctx.dispose();
});
