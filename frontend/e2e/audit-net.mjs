// One-off: list failing API calls per page.
import { chromium } from "@playwright/test";
import { authFile, baseURL } from "./helpers.mjs";
const browser = await chromium.launch();
const ctx = await browser.newContext({ baseURL, storageState: authFile("admin") });
const page = await ctx.newPage();
page.on("response", async (r) => { if (r.status() >= 400 && r.url().includes("/api/")) console.log(r.status(), r.request().method(), r.url().replace(baseURL, ""), (await r.text().catch(() => "")).slice(0, 160)); });
for (const p of process.argv.slice(2)) {
  await ctx.request.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN }, headers: { Origin: baseURL } });
  console.log("==", p); await page.goto(`/${p}`); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(500);
}
await browser.close();
