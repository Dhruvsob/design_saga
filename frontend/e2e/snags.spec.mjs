// Site snags: raise with a photo -> mark fixed with a photo -> verify & close; reopen needs a reason.
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile, baseURL, openProjectTab } from "./helpers.mjs";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "snag logic is viewport independent");
});

// 1x1 JPEG
const JPG = Buffer.from("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=", "base64");

test("snag: raised with photo, fixed with photo, verified and closed; staff cannot verify", async ({ browser }) => {
  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Snag ${uid()}` } }));
  const project = await json(ctx.post("/api/projects", { data: { name: `Site ${uid()}`, client_id: client.id, engagement_type: "consultancy" } }));
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin") })).newPage();
  await page.goto(`/projects/${project.id}`);
  await openProjectTab(page, "Snags", { timeout: 20000 });
  await page.getByTestId("snag-add").click();
  await page.getByTestId("snag-title").fill("Cracked tile at entrance");
  await page.getByTestId("snag-photo").setInputFiles({ name: "crack.jpg", mimeType: "image/jpeg", buffer: JPG });
  await page.getByTestId("snag-save").click();
  const card = page.getByTestId("snag-SN-001");
  await expect(card).toContainText("Open", { timeout: 20000 });

  const { snags } = await json(ctx.get(`/api/projects/${project.id}/snags`));
  expect(snags[0].photos.map((p) => p.kind)).toEqual(["issue"]);
  const photo = await ctx.get(`/api/snags/${snags[0].id}/photos/${snags[0].photos[0].id}`);
  expect(photo.ok()).toBe(true);
  const staff = await api("employee");
  expect([403, 404]).toContain((await staff.post(`/api/snags/${snags[0].id}/status`, { data: { action: "close" } })).status());
  expect([403, 404]).toContain((await staff.get(`/api/snags/${snags[0].id}/photos/${snags[0].photos[0].id}`)).status());
  await staff.dispose();
  expect((await ctx.post(`/api/snags/${snags[0].id}/status`, { data: { action: "close" } })).status(), "close only after a fix").toBe(409);

  await page.getByTestId("snag-fix-SN-001").click();
  await page.getByTestId("snag-fix-photo").setInputFiles({ name: "fixed.jpg", mimeType: "image/jpeg", buffer: JPG });
  await page.getByTestId("snag-fix-save").click();
  await expect(card).toContainText("Fixed · to verify", { timeout: 20000 });
  await page.getByTestId("snag-close-SN-001").click();
  await page.getByTestId("confirm-ok").click();
  await page.getByRole("button", { name: /^All$/ }).click();
  await expect(card).toContainText("Closed", { timeout: 20000 });

  await page.getByTestId("snag-actions-SN-001").click();
  await page.getByRole("menuitem", { name: "Reopen" }).click();
  await page.getByTestId("form-field-note").fill("Grout missing");
  await page.getByTestId("confirm-ok").click();
  await expect(card).toContainText("reopened 1", { timeout: 20000 });
  await page.getByTestId("snag-actions-SN-001").click();
  await page.getByRole("menuitem", { name: "Photos & history" }).click();
  await expect(page.getByRole("dialog")).toContainText("Grout missing");
  await expect(page.getByTestId("snag-photos").locator("img")).toHaveCount(2, { timeout: 20000 });
  await ctx.dispose();
});
