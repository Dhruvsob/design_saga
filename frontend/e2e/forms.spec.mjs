// Searchable selectors (UX-04): long client/project/vendor/employee/account
// lists can be searched and chosen by mouse or keyboard on desktop and mobile,
// and the chosen value is what the form saves.
import { test, expect } from "@playwright/test";
import { api, json, uid, authFile } from "./helpers.mjs";

test.use({ storageState: authFile("admin") });

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
});

test("client picker searches a long list and the invoice saves that client", async ({ page }) => {
  const ctx = await api("admin");
  const tag = uid();
  for (let i = 0; i < 8; i++) await json(ctx.post("/api/clients", { data: { name: `Filler ${tag} ${i}` } }));
  const target = await json(ctx.post("/api/clients", { data: { name: `Zebra Interiors ${tag}` } }));

  const clientsLoaded = page.waitForResponse((r) => r.url().includes("/api/clients") && r.ok());
  await page.goto("/invoices");
  await clientsLoaded;
  await page.getByRole("button", { name: /new invoice/i }).click();
  const client = page.getByRole("combobox", { name: /select client/i });
  await client.click();
  const search = page.getByPlaceholder("Type to search…");
  await expect(search, "search appears for long lists").toBeVisible();
  await search.fill(`Zebra Interiors ${tag}`);
  await page.keyboard.press("Enter");
  await expect(client).toContainText(`Zebra Interiors ${tag}`);
  await expect(client).toHaveAttribute("data-value", target.id);

  // Keyboard: ArrowDown opens, Escape closes, focus stays on the field.
  await client.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByPlaceholder("Type to search…")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByPlaceholder("Type to search…")).toHaveCount(0);

  await page.getByPlaceholder("Description").first().fill("Concept design");
  await page.getByPlaceholder("Rate").first().fill("1000");
  await page.getByTestId("invoice-submit").click();
  await expect.poll(async () => {
    const rows = await json(ctx.get("/api/invoices?doc_type=invoice"));
    return rows.some((r) => r.client_id === target.id);
  }, { message: "invoice saved with the searched client" }).toBe(true);
  await ctx.dispose();
});

test("double-clicking Save creates one record, not two", async ({ page }) => {
  const ctx = await api("admin");
  const name = `Double Click ${uid()}`;
  await page.goto("/clients");
  await page.getByRole("button", { name: /new client/i }).click();
  await page.getByTestId("client-name").fill(name);
  const save = page.getByTestId("client-submit");
  await save.dblclick();
  await page.waitForTimeout(1500);
  const rows = (await json(ctx.get("/api/clients"))).filter((c) => c.name === name);
  expect(rows, "exactly one client saved").toHaveLength(1);
  await ctx.dispose();
});
