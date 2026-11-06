// Project phase templates (PRJ-01): apply, track, fee milestones, access.
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { api, json, uid, authFile } from "./helpers.mjs";

test.use({ storageState: authFile("admin") });

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
  for (const role of ["admin", "employee"]) await (await api(role)).dispose();
});

test("apply consultancy phases with fee milestones, then track progress", async ({ page }, testInfo) => {
  const ctx = await api("admin");
  const project = await json(ctx.post("/api/projects", { data: {
    name: `Phase QA ${uid()}`, budget: 300000, start_date: "2026-04-01", engagement_type: "consultancy",
  } }));

  await page.goto(`/projects/${project.id}`);
  await page.getByTestId("tab-Phases").click();
  await expect(page.getByTestId("phase-setup")).toBeVisible();
  await page.getByTestId("template-consultancy").click();
  await page.getByTestId("phase-milestones").check();
  await page.getByTestId("phase-apply").click();
  await expect(page.getByTestId("phase-plan")).toBeVisible();
  await expect(page.getByTestId("phase-7")).toBeVisible();

  const { phases, summary } = await json(ctx.get(`/api/projects/${project.id}/phases`));
  expect(phases).toHaveLength(8);
  expect(phases[0].planned_start).toBe("2026-04-01");
  expect(summary.progress_pct).toBe(0);
  const milestones = await json(ctx.get(`/api/projects/${project.id}/milestones`));
  const list = Array.isArray(milestones) ? milestones : milestones.items || milestones.milestones || [];
  expect(list).toHaveLength(8);
  expect(Math.round(list.reduce((s, m) => s + m.amount, 0) * 100)).toBe(30000000);

  await page.getByTestId("phase-status-0").selectOption("in_progress");
  await expect(page.getByText("Current phase:")).toContainText(phases[0].name);
  const firstDeliverable = page.getByTestId(`deliverable-${phases[0].deliverables[0].id}`);
  await firstDeliverable.click();
  await expect(firstDeliverable).toHaveAttribute("aria-pressed", "true");

  const again = await ctx.post(`/api/projects/${project.id}/phases/apply`, { data: { template: "turnkey" } });
  expect(again.status(), "a template cannot be applied twice").toBe(409);

  if (testInfo.project.name === "desktop") {
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).include('[data-testid="phase-plan"]').analyze();
    expect(axe.violations.map((v) => v.id)).toEqual([]);
  }
  await ctx.dispose();
});

test("employees cannot create or change a phase plan", async () => {
  const admin = await api("admin");
  const project = await json(admin.post("/api/projects", { data: { name: `Phase RBAC ${uid()}`, engagement_type: "turnkey" } }));
  const employee = await api("employee");
  const res = await employee.post(`/api/projects/${project.id}/phases/apply`, { data: { template: "turnkey" } });
  expect([403, 404]).toContain(res.status());
  expect((await json(admin.get(`/api/projects/${project.id}/phases`))).phases).toHaveLength(0);
  await admin.dispose();
  await employee.dispose();
});
