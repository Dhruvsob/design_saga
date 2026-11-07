// One-off audit helper: screenshot every main screen as the QA admin.
// Run: node e2e/audit-shots.mjs <outDir>   (local QA stack must be running)
import { chromium } from "@playwright/test";
import { authFile, baseURL } from "./helpers.mjs";

const out = process.argv[2];
const pages = process.argv.length > 3 ? process.argv.slice(3) : [
  "dashboard", "crm", "clients", "quotations", "projects", "tasks", "calendar", "vendors",
  "purchase-orders", "invoices", "accounting", "expenses", "loans", "employees", "attendance",
  "holidays", "settings/company", "admin/rbac", "settings/audit",
];
const browser = await chromium.launch();
const ctx = await browser.newContext({ baseURL, storageState: authFile("admin"), viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`${page.url()}: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`${page.url()}: console ${m.text().slice(0, 160)}`); });
const unlock = () => ctx.request.post("/api/auth/pin/unlock", {
  data: { pin: process.env.QA_PIN }, headers: { Origin: baseURL },
});
for (const p of pages) {
  await unlock();                                  // the App PIN locks idle sessions
  await page.goto(`/${p}`);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/${p.replace(/\//g, "_")}.png`, fullPage: true });
}
console.log(errors.length ? errors.join("\n") : "no page errors");
await browser.close();
