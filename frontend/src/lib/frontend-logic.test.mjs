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

import { createElement as h, Fragment } from "react";
import { readOptions } from "./selectOptions.js";

test("SearchSelect reads native <option>/<optgroup> children unchanged", () => {
  const children = [
    h("option", { key: "e", value: "" }, "Select client"),
    [1, 2].map((n) => h("option", { key: n, value: `c${n}` }, "Client ", n)),
    false && h("option", { value: "hidden" }, "never"),
    h(Fragment, { key: "f" }, h("optgroup", { label: "Bank" }, h("option", { value: "b1", disabled: true }, "HDFC"))),
  ];
  assert.deepEqual(readOptions(children), [
    { value: "", label: "Select client", disabled: false, group: "" },
    { value: "c1", label: "Client 1", disabled: false, group: "" },
    { value: "c2", label: "Client 2", disabled: false, group: "" },
    { value: "b1", label: "HDFC", disabled: true, group: "Bank" },
  ]);
});
