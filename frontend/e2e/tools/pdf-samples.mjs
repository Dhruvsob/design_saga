// Downloads one sample of every generated PDF from the local QA tenant for visual review.
// Run: E2E_BASE_URL=http://127.0.0.1:5174 node e2e/tools/pdf-samples.mjs <outDir>
import fs from "node:fs";
import { request as pwRequest } from "@playwright/test";
import { authFile, baseURL } from "../helpers.mjs";

const out = process.argv[2];
const api = await pwRequest.newContext({ baseURL, storageState: authFile("admin"), extraHTTPHeaders: { Origin: baseURL } });
await api.post("/api/auth/pin/unlock", { data: { pin: process.env.QA_PIN } });
const rows = async (path) => { const r = await api.get(path); if (!r.ok()) return []; const d = await r.json(); return Array.isArray(d) ? d : d.items || d.rows || []; };
const save = async (name, path) => {
  const r = await api.get(path);
  if (!r.ok()) { console.log(`${name}: HTTP ${r.status()} ${path}`); return; }
  fs.writeFileSync(`${out}/${name}.pdf`, await r.body());
  console.log(`${name}: ok ${path}`);
};
const uid = Date.now().toString(36).slice(-5);
// Rich samples so tables, GST and page breaks are exercised.
const client = await (await api.post("/api/clients", { data: { name: `Mehta Residence ${uid}`, phone: "9825012345", email: "mehta@example.com", address: "12 Satellite Road, Ahmedabad" } })).json();
const project = await (await api.post("/api/projects", { data: { name: `Mehta Villa ${uid}`, client_id: client.id, engagement_type: "turnkey", budget: 2500000 } })).json();
const items = Array.from({ length: 28 }, (_, i) => ({ description: `${["Living room false ceiling with cove lighting", "Kitchen modular cabinets – BWP ply with acrylic shutters", "Master bedroom wardrobe, 8 ft, laminate finish", "Electrical points and conduit", "Wall putty and two coats emulsion"][i % 5]} (${i + 1})`, quantity: 1 + (i % 3), rate: 12500 + i * 750 }));
const inv = await (await api.post("/api/invoices", { data: { client_id: client.id, project_id: project.id, doc_type: "invoice", tax_rate: 18, due_date: "2026-11-30", items } })).json();
await api.patch(`/api/invoices/${inv.id}/status`, { data: { status: "sent" } });
await save("invoice-long", `/api/invoices/${inv.id}/pdf`);
const short = await (await api.post("/api/invoices", { data: { client_id: client.id, project_id: project.id, doc_type: "invoice", tax_rate: 18, items: items.slice(0, 2) } })).json();
await save("invoice-short", `/api/invoices/${short.id}/pdf`);
for (const q of await rows("/api/quotations-adv")) {
  const t = q.proposal ? "quotation-consultancy-proposal" : `quotation-${q.type}`;
  if (!fs.existsSync(`${out}/${t}.pdf`)) await save(t, `/api/quotations-adv/${q.id}/pdf`);
}
const turnkey = await (await api.post("/api/quotations-adv", { data: { type: "turnkey", project_title: `Mehta Villa ${uid}`, client_id: client.id, client_name: client.name } })).json();
await save("quotation-turnkey-new", `/api/quotations-adv/${turnkey.id}/pdf`);
const rem = (await rows("/api/accounting/reminders"))[0];
if (rem) await save("payment-reminder", `/api/accounting/reminders/${rem.id}/pdf`);
const runs = await rows("/api/payroll/runs");
const paid = runs.find((r) => r.status === "paid");
if (paid) await save("salary-slip", `/api/payroll/runs/${paid.id}/slip.pdf`);
const vendor = (await rows("/api/vendors"))[0];
if (vendor) await save("vendor-incentive-statement", `/api/vendors/${vendor.id}/commission-statement.pdf`);
await api.dispose();
