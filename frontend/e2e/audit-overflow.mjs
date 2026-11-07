// Which elements stick out past a phone screen? node e2e/audit-overflow.mjs <path>...
import { chromium } from "@playwright/test";
import { authFile, baseURL } from "./helpers.mjs";
const browser = await chromium.launch();
const ctx = await browser.newContext({ baseURL, storageState: authFile("admin"), viewport: { width: 390, height: 844 } });
const page = await ctx.newPage();
for (const p of process.argv.slice(2)) {
  await ctx.request.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN }, headers: { Origin: baseURL } });
  await page.goto(`/${p}`); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(600);
  const out = await page.evaluate(() => {
    const w = window.innerWidth; const rows = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.right > w + 1 && r.width > 0) {
        let scroller = false;
        for (let a = el.parentElement; a; a = a.parentElement) {
          const ox = getComputedStyle(a).overflowX;
          if (ox === "auto" || ox === "scroll" || ox === "hidden") { scroller = true; break; }
        }
        if (!scroller) rows.push(`${el.tagName.toLowerCase()}.${(el.className && el.className.baseVal === undefined ? el.className : "").toString().slice(0, 90)} right=${Math.round(r.right)} text=${(el.innerText || "").slice(0, 40).replace(/\s+/g, " ")}`);
      }
    }
    return rows.slice(0, 6);
  });
  console.log("==", p); console.log(out.join("\n"));
}
await browser.close();
