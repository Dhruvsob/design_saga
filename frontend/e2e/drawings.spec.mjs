// Drawing register on the project page: add, issue rev A with a PDF, ask for changes, issue rev B, approve.
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile, baseURL, openProjectTab } from "./helpers.mjs";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "register logic is viewport independent");
});

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

test("drawing register: revisions A then B, supersession, approval, staff cannot approve", async ({ browser }) => {
  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Drw ${uid()}` } }));
  const project = await json(ctx.post("/api/projects", { data: { name: `Bungalow ${uid()}`, client_id: client.id, engagement_type: "consultancy" } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto(`/projects/${project.id}`);
  await openProjectTab(page, "Drawings", { timeout: 20000 });
  await page.getByTestId("drawing-add").click();
  await page.getByTestId("form-field-number").fill("a-101");
  await page.getByTestId("form-field-title").fill("Ground floor plan");
  await page.getByTestId("confirm-ok").click();
  const row = page.getByTestId("drawing-row-A-101");
  await expect(row).toContainText("Ground floor plan", { timeout: 20000 });

  await page.getByTestId("drawing-issue-A-101").click();
  await page.getByTestId("drawing-file").setInputFiles({ name: "a101-a.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByTestId("drawing-purpose").selectOption("approval");
  await page.getByTestId("drawing-issue-save").click();
  await expect(row).toContainText("For approval", { timeout: 20000 });
  await expect(row).toContainText("Issued");

  await page.getByTestId("drawing-actions-A-101").click();
  await page.getByRole("menuitem", { name: "Ask for changes" }).click();
  await page.getByTestId("form-field-comment").fill("Bigger utility area");
  await page.getByTestId("confirm-ok").click();
  await expect(row).toContainText("Changes asked", { timeout: 20000 });

  await page.getByTestId("drawing-issue-A-101").click();
  await expect(page.getByTestId("drawing-issue-form")).toContainText("Rev A will be marked superseded");
  await page.getByTestId("drawing-file").setInputFiles({ name: "a101-b.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByTestId("drawing-purpose").selectOption("construction");
  await page.getByTestId("drawing-issue-save").click();
  await expect(row).toContainText("For construction", { timeout: 20000 });
  await expect(row.locator("td").nth(2)).toContainText("B");

  const staff = await api("employee");
  const list = await json(ctx.get(`/api/projects/${project.id}/drawings`));
  const d = list.drawings[0];
  expect(d.revisions.map((r) => [r.rev, r.status])).toEqual([["A", "rejected"], ["B", "issued"]]);
  expect((await staff.post(`/api/drawings/${d.id}/revisions/B/decision`, { data: { decision: "approved" } })).status()).toBe(403);
  await staff.dispose();

  await page.getByTestId("drawing-actions-A-101").click();
  await page.getByRole("menuitem", { name: "Approve" }).click();
  await page.getByTestId("confirm-ok").click();
  await expect(row).toContainText("Approved", { timeout: 20000 });
  await expect(page.getByTestId("drawings-counts")).toContainText("1 approved");
  await page.getByTestId("drawing-actions-A-101").click();
  await page.getByRole("menuitem", { name: "Revision history" }).click();
  await expect(page.getByTestId("drawing-history")).toContainText("Bigger utility area");
  const xlsx = await ctx.get(`/api/projects/${project.id}/drawings/register.xlsx`);
  expect(xlsx.ok()).toBe(true);
  expect((await xlsx.body()).subarray(0, 2).toString()).toBe("PK");
  await ctx.dispose();
});
