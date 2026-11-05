import { test } from "node:test";
import assert from "node:assert/strict";
import { visibleNavGroups } from "./navigation.js";
import { roundPaise } from "./format.js";

const groups = [
  { id: "home", label: null, items: [{ to: "/dashboard", perm: "dashboard.read" }] },
  { id: "sales", label: "Sales", items: [
    { to: "/crm", perm: "leads.read", module: "crm" },
    { to: "/clients", perm: "clients.read", module: "clients" },
  ] },
  { id: "admin", label: "Administration", items: [{ to: "/settings/audit", perm: "*.*" }] },
];

test("hides items without permission and drops empty groups", () => {
  const perms = new Set(["dashboard.read", "clients.read"]);
  const out = visibleNavGroups(groups, (p) => perms.has(p));
  assert.deepEqual(out.map((g) => g.id), ["home", "sales"]);
  assert.deepEqual(out[1].items.map((i) => i.to), ["/clients"]);
});

test("respects disabled tenant modules even with permission", () => {
  const out = visibleNavGroups(groups, () => true, { crm: false, clients: false });
  assert.deepEqual(out.map((g) => g.id), ["home", "admin"]);
});

test("admin links follow permission, not role name", () => {
  const out = visibleNavGroups(groups, (p) => p === "*.*");
  assert.deepEqual(out.map((g) => g.id), ["admin"]);
});

test("roundPaise matches backend half-up policy", () => {
  assert.equal(roundPaise(2.675), 2.68);
  assert.equal(roundPaise(1.005), 1.01);
  assert.equal(roundPaise(0.1 + 0.2), 0.3);
  assert.equal(roundPaise(3 * 33.335), 100.01);
  assert.equal(roundPaise("bad"), 0);
});
