// Creates an isolated QA tenant with an Admin and an Employee through the real
// API, completes the mandatory App PIN setup, and stores each session.
// Refuses to run unless the target is a local origin.
import { request } from "@playwright/test";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";
export const AUTH_DIR = new URL("./.auth/", import.meta.url);

function qaPin() {
  const pin = process.env.QA_PIN || "";
  if (!/^\d{6}$/.test(pin)) throw new Error("QA_PIN must be a 6-digit, non-trivial PIN");
  return pin;
}

export async function session(identifier, password) {
  const ctx = await request.newContext({ baseURL, extraHTTPHeaders: { Origin: baseURL } });
  const res = await ctx.post("/api/auth/login-password", { data: { identifier, password } });
  if (!res.ok()) throw new Error(`login failed for ${identifier}: ${res.status()}`);
  return ctx;
}

export async function ensurePin(ctx) {
  const status = await (await ctx.get("/api/auth/pin/status")).json();
  let res = null;
  if (status.setup_required) {
    res = await ctx.post("/api/auth/pin/setup", { data: { pin: qaPin() } });
  } else if (status.locked) {
    res = await ctx.post("/api/auth/pin/unlock", { data: { pin: qaPin() } });
  }
  if (res && !res.ok()) throw new Error(`PIN step failed: ${res.status()} ${await res.text()}`);
}

export default async function globalSetup() {
  const host = new URL(baseURL).hostname;
  if (!["127.0.0.1", "localhost"].includes(host)) {
    throw new Error("E2E setup refuses non-local targets");
  }
  const owner = process.env.QA_SUPERADMIN_EMAIL;
  const password = process.env.QA_PASSWORD;
  if (!owner || !password) throw new Error("QA_SUPERADMIN_EMAIL and QA_PASSWORD are required");
  fs.mkdirSync(AUTH_DIR, { recursive: true });

  const stamp = Date.now().toString(36);
  const adminEmail = `admin-${stamp}@qa.example.com`;
  const employeeEmail = `employee-${stamp}@qa.example.com`;

  const sa = await session(owner, password);
  await ensurePin(sa);
  const org = await sa.post("/api/platform/orgs", { data: {
    name: `QA Studio ${stamp}`, admin_email: adminEmail, admin_name: "QA Admin",
    admin_password: password, business_mode: "hybrid",
  } });
  if (!org.ok()) throw new Error(`tenant creation failed: ${org.status()} ${await org.text()}`);
  await sa.dispose();

  const admin = await session(adminEmail, password);
  await ensurePin(admin);
  const reg = await admin.post("/api/auth/register", { data: {
    email: employeeEmail, password, name: "QA Employee", role: "Employee",
    approve_immediately: true,
  } });
  if (!reg.ok()) throw new Error(`employee creation failed: ${reg.status()} ${await reg.text()}`);
  await admin.storageState({ path: fileURLToPath(new URL("admin.json", AUTH_DIR)) });
  await admin.dispose();

  const employee = await session(employeeEmail, password);
  await ensurePin(employee);
  await employee.storageState({ path: fileURLToPath(new URL("employee.json", AUTH_DIR)) });
  await employee.dispose();

  // The App PIN locks a session after 5 minutes without activity (server-side). Every test
  // shares these two sessions, and pages that only navigate send no activity, so a long run
  // would meet the lock screen at a random point. Keep both sessions active for the run,
  // as a person working would; the lock itself is covered by the backend tests.
  const keep = [];
  for (const role of ["admin", "employee"]) {
    keep.push(await request.newContext({ baseURL, extraHTTPHeaders: { Origin: baseURL },
      storageState: fileURLToPath(new URL(`${role}.json`, AUTH_DIR)) }));
  }
  const renew = async () => {
    for (const ctx of keep) {
      try {
        const res = await ctx.post("/api/auth/pin/touch");
        if (res.status() === 423) await ctx.post("/api/auth/pin/unlock", { data: { pin: qaPin() } });
      } catch { /* server restarting; next tick retries */ }
    }
  };
  const timer = setInterval(renew, 60_000);
  return async () => {
    clearInterval(timer);
    await Promise.all(keep.map((ctx) => ctx.dispose()));
  };
}
