import { request } from "@playwright/test";
import { fileURLToPath } from "node:url";

export const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";
export const authFile = (role) => fileURLToPath(new URL(`./.auth/${role}.json`, import.meta.url));

/** API context for a stored role session; unlocks the App PIN if it timed out. */
export async function api(role) {
  const ctx = await request.newContext({
    baseURL, storageState: authFile(role), extraHTTPHeaders: { Origin: baseURL },
  });
  const status = await (await ctx.get("/api/auth/pin/status")).json();
  if (status.locked) {
    const res = await ctx.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN } });
    if (!res.ok()) throw new Error(`PIN unlock failed: ${res.status()}`);
  }
  return ctx;
}

export async function json(resPromise, expectedStatus = 200) {
  const res = await resPromise;
  const body = await res.json().catch(() => ({}));
  if (res.status() !== expectedStatus) {
    throw new Error(`expected HTTP ${expectedStatus}, got ${res.status()}: ${JSON.stringify(body).slice(0, 300)}`);
  }
  return body;
}

export async function accounts(ctx) {
  const rows = await json(ctx.get("/api/accounts"));
  const byName = (n) => rows.find((a) => a.name === n);
  return { rows, cash: byName("Cash"), bank: byName("Bank - Primary"), byName };
}

export async function journals(ctx, query) {
  const params = new URLSearchParams({ limit: "500", ...query });
  const body = await json(ctx.get(`/api/journal-entries?${params}`));
  return Array.isArray(body) ? body : body.items;
}

export const balanced = (je) => {
  const sum = (k) => Math.round(je.lines.reduce((s, l) => s + Number(l[k] || 0), 0) * 100);
  return sum("debit") === sum("credit");
};

export const listOf = (body, ...keys) =>
  Array.isArray(body) ? body : keys.map((k) => body[k]).find(Array.isArray) || [];

export const today = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
export const uid = () => Math.random().toString(36).slice(2, 8);
