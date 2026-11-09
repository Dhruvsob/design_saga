// UX inspection helper: screenshots every main screen, detail page and tab,
// at desktop and phone width, and reports console/page errors.
// Run (local QA stack up): E2E_BASE_URL=http://127.0.0.1:5174 node e2e/tools/ux-sweep.mjs <outDir> [desktop|phone|all]
import { chromium, request as pwRequest } from "@playwright/test";
import { authFile, baseURL } from "../helpers.mjs";

const out = process.argv[2];
const mode = process.argv[3] || "all";
const browser = await chromium.launch();
const api = await pwRequest.newContext({ baseURL, storageState: authFile("admin"), extraHTTPHeaders: { Origin: baseURL } });
await api.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN } });
const first = async (path, pick = (x) => x) => {
  const r = await api.get(path); if (!r.ok()) return null;
  const d = await r.json(); const rows = Array.isArray(d) ? d : d.items || d.rows || d.employees || [];
  return pick(rows)?.[0] || null;
};
const project = await first("/api/projects", (r) => r.filter((p) => p.budget > 0).concat(r));
const vendor = await first("/api/vendors");
const employee = await first("/api/employees");
const client = await first("/api/clients");
const quote = await first("/api/quotations-adv");
const pages = [
  ["dashboard"], ["crm"], ["clients"], ["quotations"], ["projects"], ["tasks"], ["calendar"], ["vendors"],
  ["purchase-orders"], ["invoices"], ["invoices/reminders"], ["invoices/received"], ["accounting"],
  ["accounting?tab=receivables"], ["accounting?tab=daybook"], ["accounting?tab=ledgers"], ["accounting?tab=reports"],
  ["accounting?tab=coa"], ["accounting?tab=close"], ["accounting?tab=commissions"], ["expenses"], ["loans"],
  ["employees"], ["attendance"], ["payroll"], ["holidays"], ["live-map"], ["settings/company"], ["admin/rbac"], ["settings/audit"],
];
if (project) for (const t of ["Overview", "Phases", "Tasks", "Milestones", "Vendors", "Files", "Drawings", "Site visits", "Snags", "Invoices", "Activity"]) pages.push([`projects/${project.id}`, t]);
if (vendor) pages.push([`vendors/${vendor.id}`]);
if (employee) pages.push([`employees/${employee.id}`]);
if (client) pages.push([`clients/${client.id}`]);
if (quote) pages.push([`quotations/${quote.id}`]);

const errors = [];
for (const [width, height, tag] of [[1440, 900, "d"], [390, 844, "m"]]) {
  if ((mode === "desktop" && tag === "m") || (mode === "phone" && tag === "d")) continue;
  const ctx = await browser.newContext({ baseURL, storageState: authFile("admin"), viewport: { width, height } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${tag} ${page.url()}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|401|403/.test(m.text())) errors.push(`${tag} ${page.url()}: ${m.text().slice(0, 160)}`); });
  for (const [path, tab] of pages) {
    if (tag === "m" && (tab && tab !== "Overview")) continue;
    await ctx.request.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN }, headers: { Origin: baseURL } });
    await page.goto(`/${path}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    if (tab) { await page.goto(`/${path}?tab=${encodeURIComponent(tab)}`); await page.waitForLoadState("networkidle").catch(() => {}); }
    await page.waitForTimeout(700);
    const name = `${tag}_${path.replace(/[/?=&]/g, "_")}${tab ? `_${tab.replace(/\s/g, "-")}` : ""}`.replace(/_(prj|vnd|emp|cli|quo)_[a-z0-9]+/, "_$1");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    if (overflow) errors.push(`${tag} ${path}${tab ? ` [${tab}]` : ""}: horizontal page overflow`);
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: tag === "d" });
  }
  await ctx.close();
}
console.log(errors.length ? errors.join("\n") : "no errors");
await api.dispose();
await browser.close();
