// Bug sweep: every page × role × viewport. Prints one line per finding.
// Run: node e2e/audit-sweep.mjs   (local QA stack running, QA_PIN set)
import { chromium } from "@playwright/test";
import { authFile, baseURL } from "./helpers.mjs";

const PAGES = [
  "dashboard", "crm", "clients", "quotations", "projects", "tasks", "calendar", "vendors",
  "purchase-orders", "invoices", "invoices/reminders", "invoices/received", "accounting",
  "accounting?tab=receivables", "accounting?tab=daybook", "accounting?tab=reports", "accounting?tab=balance",
  "accounting?tab=cashflow", "accounting?tab=coa", "accounting?tab=commissions", "accounting?tab=validation",
  "expenses", "loans", "employees", "attendance", "holidays", "settings/company", "admin/rbac", "settings/audit",
];
const BAD_TEXT = [/\bundefined\b/, /\bNaN\b/, /Invalid Date/, /\[object Object\]/, /₹-\d/, /\bnull\b/];
const SNAKE = /\b[a-z]{3,}_[a-z_]{3,}\b/g;
const IGNORE_SNAKE = new Set(["e.g", "user_id"]);

const findings = [];
const note = (role, vp, page, kind, detail) => findings.push(`${role}\t${vp}\t${page}\t${kind}\t${detail}`);

async function detailLinks(ctx) {
  const pick = async (url, key = "id") => {
    const r = await ctx.request.get(`/api/${url}`);
    if (!r.ok()) return null;
    const body = await r.json();
    const rows = Array.isArray(body) ? body : body.items || body.rows || [];
    return rows[0]?.[key] || null;
  };
  const out = [];
  for (const [api, path] of [["projects", "projects"], ["clients", "clients"], ["vendors", "vendors"],
                             ["employees", "employees"], ["tasks", "tasks"], ["leads", "crm"]]) {
    const id = await pick(api);
    if (id) out.push(`${path}/${id}`);
  }
  return out;
}

const browser = await chromium.launch();
for (const role of ["admin", "employee"]) {
  for (const [vp, size] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
    const ctx = await browser.newContext({ baseURL, storageState: authFile(role), viewport: size });
    const page = await ctx.newPage();
    let current = "";
    page.on("pageerror", (e) => note(role, vp, current, "CRASH", e.message.slice(0, 160)));
    page.on("console", (m) => { if (m.type() === "error" && !/403|401|Failed to load resource/.test(m.text())) note(role, vp, current, "CONSOLE", m.text().slice(0, 160)); });
    page.on("response", async (r) => {
      if (!r.url().includes("/api/") || r.status() < 400) return;
      if (role === "employee" && r.status() === 403) return;   // permission refusals are expected for staff
      note(role, vp, current, `API ${r.status()}`, `${r.request().method()} ${r.url().replace(baseURL, "")} ${(await r.text().catch(() => "")).slice(0, 120)}`);
    });
    const pages = [...PAGES, ...(await detailLinks(ctx))];
    for (const p of pages) {
      current = p;
      await ctx.request.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN }, headers: { Origin: baseURL } });
      await page.goto(`/${p}`).catch((e) => note(role, vp, p, "NAV", e.message.slice(0, 120)));
      await page.waitForLoadState("networkidle").catch(() => {});
      await page.waitForTimeout(600);
      const text = await page.locator("main").innerText().catch(() => page.locator("body").innerText().catch(() => ""));
      for (const rx of BAD_TEXT) {
        const m = text.match(new RegExp(`.{0,40}${rx.source}.{0,40}`));
        if (m) note(role, vp, p, "TEXT", m[0].replace(/\s+/g, " "));
      }
      const snakes = [...new Set((text.match(SNAKE) || []).filter((w) => !IGNORE_SNAKE.has(w)))];
      if (snakes.length) note(role, vp, p, "RAW-CODE", snakes.slice(0, 8).join(", "));
      if (vp === "phone") {
        const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        if (over > 2) note(role, vp, p, "SIDEWAYS", `${over}px wider than the screen`);
      }
    }
    await ctx.close();
  }
}
await browser.close();
console.log(findings.length ? findings.join("\n") : "no findings");
console.log(`TOTAL ${findings.length}`);
