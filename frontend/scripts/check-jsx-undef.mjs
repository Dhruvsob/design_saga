// CI guard: fails when a JSX tag like <Trash /> is used but never imported or declared
// (ESLint here has no react plugin, so such a typo only crashes at runtime). Usage: node scripts/check-jsx-undef.mjs [dir]
// Find capitalised JSX tags that are never imported or declared in their file.
import fs from "node:fs";
import path from "node:path";

const root = process.argv[2] || "src";
const files = [];
const walk = (d) => {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(jsx|js)$/.test(e.name)) files.push(p);
  }
};
walk(root);

let problems = 0;
for (const f of files) {
  const src = fs.readFileSync(f, "utf8");
  const tags = new Set([...src.matchAll(/<([A-Z][A-Za-z0-9_]*)[\s/>.]/g)].map((m) => m[1]));
  if (!tags.size) continue;
  const declared = new Set();
  // imports: default, named (with "as"), namespace
  for (const m of src.matchAll(/import\s+([^"';]*?)\s+from\s+["'][^"']+["']/g)) {
    const spec = m[1];
    const def = spec.match(/^([A-Za-z_$][\w$]*)/);
    if (def) declared.add(def[1]);
    const ns = spec.match(/\*\s+as\s+([A-Za-z_$][\w$]*)/);
    if (ns) declared.add(ns[1]);
    const named = spec.match(/\{([\s\S]*?)\}/);
    if (named) for (const part of named[1].split(",")) {
      const t = part.trim(); if (!t) continue;
      const as = t.match(/\bas\s+([A-Za-z_$][\w$]*)/);
      declared.add(as ? as[1] : t.split(/\s+/)[0]);
    }
  }
  for (const m of src.matchAll(/\b(?:function|class)\s+([A-Z][\w$]*)/g)) declared.add(m[1]);
  for (const m of src.matchAll(/\b(?:const|let|var)\s+([A-Z][\w$]*)\s*=/g)) declared.add(m[1]);
  // destructured / parameter names like { icon: Icon }, ({ as: Tag }), a.icon -> <a.icon>
  for (const m of src.matchAll(/:\s*([A-Z][\w$]*)\s*[,}=)]/g)) declared.add(m[1]);
  for (const m of src.matchAll(/[({,[]\s*([A-Z][\w$]*)\s*[,})=\]]/g)) declared.add(m[1]);
  for (const m of src.matchAll(/\bconst\s*\{([^}]*)\}\s*=/g)) for (const p of m[1].split(",")) {
    const n = p.split(":").pop().trim().split("=")[0].trim(); if (n) declared.add(n);
  }
  const missing = [...tags].filter((t) => !declared.has(t) && t !== "React" && t !== "Fragment");
  if (missing.length) { problems += missing.length; console.log(`${path.relative(root, f)}: ${missing.join(", ")}`); }
}
console.log(`JSX check: ${problems} undefined component name(s)`);
if (problems) process.exit(1);
