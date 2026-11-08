// Close & export: check -> Excel export -> close (lock) -> reopen with reason.
import { test, expect } from "@playwright/test";
import { api, json, accounts, today, uid, authFile, baseURL } from "./helpers.mjs";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "period logic is viewport independent");
});

const fyStart = () => {
  const t = new Date(Date.now() + 5.5 * 3600e3);
  return t.getUTCMonth() >= 3 ? t.getUTCFullYear() : t.getUTCFullYear() - 1;
};

test("books close only after check + export; locked days refuse entries; admin reopens with a reason", async ({ browser }) => {
  const ctx = await api("admin");
  const { cash } = await accounts(ctx);
  const income = (await json(ctx.get("/api/accounts"))).find((a) => a.type === "income" && a.active !== false);
  const y = fyStart() - 1;                         // last finished financial year
  const from = `${y}-04-01`, to = `${y + 1}-03-31`;
  const before = (await json(ctx.get("/api/accounting/periods"))).locked_through;
  expect(before ?? null).toBeNull();

  // a back-dated entry inside last year, while it is still open
  const posted = await json(ctx.post("/api/journal-entries", { data: {
    date: `${y + 1}-03-20`, narration: `Year-end fee ${uid()}`,
    lines: [{ account_id: cash.id, debit: 2500, credit: 0 }, { account_id: income.id, debit: 0, credit: 2500 }],
  } }));

  // employees can't export or close
  const staff = await api("employee");
  expect((await staff.post(`/api/accounting/periods/export?from_date=${from}&to_date=${to}`)).status()).toBe(403);
  expect((await staff.post("/api/accounting/periods/close", { data: { through_date: to, export_id: "x" } })).status()).toBe(403);
  await staff.dispose();

  const check = await json(ctx.get(`/api/accounting/periods/check?from_date=${from}&to_date=${to}`));
  expect(check.blockers, JSON.stringify(check.blockers)).toEqual([]);
  expect(check.entries).toBeGreaterThanOrEqual(1);
  expect((await ctx.get(`/api/accounting/periods/check?from_date=${today()}&to_date=2099-12-31`)).ok()).toBe(true);
  expect((await json(ctx.get(`/api/accounting/periods/check?from_date=${today()}&to_date=2099-12-31`))).ok, "future period").toBe(false);
  expect((await ctx.post("/api/accounting/periods/close", { data: { through_date: to, export_id: "pex_missing" } })).status(),
    "no export, no close").toBe(409);

  // UI: check -> download -> close
  const page = await (await browser.newContext({ baseURL, storageState: authFile("admin"), acceptDownloads: true })).newPage();
  await page.goto("/accounting?tab=close");
  await expect(page.getByTestId("period-lock-status")).toContainText("No period is closed yet", { timeout: 20000 });
  await page.getByTestId("period-fy").selectOption(`${y}-${String(y + 1).slice(-2)}`);
  await page.getByTestId("period-part").selectOption("year");
  await expect(page.getByTestId("period-close-btn")).toBeDisabled();
  await page.getByTestId("period-check").click();
  await expect(page.getByTestId("period-check-result")).toContainText("Ready to close", { timeout: 30000 });
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("period-export").click()]);
  expect(download.suggestedFilename()).toBe(`books-${from}-to-${to}.xlsx`);
  const file = await download.path();
  const fs = await import("node:fs");
  expect(fs.readFileSync(file).subarray(0, 2).toString()).toBe("PK");       // a real .xlsx (zip)
  await expect(page.getByTestId("period-export-done")).toContainText("SHA-256");
  if (await page.getByTestId("period-accept").count()) await page.getByTestId("period-accept").check();
  await page.getByTestId("period-close-btn").click();
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId("period-lock-status")).toContainText(`Books closed up to 31/03/${y + 1}`, { timeout: 20000 });
  await expect(page.getByTestId("period-history")).toContainText("Closed");

  // the lock holds everywhere money is written
  const late = await ctx.post("/api/journal-entries", { data: {
    date: `${y + 1}-03-31`, narration: "Late entry",
    lines: [{ account_id: cash.id, debit: 10, credit: 0 }, { account_id: income.id, debit: 0, credit: 10 }],
  } });
  expect(late.status()).toBe(409);
  expect((await late.json()).detail).toContain(`closed up to 31/03/${y + 1}`);
  const del = await ctx.post(`/api/journal-entries/${posted.id}/correct`, { data: { date: `${y + 1}-03-20`, amount: 3000, narration: "fix" } });
  expect(del.status(), "correcting in place would rewrite closed books").toBe(409);
  const rev = await ctx.post(`/api/journal-entries/${posted.id}/reverse`, { data: {} });
  expect(rev.ok(), "a reversal dated today is still allowed").toBe(true);
  // reports for the closed year still work
  expect((await ctx.get(`/api/accounting/reports/pl?from_date=${from}&to_date=${to}`)).ok()).toBe(true);

  // reopen: admin + reason
  await page.getByTestId("period-reopen").click();
  await page.getByTestId("form-field-reason").fill("Auditor asked for a reclassification");
  await page.getByTestId("confirm-ok").click();
  await expect(page.getByTestId("period-lock-status")).toContainText("No period is closed yet", { timeout: 20000 });
  await expect(page.getByTestId("period-history")).toContainText("Auditor asked");
  const audit = await json(ctx.get("/api/accounting/periods"));
  expect(audit.history.map((h) => h.action).slice(0, 2)).toEqual(["reopen", "close"]);
  await ctx.dispose();
});
