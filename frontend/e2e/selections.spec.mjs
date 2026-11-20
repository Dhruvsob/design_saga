// Room-wise selections (P2.3) and quotation acceptance through the client
// portal: the studio proposes, the client decides with their personal link,
// the studio sees who approved, and purchasing picks up only approved items.
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile, closeExtraContexts } from "./helpers.mjs";

test.afterEach(closeExtraContexts);
test.use({ storageState: authFile("admin") });
test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
});

async function projectWithClientLink(ctx) {
  const client = await json(ctx.post("/api/clients", { data: { name: `Mehta ${uid()}` } }));
  const project = await json(ctx.post("/api/projects", { data: {
    name: `Juhu Residence ${uid()}`, client_id: client.id, project_type: "Residential", engagement_type: "turnkey" } }));
  const person = await json(ctx.post(`/api/projects/${project.id}/portal-people`, { data: { name: "Anita Mehta" } }));
  return { client, project, token: person.token };
}

test("a selection goes to the client, comes back approved, and becomes a purchase line", async ({ page, browser }) => {
  const ctx = await api("admin");
  const { project, token } = await projectWithClientLink(ctx);
  const item = `Counter top ${uid()}`;

  await page.goto(`/projects/${project.id}?tab=Selections`);
  await page.getByTestId("selection-add").click();
  await page.getByTestId("selection-room").fill("Kitchen");
  await page.getByTestId("selection-item").fill(item);
  await page.getByTestId("selection-spec").fill("Quartz, 20 mm, honed, mitred edge");
  await page.getByTestId("selection-save").click();
  const row = page.locator('[data-testid^="selection-row-"]').filter({ hasText: item });
  await expect(row).toContainText("To send");
  const id = (await row.getAttribute("data-testid")).replace("selection-row-", "");

  await page.getByTestId(`selection-actions-${id}`).click();
  await page.getByTestId(`selection-send-${id}`).click();
  await expect(page.getByTestId(`selection-status-${id}`)).toHaveText("Waiting for client");

  // The client decides in the portal with their personal link (no sign-in).
  const portal = await (await browser.newContext({ storageState: { cookies: [], origins: [] } })).newPage();
  await portal.goto(`/portal/${token}`);
  const card = portal.locator('[data-testid^="portal-approval-"]').filter({ hasText: `Kitchen: ${item}` });
  await expect(card).toContainText("Material or finish");
  await expect(card).toContainText("Quartz, 20 mm, honed");
  await card.getByTestId("portal-approve").click();
  await card.getByTestId("portal-decision-confirm").click();
  await expect(portal.getByText(/is approved/)).toBeVisible();

  await page.reload();
  await expect(page.getByTestId(`selection-status-${id}`)).toHaveText("Approved");
  await expect(page.getByTestId(`selection-row-${id}`)).toContainText("Anita Mehta (client) approved");

  // Purchasing: the project's approved selection becomes an order line.
  await page.goto("/purchase-orders");
  await page.getByTestId("create-po-btn").click();
  const form = page.getByTestId("po-create-form");
  await form.getByTestId("po-project").click();
  await page.getByRole("option", { name: project.name, exact: true }).click();
  await form.getByTestId("po-add-approved").click();
  await expect(form.locator('input[placeholder="Item"]').first()).toHaveValue(`Kitchen: ${item}`);
  await expect(form.getByLabel("Line 1 specification")).toHaveValue("Quartz, 20 mm, honed, mitred edge");
  await ctx.dispose();
});

test("the client accepts the exact quotation version from the portal", async ({ page, browser }) => {
  const ctx = await api("admin");
  const { client, project, token } = await projectWithClientLink(ctx);
  const q = await json(ctx.post("/api/quotations-adv", { data: {
    type: "turnkey", project_title: "Juhu interiors", client_id: client.id, project_id: project.id } }));
  await json(ctx.put(`/api/quotations-adv/${q.id}`, { data: { boq: [{ category: "Carpentry", items: [
    { description: "Wardrobe, 8 ft", unit: "nos", quantity: 2, rate: 85000, margin_pct: 10 }] }] } }));

  await page.goto(`/quotations/${q.id}`);
  await page.getByTestId("send-for-acceptance").click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId("client-acceptance")).toContainText("Waiting for the client");

  const portal = await (await browser.newContext({ storageState: { cookies: [], origins: [] } })).newPage();
  await portal.goto(`/portal/${token}`);
  const card = portal.locator('[data-testid^="portal-approval-"]').filter({ hasText: "Juhu interiors" });
  await expect(card).toContainText("Quotation");
  await card.getByTestId("portal-approve").click();
  await card.getByTestId("portal-decision-confirm").click();
  await expect(portal.getByText(/is approved/)).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("client-acceptance")).toContainText("Accepted by Anita Mehta");
  await expect(page.getByTestId("client-acceptance")).toContainText("version 1");
  await ctx.dispose();
});
