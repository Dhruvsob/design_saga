// Lead -> client + project -> quotation -> accepted -> linked to the SAME project (no duplicate).
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile, baseURL } from "./helpers.mjs";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "chain logic is viewport independent");
});

test("lead to project to accepted quotation keeps one project per job", async ({ browser }) => {
  const ctx = await api("admin");
  const name = `Mehta ${uid()}`;
  const lead = await json(ctx.post("/api/leads", { data: { name, phone: `98${Date.now().toString().slice(-8)}`, project_type: "Residential", budget: 0 } }));
  const conv = await json(ctx.post(`/api/leads/${lead.id}/convert`));
  const projectId = conv.project_id || conv.project?.id;
  const clientId = conv.client_id || conv.client?.id;
  expect(projectId && clientId).toBeTruthy();
  expect((await ctx.post(`/api/leads/${lead.id}/convert`)).status(), "no second conversion").toBe(409);

  const quote = await json(ctx.post("/api/quotations-adv", { data: {
    type: "consultancy", project_title: `${name} residence`, client_id: clientId, client_name: name } }));
  await json(ctx.post(`/api/quotations-adv/${quote.id}/status`, { data: { status: "approved" } }));

  // UI: converting offers the lead's project
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto(`/quotations/${quote.id}`);
  await page.getByRole("button", { name: /convert/i }).first().click({ timeout: 20000 });
  await expect(page.getByTestId("form-field-project_id")).toBeVisible();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByText("Quotation linked to the existing project")).toBeVisible({ timeout: 20000 });
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}`));

  const projects = (await json(ctx.get("/api/projects"))).filter((p) => p.client_id === clientId);
  expect(projects, "still one project for this client").toHaveLength(1);
  expect(projects[0].from_quotation_id).toBe(quote.id);
  const q2 = await json(ctx.get(`/api/quotations-adv/${quote.id}`));
  expect([q2.status, q2.converted_project_id]).toEqual(["converted", projectId]);
  expect((await ctx.post(`/api/quotations-adv/${quote.id}/convert-to-project`, { data: { project_id: projectId } })).status()).toBe(409);

  // a second quotation cannot be linked to the same project; a different client's project is refused
  const quote2 = await json(ctx.post("/api/quotations-adv", { data: {
    type: "consultancy", project_title: `${name} annex`, client_id: clientId, client_name: name } }));
  await json(ctx.post(`/api/quotations-adv/${quote2.id}/status`, { data: { status: "approved" } }));
  expect((await ctx.post(`/api/quotations-adv/${quote2.id}/convert-to-project`, { data: { project_id: projectId } })).status()).toBe(409);
  const other = await json(ctx.post("/api/clients", { data: { name: `Other ${uid()}` } }));
  const otherProject = await json(ctx.post("/api/projects", { data: { name: `Other ${uid()}`, client_id: other.id, engagement_type: "consultancy" } }));
  expect((await ctx.post(`/api/quotations-adv/${quote2.id}/convert-to-project`, { data: { project_id: otherProject.id } })).status()).toBe(400);
  const fresh = await json(ctx.post(`/api/quotations-adv/${quote2.id}/convert-to-project`));
  expect(fresh.linked_existing).toBe(false);
  expect(fresh.project_id).not.toBe(projectId);
  await ctx.dispose();
});
