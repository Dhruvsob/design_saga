// Probe read endpoints with bad input; any 5xx is a bug (should be a clear 4xx).
import { request } from "@playwright/test";
import { authFile, baseURL } from "./helpers.mjs";

const ctx = await request.newContext({ baseURL, storageState: authFile("admin"), extraHTTPHeaders: { Origin: baseURL } });
await ctx.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN } });
const probes = [
  "/api/attendance/monthly?year=2026&month=13", "/api/attendance/monthly?year=0&month=1",
  "/api/attendance/my-salary?year=2026&month=0", "/api/attendance/me/summary?year=abc&month=1",
  "/api/journal-entries?from_date=2026-02-30", "/api/journal-entries?from_date=notadate&to_date=x",
  "/api/journal-entries?limit=-5&offset=-1", "/api/accounting/reports/pl?from_date=2026-13-01",
  "/api/accounting/reports/pl?fy=abcd", "/api/accounting/reports/balance-sheet?as_of=31-10-2026",
  "/api/accounting/reports/cash-flow?from_date=2026-11-30&to_date=2026-01-01",
  "/api/accounting/ledger/client/nope", "/api/accounting/ledger/banana/x",
  "/api/accounting/accounts/acc_nope/ledger", "/api/accounting/received-payments?from_date=zz",
  "/api/calendar/feed?start=2026-13-01&end=2026-12-31", "/api/calendar/feed?start=abc&end=def",
  "/api/projects/prj_nope", "/api/clients/cli_nope", "/api/vendors/vnd_nope", "/api/employees/emp_nope",
  "/api/tasks/tsk_nope", "/api/invoices/inv_nope", "/api/invoices/inv_nope/pdf", "/api/payroll/runs/pr_nope/slip.pdf",
  "/api/accounting/reminders/rem_nope/pdf", "/api/employees/emp_nope/salary/preview?year=2026&month=10",
  "/api/vendors/vnd_nope/ledger", "/api/vendors/vnd_nope/performance", "/api/projects/prj_nope/milestones",
  "/api/search?q=%5B%28%2A", "/api/vendors?q=%5B%28%2A", "/api/journal-entries?q=%5B%28%2A",
];
let bad = 0;
for (const url of probes) {
  const r = await ctx.get(url);
  if (r.status() >= 500) { bad += 1; console.log(r.status(), url, (await r.text()).slice(0, 140)); }
}
console.log(`probes ${probes.length}, server errors ${bad}`);
await ctx.dispose();
