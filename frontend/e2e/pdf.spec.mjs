// Every generated PDF carries the tenant logo and company details from
// Company Settings. Uploads a test-only logo through the real API (this also
// exercises the self-hosted local logo storage), then downloads each PDF type.
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { api, json, accounts, today, uid } from "./helpers.mjs";

const LOGO = fs.readFileSync(fileURLToPath(new URL("./fixtures/qa-test-logo.png", import.meta.url)));
const OUT = process.env.E2E_PDF_DIR || "";

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name !== "desktop", "PDF output is viewport independent");
});

async function pdfOf(ctx, url, name) {
  const res = await ctx.get(url);
  expect(res.status(), `${name} downloads`).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/pdf");
  const body = await res.body();
  expect(body.subarray(0, 4).toString()).toBe("%PDF");
  // fpdf2 embeds raster images as XObjects; the logo is the only image used.
  expect(body.includes(Buffer.from("/Subtype /Image")), `${name} embeds the logo`).toBe(true);
  if (OUT) fs.writeFileSync(`${OUT}/${name}.pdf`, body);
  return body;
}

test("logo and company details appear on every PDF type", async () => {
  test.setTimeout(120_000);
  const ctx = await api("admin");
  const up = await ctx.post("/api/org/current/logo/upload", {
    multipart: { file: { name: "logo.png", mimeType: "image/png", buffer: LOGO } },
  });
  expect(up.status(), "logo upload works without external object storage").toBe(200);
  const { logo_url: logoUrl } = await up.json();
  expect(logoUrl).toMatch(/^\/api\/org\/logo\//);
  const served = await ctx.get(logoUrl);
  expect(served.status(), "uploaded logo is served back").toBe(200);

  await json(ctx.patch("/api/org/current", { data: {
    address: { line1: "QA Test Address", city: "Ahmedabad", state: "Gujarat", pincode: "380001" },
    phone: "+91 00000 00000", website: "example.com", gstin: "TESTGSTIN00000",
    bank_details: { bank: "QA Test Bank", account: "000000000000", ifsc: "TEST0000000" },
    branding: { tagline: "Architecture & Interior Design", logo_url: logoUrl },
  } }));

  const client = await json(ctx.post("/api/clients", { data: { name: `PDF Client ${uid()}` } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", status: "draft", tax_rate: 18,
    items: [{ description: "Concept design", quantity: 1, rate: 50000 }],
  } }));
  await pdfOf(ctx, `/api/invoices/${inv.id}/pdf`, "invoice");

  const quote = await json(ctx.post("/api/quotations-adv", { data: {
    type: "consultancy", project_title: "PDF QA Residence", client_name: client.name, area_sqft: 1800,
  } }));
  await pdfOf(ctx, `/api/quotations-adv/${quote.id}/pdf`, "quotation");

  const { bank } = await accounts(ctx);
  const emp = await json(ctx.post("/api/employees", { data: {
    first_name: "Pdf", last_name: `QA${uid()}`, salary: { basic: 30000 },
    bank: { account_number: "123456789012" },
  } }));
  const paid = await json(ctx.post(`/api/employees/${emp.id}/pay-salary`, { data: {
    year: 2026, month: 9, paid_from_account_id: bank.id, payment_method: "bank_transfer",
    reference: "NEFT-PDF", apply_attendance_deductions: false, payment_date: today(),
  } }));
  const slip = await pdfOf(ctx, `/api/payroll/runs/${paid.run.id}/slip.pdf`, "salary-slip");
  expect(slip.includes(Buffer.from("123456789012")), "full bank account is masked").toBe(false);
  await pdfOf(ctx, `/api/payroll/payslip.pdf?employee_id=${emp.id}&year=2026&month=9`, "attendance-payslip");

  const vendor = await json(ctx.post("/api/vendors", { data: { name: `PDF Vendor ${uid()}` } }));
  await json(ctx.post(`/api/vendors/${vendor.id}/commissions`, { data: { amount: 4000, recognition: "planned" } }));
  await pdfOf(ctx, `/api/vendors/${vendor.id}/commission-statement.pdf`, "commission-statement");
  await ctx.dispose();
});

test("invoice preview loads inside the app under production security headers", async ({ browser }) => {
  const { authFile, baseURL } = await import("./helpers.mjs");
  const ctx = await api("admin");
  const client = await json(ctx.post("/api/clients", { data: { name: `Preview ${uid()}` } }));
  const inv = await json(ctx.post("/api/invoices", { data: {
    client_id: client.id, doc_type: "invoice", status: "draft", tax_rate: 0,
    items: [{ description: "Concept design", quantity: 1, rate: 1000 }],
  } }));
  await ctx.dispose();

  // Same headers gamaa.in sends (Caddy + nginx), so a blocked frame fails here too.
  const csp = fs.readFileSync(fileURLToPath(new URL("../../deploy/nginx.conf", import.meta.url)), "utf8")
    .match(/Content-Security-Policy "([^"]+)"/)[1];
  const context = await browser.newContext({ baseURL, storageState: authFile("admin") });
  await context.route("**/*", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, headers: { ...response.headers(),
      "content-security-policy": csp, "x-frame-options": "DENY" } });
  });
  const page = await context.newPage();
  const violations = [];
  page.on("console", (msg) => { if (/Content Security Policy|Refused to (frame|display)/i.test(msg.text())) violations.push(msg.text()); });
  await page.goto("/invoices");
  await page.getByRole("row", { name: new RegExp(inv.number) }).getByTitle("Preview").click();
  const frame = page.getByTestId("pdf-frame");
  await expect(frame).toBeVisible();
  expect(await frame.getAttribute("src")).toMatch(/^blob:/);
  await page.waitForTimeout(1500);
  expect(violations, violations.join("\n")).toEqual([]);
  await page.getByTestId("pdf-preview-close").click();
  await expect(page.getByTestId("pdf-preview")).toHaveCount(0);
  await context.close();
});
