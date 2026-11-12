import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { DownloadSimple, FileArrowUp, Warning, X } from "@phosphor-icons/react";
import api from "../lib/api";

/** Minimal RFC 4180 reader: quoted fields, doubled quotes, CR/LF, Excel's BOM. */
export function parseCsv(text) {
  const src = String(text || "").replace(/^﻿/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < src.length; i += 1) {
    const c = src[i];
    if (quoted) {
      if (c === '"' && src[i + 1] === '"') { field += '"'; i += 1; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"' && field === "") quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && src[i + 1] === "\n") i += 1;
      row.push(field); field = "";
      if (row.some((v) => v.trim() !== "")) rows.push(row);
      row = [];
    } else field += c;
  }
  row.push(field);
  if (row.some((v) => v.trim() !== "")) rows.push(row);
  return rows;
}

// Accepted column titles (case and spacing ignored) → API field.
const ALIASES = {
  first_name: ["first name", "firstname", "first_name", "given name"],
  last_name: ["last name", "lastname", "last_name", "surname"],
  full_name: ["name", "full name", "employee name"],
  email: ["email", "email address", "e-mail"],
  phone: ["phone", "mobile", "phone number", "mobile number", "contact"],
  department: ["department", "dept"],
  designation: ["designation", "title", "job title", "role"],
  joining_date: ["joining date", "date of joining", "doj", "joining_date", "start date"],
  employment_type: ["employment type", "type", "employment_type"],
  monthly_salary: ["monthly salary", "salary", "monthly_salary", "ctc per month"],
};
const TEMPLATE = [
  ["First name", "Last name", "Email", "Phone", "Department", "Designation", "Joining date", "Employment type", "Monthly salary"],
  ["Asha", "Mehta", "asha@studio.in", "+91 98765 43210", "Design", "Interior Designer", "01/04/2026", "full_time", "45000"],
];

function mapRows(table) {
  const [header, ...body] = table;
  const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
  const index = {};
  header.forEach((h, i) => {
    const key = Object.keys(ALIASES).find((k) => ALIASES[k].includes(norm(h)));
    if (key && index[key] === undefined) index[key] = i;
  });
  const missing = index.first_name === undefined && index.full_name === undefined;
  const rows = body.map((cells) => {
    const get = (k) => (index[k] === undefined ? "" : String(cells[index[k]] ?? "").trim());
    let first = get("first_name");
    let last = get("last_name");
    if (!first && get("full_name")) {
      const parts = get("full_name").split(/\s+/);
      first = parts.shift() || "";
      last = last || parts.join(" ");
    }
    return {
      first_name: first, last_name: last, email: get("email"), phone: get("phone"),
      department: get("department"), designation: get("designation"),
      joining_date: get("joining_date"), employment_type: get("employment_type"),
      monthly_salary: get("monthly_salary"),
    };
  });
  return { rows, missing, columns: Object.keys(index) };
}

function downloadTemplate() {
  const text = TEMPLATE.map((r) => r.map((v) => `"${v}"`).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([`﻿${text}`], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "employees-template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

/** Import many employees at once: choose a CSV, review every row, then save. */
export default function EmployeeImport({ onClose, onDone }) {
  const fileRef = useRef(null);
  const [rows, setRows] = useState(null);
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const detail = (ex, fallback) => {
    const d = ex?.response?.data?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => x?.msg || String(x)).join(" · ");
    return fallback;
  };

  const pick = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setErr(""); setCheck(null); setRows(null);
    if (file.size > 2 * 1024 * 1024) { setErr("The file is larger than 2 MB."); return; }
    const table = parseCsv(await file.text());
    if (table.length < 2) { setErr("The file has no rows under the header."); return; }
    const mapped = mapRows(table);
    if (mapped.missing) { setErr("Add a \"First name\" (or \"Name\") column. Download the template to see the layout."); return; }
    if (mapped.rows.length > 500) { setErr("Import up to 500 employees at a time."); return; }
    setRows(mapped.rows);
    setBusy(true);
    try {
      const { data } = await api.post("/employees/import", { rows: mapped.rows, dry_run: true });
      setCheck(data);
    } catch (ex) {
      setErr(detail(ex, "Could not check the file"));
    } finally { setBusy(false); }
  };

  const commit = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/employees/import", { rows, dry_run: false });
      if (data.created) {
        toast.success(`${data.created} employee${data.created === 1 ? "" : "s"} added`);
        onDone();
      } else {
        setCheck(data);
      }
    } catch (ex) {
      setErr(detail(ex, "Import failed"));
    } finally { setBusy(false); }
  };

  const bad = (check?.rows || []).filter((r) => r.errors.length);
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => !busy && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="emp-import-title" onClick={(e) => e.stopPropagation()}
           className="bg-[var(--surface)] w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-[var(--line)] rounded-xl p-6 space-y-4"
           data-testid="employee-import">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="overline">HR / BULK ADD</div>
            <h2 id="emp-import-title" className="font-display font-bold tracking-tight text-2xl">Import employees</h2>
          </div>
          <button type="button" onClick={onClose} disabled={busy} className="btn-ghost text-xs" aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <p className="text-sm text-[var(--ink-2)]">
          Upload a CSV (Excel: Save As → CSV) with one employee per row. Each gets the next employee
          number; ERP logins are created later from the employee&apos;s page. Nothing is saved until every
          row is correct.
        </p>
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={pick}
                 aria-label="CSV file" data-testid="employee-import-file" />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={busy} className="btn-primary text-xs">
            <FileArrowUp size={13} /> {rows ? "Choose another file" : "Choose CSV file"}
          </button>
          <button type="button" onClick={downloadTemplate} className="btn-ghost text-xs">
            <DownloadSimple size={13} /> Template
          </button>
        </div>
        {err && (
          <div role="alert" className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 flex items-center gap-2">
            <Warning size={13} /> {err}
          </div>
        )}
        {busy && !check && <div className="overline live-dot">CHECKING ROWS</div>}
        {check && (
          <div className="space-y-3" data-testid="employee-import-check">
            <div className="text-sm">
              <b>{check.valid}</b> ready{check.invalid ? <> · <b className="text-[var(--danger)]">{check.invalid}</b> need fixing</> : null}
            </div>
            {bad.length > 0 && (
              <div className="border border-[var(--line)] rounded-md divide-y divide-[var(--line-soft)] max-h-64 overflow-y-auto">
                {bad.map((r) => (
                  <div key={r.row} className="px-3 py-2 text-xs">
                    <div className="font-semibold">Row {r.row + 1}{r.name ? ` · ${r.name}` : ""}</div>
                    <ul className="list-disc pl-4 text-[var(--danger)]">
                      {r.errors.map((m) => <li key={m}>{m}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            )}
            {bad.length > 0 ? (
              <p className="text-xs text-[var(--ink-3)]">Fix these rows in the file and choose it again. Row numbers count the header as row 1.</p>
            ) : (
              <div className="flex justify-end gap-2">
                <button type="button" onClick={onClose} disabled={busy} className="btn-ghost">Cancel</button>
                <button type="button" onClick={commit} disabled={busy} className="btn-primary" data-testid="employee-import-commit">
                  {busy ? "Adding…" : `Add ${check.valid} employee${check.valid === 1 ? "" : "s"}`}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
