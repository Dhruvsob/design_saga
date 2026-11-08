import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle, Circle, X } from "@phosphor-icons/react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";

const listLength = (result) => {
  if (result.status !== "fulfilled") return null;
  const data = result.value?.data;
  return Array.isArray(data) ? data.length : Array.isArray(data?.items) ? data.items.length : null;
};

/**
 * Admin-only setup checklist for a new firm (PROD-01). Each step is derived
 * from real data, links to the screen that completes it and ticks itself off.
 * Hidden once everything is done or when the admin dismisses it.
 */
export default function GettingStarted() {
  const { hasPerm, currentOrg } = useAuth();
  const isAdmin = hasPerm("*.*");
  const storageKey = `ds_setup_dismissed_${currentOrg?.org_id || "org"}`;
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(storageKey) === "1"; } catch { return false; }
  });
  const [counts, setCounts] = useState(null);

  useEffect(() => {
    if (!isAdmin || dismissed) return;
    let alive = true;
    Promise.allSettled([
      api.get("/employees"), api.get("/clients"), api.get("/projects"), api.get("/vendors"),
    ]).then(([employees, clients, projects, vendors]) => {
      if (alive) {
        setCounts({ employees: listLength(employees), clients: listLength(clients),
                    projects: listLength(projects), vendors: listLength(vendors) });
      }
    });
    return () => { alive = false; };
  }, [isAdmin, dismissed]);

  const steps = useMemo(() => {
    const org = currentOrg || {};
    const address = org.address || {};
    const bank = org.bank_details || {};
    const has = (n) => (n === null || n === undefined ? null : n > 0);
    return [
      { key: "logo", label: "Upload your company logo", hint: "Shown on every invoice, quotation and payslip",
        done: Boolean(org.branding?.logo_url), to: "/settings/company" },
      { key: "profile", label: "Add address, phone and GSTIN", hint: "Printed in the letterhead of every PDF",
        done: Boolean(address.line1 && (org.phone || org.email) && org.gstin), to: "/settings/company" },
      { key: "bank", label: "Add bank details for payments", hint: "Clients see these on invoices",
        done: Boolean(bank.account || bank.upi), to: "/settings/company" },
      { key: "employee", label: "Add your first employee", hint: "Needed for attendance, tasks and payroll",
        done: has(counts?.employees), to: "/employees" },
      { key: "client", label: "Add your first client", hint: "Then quote, invoice and track collections",
        done: has(counts?.clients), to: "/clients" },
      { key: "project", label: "Create your first project", hint: "Tasks, files, site work and finances live here",
        done: has(counts?.projects), to: "/projects" },
      { key: "vendor", label: "Add a vendor or contractor", hint: "For purchase orders, bills and vendor incentives",
        done: has(counts?.vendors), to: "/vendors" },
    ];
  }, [currentOrg, counts]);

  if (!isAdmin || dismissed || !counts) return null;
  const doneCount = steps.filter((s) => s.done).length;
  if (doneCount === steps.length) return null;

  const dismiss = () => {
    try { localStorage.setItem(storageKey, "1"); } catch { /* storage unavailable */ }
    setDismissed(true);
  };

  return (
    <section className="card-flat" aria-labelledby="getting-started-title" data-testid="getting-started">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="overline">GETTING STARTED · {doneCount} OF {steps.length} DONE</div>
          <h2 id="getting-started-title" className="font-display font-bold text-xl mt-1">Set up your studio</h2>
        </div>
        <button type="button" className="btn-icon" onClick={dismiss} aria-label="Hide setup checklist"
                data-testid="getting-started-dismiss">
          <X size={16} />
        </button>
      </div>
      <div className="mt-3 h-1.5 rounded-full bg-[var(--line-soft)] overflow-hidden" aria-hidden="true">
        <div className="h-full bg-[var(--accent-strong)]" style={{ width: `${Math.round((doneCount / steps.length) * 100)}%` }} />
      </div>
      <ul className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-2">
        {steps.map((step) => (
          <li key={step.key}>
            <Link to={step.to} data-testid={`setup-step-${step.key}`}
                  className={`flex items-start gap-3 p-3 rounded-lg border transition ${step.done
                    ? "border-[var(--line)] bg-[var(--surface-2)]" : "border-[var(--line)] bg-white hover:border-[var(--accent-strong)]"}`}>
              {step.done
                ? <CheckCircle size={18} weight="fill" className="text-[var(--success)] shrink-0 mt-0.5" aria-hidden="true" />
                : <Circle size={18} className="text-[var(--ink-3)] shrink-0 mt-0.5" aria-hidden="true" />}
              <span className="min-w-0">
                <span className={`block text-sm font-semibold ${step.done ? "text-[var(--ink-3)] line-through" : "text-[var(--ink)]"}`}>
                  {step.label}
                  {step.done && <span className="sr-only"> (done)</span>}
                </span>
                <span className="block text-xs text-[var(--ink-3)]">{step.hint}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
