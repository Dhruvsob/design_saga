// Expense receipts: staff attach a photo or PDF to a claim line (phone camera
// on mobile) instead of pasting a link. The receipt counts for the policy's
// "receipt above ₹X" rule; the claimant, approvers and finance can open it,
// other staff and signed-out visitors cannot.
import { test, expect, request } from "@playwright/test";
import fs from "node:fs";
import { api, json, uid, authFile, baseURL } from "./helpers.mjs";
import { session, ensurePin } from "./global-setup.mjs";

const PNG = fs.readFileSync(new URL("./fixtures/qa-test-logo.png", import.meta.url));
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

test.beforeEach(async ({ browserName }, testInfo) => {
  void browserName;
  test.skip(testInfo.project.name === "laptop", "desktop + mobile cover both layouts");
});

async function openNewClaim(page, title) {
  const policy = page.waitForResponse((r) => r.url().includes("/api/expense-policy") && r.ok());
  await page.goto("/expenses");
  await page.getByTestId("new-expense-btn").click();
  await policy;
  await page.getByTestId("exp-title").fill(title);
}

/** A second, unrelated employee in the same company. */
async function otherEmployee() {
  const admin = await api("admin");
  const email = `other-${uid()}@qa.example.com`;
  await json(admin.post("/api/auth/register", { data: {
    email, password: process.env.QA_PASSWORD, name: "Other Employee", role: "Employee",
    approve_immediately: true,
  } }));
  await admin.dispose();
  const ctx = await session(email, process.env.QA_PASSWORD);
  await ensurePin(ctx);
  return ctx;
}

test.describe("employee", () => {
  test.use({ storageState: authFile("employee") });

  test("attaches a receipt photo and the claim goes for approval, not 'receipt required'", async ({ page }, testInfo) => {
    const mobile = testInfo.project.name === "mobile";
    const title = `Auto to site ${uid()}`;
    await openNewClaim(page, title);
    const line = page.getByTestId("exp-line-0");
    await line.getByLabel("Amount").fill("2400");
    await line.getByLabel("What it was for").fill("Auto fare, Andheri site");
    await expect(page.getByTestId("exp-receipt-warning"), "above ₹1,000 without a receipt warns").toBeVisible();

    // Phones get a camera button that opens the rear camera; desktops just attach a file.
    if (mobile) {
      await expect(page.getByTestId("exp-line-0-photo")).toBeVisible();
      await expect(page.getByTestId("exp-line-0-photo-input")).toHaveAttribute("capture", "environment");
    } else {
      await expect(page.getByTestId("exp-line-0-photo")).toHaveCount(0);
    }
    const input = page.getByTestId(mobile ? "exp-line-0-photo-input" : "exp-line-0-file-input");
    const uploaded = page.waitForResponse((r) => r.url().endsWith("/api/expenses/receipts") && r.request().method() === "POST");
    await input.setInputFiles({ name: "bill.png", mimeType: "image/png", buffer: PNG });
    expect((await uploaded).status()).toBe(200);

    const chip = page.getByTestId("exp-line-0-receipt");
    await expect(chip).toContainText("bill.png");
    await expect.poll(() => chip.locator("img").evaluate((img) => img.complete && img.naturalWidth > 0),
      { message: "the uploader can preview their own receipt" }).toBe(true);
    await expect(page.getByTestId("exp-receipt-warning")).toHaveCount(0);

    const saved = page.waitForResponse((r) => r.url().endsWith("/api/expenses") && r.request().method() === "POST");
    await page.getByTestId("exp-submit").click();
    const claim = await (await saved).json();
    expect(claim.status, "a receipt satisfies the policy").toBe("pending_l1");
    expect(claim.has_receipt).toBe(true);
    const receipt = claim.lines[0].receipt_file;
    expect(receipt.id).toMatch(/^rcpt_[a-f0-9]{12}$/);
    expect(receipt.content_type).toBe("image/png");
    expect(claim.lines[0].receipt_url).toBeNull();

    // Who can open the stored file.
    const mine = await api("employee");
    const own = await mine.get(receipt.url);
    expect(own.status()).toBe(200);
    expect(own.headers()["content-type"]).toBe("image/png");
    expect(own.headers()["cache-control"]).toBe("private, no-store");
    expect(Buffer.compare(await own.body(), PNG)).toBe(0);
    const admin = await api("admin");
    expect((await admin.get(receipt.url)).status(), "approver/finance can open it").toBe(200);
    const other = await otherEmployee();
    expect((await other.get(receipt.url)).status(), "another employee cannot").toBe(404);
    // Inside a test, new request contexts inherit the test's storageState; clear it explicitly.
    const anonymous = await request.newContext({
      baseURL, extraHTTPHeaders: { Origin: baseURL }, storageState: { cookies: [], origins: [] },
    });
    expect((await anonymous.get(receipt.url)).status(), "signed out cannot").toBe(401);
    // The same receipt cannot be claimed twice.
    const again = await mine.post("/api/expenses", { data: {
      title: `${title} again`, lines: [{ category: "travel", amount: 2400, receipt_file_id: receipt.id }],
    } });
    expect(again.status()).toBe(409);
    await Promise.all([mine.dispose(), admin.dispose(), other.dispose(), anonymous.dispose()]);
  });

  test("refuses non-receipt files and discards a receipt removed before saving", async ({ page }) => {
    await openNewClaim(page, `Stationery ${uid()}`);
    const fileInput = page.getByTestId("exp-line-0-file-input");
    await fileInput.setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
    await expect(page.getByTestId("exp-line-0-receipt-error")).toContainText("photo (JPG, PNG or WebP) or a PDF");
    await expect(page.getByTestId("exp-line-0-receipt")).toHaveCount(0);

    // The server checks too, by extension and by content.
    const ctx = await api("employee");
    for (const upload of [
      { name: "x.jpg", mimeType: "image/jpeg", buffer: Buffer.from("<script>alert(1)</script>") },
      { name: "bill.docx", mimeType: "application/octet-stream", buffer: Buffer.from("PK\x03\x04") },
    ]) {
      const res = await ctx.post("/api/expenses/receipts", { multipart: { upload } });
      expect(res.status(), `${upload.name} is refused`).toBe(422);
    }

    const uploaded = page.waitForResponse((r) => r.url().endsWith("/api/expenses/receipts") && r.request().method() === "POST");
    await fileInput.setInputFiles({ name: "bill.pdf", mimeType: "application/pdf", buffer: PDF });
    const receipt = await (await uploaded).json();
    await expect(page.getByTestId("exp-line-0-receipt")).toContainText("bill.pdf");
    expect((await ctx.get(receipt.url)).status()).toBe(200);

    const deleted = page.waitForResponse((r) => r.request().method() === "DELETE" && r.url().includes(receipt.id));
    await page.getByRole("button", { name: "Remove receipt from line 1" }).click();
    expect((await deleted).status()).toBe(200);
    await expect(page.getByTestId("exp-line-0-attach")).toBeVisible();
    expect((await ctx.get(receipt.url)).status(), "removed receipt is gone").toBe(404);
    await ctx.dispose();
  });

  test("a large phone photo is shrunk to a JPEG before upload", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "browser-side resize runs the same everywhere");
    await openNewClaim(page, `Big photo ${uid()}`);
    const uploaded = page.waitForResponse((r) => r.url().endsWith("/api/expenses/receipts") && r.request().method() === "POST");
    // A noisy 2600×1800 PNG is ~18 MB: over the 15 MB server limit unless resized first.
    const originalSize = await page.getByTestId("exp-line-0-file-input").evaluate(async (input) => {
      const canvas = document.createElement("canvas");
      canvas.width = 2600; canvas.height = 1800;
      const ctx = canvas.getContext("2d");
      const pixels = ctx.createImageData(canvas.width, canvas.height);
      for (let i = 0; i < pixels.data.length; i += 1) pixels.data[i] = (i % 4 === 3) ? 255 : Math.random() * 255;
      ctx.putImageData(pixels, 0, 0);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], "IMG_1234.png", { type: "image/png" }));
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return blob.size;
    });
    const response = await uploaded;
    expect(response.status()).toBe(200);
    const receipt = await response.json();
    expect(originalSize).toBeGreaterThan(15 * 1024 * 1024);
    expect(receipt.content_type).toBe("image/jpeg");
    expect(receipt.original_name).toBe("IMG_1234.jpg");
    expect(receipt.size).toBeLessThan(originalSize / 2);
    await expect(page.getByTestId("exp-line-0-receipt")).toContainText("IMG_1234.jpg");
  });

  test("a pasted link still works as a receipt", async ({ page }) => {
    await openNewClaim(page, `Site material ${uid()}`);
    const line = page.getByTestId("exp-line-0");
    await line.getByLabel("Amount").fill("1800");
    await page.getByRole("button", { name: "Paste a receipt link for line 1" }).click();
    await line.getByLabel("Receipt link").fill("https://drive.example.com/bill-123");
    const saved = page.waitForResponse((r) => r.url().endsWith("/api/expenses") && r.request().method() === "POST");
    await page.getByTestId("exp-submit").click();
    const claim = await (await saved).json();
    expect(claim.has_receipt).toBe(true);
    expect(claim.status).toBe("pending_l1");
    expect(claim.lines[0].receipt_url).toBe("https://drive.example.com/bill-123");
  });
});

test.describe("approver", () => {
  test.use({ storageState: authFile("admin") });

  test("opens the claimant's receipt from the claim", async ({ page }) => {
    const employee = await api("employee");
    const upload = await json(employee.post("/api/expenses/receipts", {
      multipart: { upload: { name: "hardware.png", mimeType: "image/png", buffer: PNG } },
    }));
    const title = `Hardware ${uid()}`;
    const claim = await json(employee.post("/api/expenses", { data: {
      title, lines: [{ category: "materials", amount: 6500, description: "Hinges", receipt_file_id: upload.id }],
    } }));
    await employee.dispose();

    await page.goto("/expenses");
    await page.getByText(title).click();
    const chip = page.getByTestId(`exp-receipt-${claim.lines[0].id}`);
    await expect(chip).toContainText("hardware.png");
    await expect.poll(() => chip.locator("img").evaluate((img) => img.complete && img.naturalWidth > 0),
      { message: "thumbnail loads for the approver" }).toBe(true);
    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      chip.getByRole("link", { name: "hardware.png", exact: true }).click(),
    ]);
    await popup.waitForLoadState();
    expect(popup.url()).toContain(`/api/expenses/receipts/${upload.id}/content`);
    expect(await popup.evaluate(async (u) => (await fetch(u)).status, popup.url())).toBe(200);
    await popup.close();
  });
});
