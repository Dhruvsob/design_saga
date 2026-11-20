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

// ---------------------------------------------------------------- stale bundles after a deploy
import { isChunkError, reloadForNewVersion, withChunkReload } from "./chunks.js";

function fakeWindow({ storageThrows = false } = {}) {
  const store = new Map();
  const win = {
    reloads: 0,
    location: { reload: () => { win.reloads += 1; } },
    sessionStorage: {
      getItem: (k) => { if (storageThrows) throw new Error("blocked"); return store.get(k) ?? null; },
      setItem: (k, v) => { if (storageThrows) throw new Error("blocked"); store.set(k, v); },
    },
  };
  globalThis.window = win;
  return win;
}

test("recognises the browsers' stale-bundle errors and nothing else", () => {
  assert.ok(isChunkError(new TypeError("Failed to fetch dynamically imported module: https://gamaa.in/assets/Library-6iu.js")));
  assert.ok(isChunkError(new TypeError("Importing a module script failed.")));
  assert.ok(isChunkError(new TypeError("error loading dynamically imported module")));
  assert.ok(!isChunkError(new TypeError("Cannot read properties of undefined (reading 'map')")));
  assert.ok(!isChunkError(null));
});

test("reloads once for a stale bundle, then lets the error through instead of looping", async () => {
  const win = fakeWindow();
  const stale = () => Promise.reject(new TypeError("Failed to fetch dynamically imported module: x.js"));
  const pending = withChunkReload(stale)();
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(win.reloads, 1);                                   // first failure: reload, keep loading
  assert.equal(await Promise.race([pending, Promise.resolve("still loading")]), "still loading");
  await assert.rejects(withChunkReload(stale)(), /dynamically imported/);   // again within a minute: show it
  assert.equal(win.reloads, 1);
});

test("never reloads when it cannot remember having reloaded, and rethrows real page errors", async () => {
  const win = fakeWindow({ storageThrows: true });
  assert.equal(reloadForNewVersion(), false);
  assert.equal(win.reloads, 0);
  fakeWindow();
  await assert.rejects(withChunkReload(() => Promise.reject(new Error("render bug")))(), /render bug/);
});

// ---------------------------------------------------------------- 422 lists become text once
import { normalizeErrorDetail } from "./errors.js";

test("a FastAPI validation list becomes readable text a toast can render", () => {
  const list = [{ type: "string_too_long", loc: ["body", "client_name"], msg: "String should have at most 160 characters" }];
  const err = normalizeErrorDetail({ response: { status: 422, data: { detail: list } } });
  assert.equal(err.response.data.detail, "Client name: String should have at most 160 characters");
  assert.deepEqual(err.response.data.errors, list);
});

test("string and structured details are left alone", () => {
  const structured = { code: "visit_open", message: "Finish the open visit first" };
  assert.equal(normalizeErrorDetail({ response: { data: { detail: "Leave dates overlap" } } }).response.data.detail, "Leave dates overlap");
  assert.equal(normalizeErrorDetail({ response: { data: { detail: structured } } }).response.data.detail, structured);
  assert.doesNotThrow(() => normalizeErrorDetail({ message: "Network Error" }));
  assert.doesNotThrow(() => normalizeErrorDetail({ response: { data: "<html>502</html>" } }));
});

test("errorItems keeps each validation problem with its field for the error summary", async () => {
  const { errorItems, normalizeErrorDetail } = await import("./errors.js");
  const err = { response: { status: 422, data: { detail: [
    { loc: ["body", "first_name"], msg: "Field required" },
    { loc: ["body", "email"], msg: "Value error, value is not a valid email address" },
  ] } } };
  normalizeErrorDetail(err);   // what the API layer does first
  assert.deepEqual(errorItems(err), [
    { field: "first_name", text: "Field required" },
    { field: "email", text: "value is not a valid email address" },
  ]);
  assert.deepEqual(errorItems({ response: { data: { detail: "Email already in use" } } }),
    [{ field: null, text: "Email already in use" }]);
  assert.deepEqual(errorItems({ code: "ERR_NETWORK" }, "x"),
    [{ field: null, text: "No connection to the server. Check your internet and try again." }]);
});
