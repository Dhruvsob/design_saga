import { useState } from "react";
import api from "../lib/api";
import { formatDate, formatINR } from "../lib/format";

const CHECKS = [
  ["method_account_mismatches", "Payments booked to the wrong Cash/Bank account",
   "The recorded method (e.g. Bank transfer) does not match the ledger that moved (e.g. Cash)."],
  ["unbalanced_journals", "Unbalanced entries", "Debits and credits differ."],
  ["orphaned_source_journals", "Entries whose source record is missing",
   "The invoice, bill, payment or salary behind the entry no longer exists."],
  ["broken_reversal_links", "Broken reversal links", "A reversed entry points to a reversal that is missing."],
  ["paid_sources_without_active_journal", "Paid records without an accounting entry",
   "A salary or vendor payment is marked paid but has no active journal."],
];

const KIND_LABELS = {
  payroll_run: "Salary", vendor_payment: "Vendor payment", commission_receipt: "Vendor incentive receipt",
  collection_receipt: "Collection receipt", money_in: "Money In", money_out: "Money Out",
};

const METHOD_LABELS = {
  cash: "Cash", bank_transfer: "Bank transfer", upi: "UPI", cheque: "Cheque",
  credit_card: "Credit card", online: "Online", other: "Other",
};

/** Read-only accounting data check (admin). Never changes records. */
export function DataChecks() {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true); setError("");
    try {
      const { data } = await api.get("/accounting/integrity/source-links");
      setReport(data);
    } catch (e) {
      setError(e?.response?.status === 403 ? "Only administrators can run data checks."
        : (e?.response?.data?.detail || "The data check could not be completed. Try again."));
    } finally { setBusy(false); }
  };

  const rows = report?.method_account_mismatches?.rows || [];
  return (
    <div className="card-flat mb-6" data-testid="data-checks">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="overline">DATA CHECKS</div>
          <h3 className="font-display font-bold text-xl">Find accounting records that need correction</h3>
          <p className="text-xs text-[var(--ink-2)] mt-1 max-w-2xl">
            Read-only. Nothing is changed. Correct each finding from its own screen using
            reverse-and-record-again, so the history and audit trail stay intact.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={run} disabled={busy} data-testid="run-data-check">
          {busy ? "Checking…" : report ? "Run again" : "Run data check"}
        </button>
      </div>

      {error && <div className="mt-3 text-sm text-[var(--danger)]" role="alert">{error}</div>}

      {report && (
        <>
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
            {CHECKS.map(([key, label, hint]) => {
              const count = report.counts?.[key] || 0;
              return (
                <div key={key} title={hint}
                     className={`p-3 rounded-lg border ${count ? "border-[#E8C9A0] bg-[var(--warning-soft)]" : "border-[var(--line)] bg-white"}`}
                     data-testid={`check-${key}`}>
                  <div className="text-2xl font-display font-bold">{count}</div>
                  <div className="text-xs text-[var(--ink-2)]">{label}</div>
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-xs text-[var(--ink-2)]">
            {report.ok ? "No problems found." : "Hover a box for what it means."} Checked {report.journals_scanned} accounting entries.
          </div>

          {rows.length > 0 && (
            <div className="mt-5">
              <div className="overline mb-2">PAYMENTS BOOKED TO THE WRONG CASH/BANK ACCOUNT · {report.method_account_mismatches.count}</div>
              <div className="overflow-x-auto border border-[var(--line)] rounded-lg">
                <table className="w-full text-sm" data-testid="mismatch-table">
                  <thead className="bg-[var(--hover)] text-left text-xs text-[var(--ink-2)]">
                    <tr>
                      <th scope="col" className="p-2">Date</th><th scope="col" className="p-2">Type</th>
                      <th scope="col" className="p-2">For</th><th scope="col" className="p-2 text-right">Amount</th>
                      <th scope="col" className="p-2">Recorded as</th><th scope="col" className="p-2">Account used</th>
                      <th scope="col" className="p-2">How to correct</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={`${r.kind}-${r.id}`} className="border-t border-[var(--line-soft)] align-top">
                        <td className="p-2 whitespace-nowrap">{formatDate(r.date)}</td>
                        <td className="p-2 whitespace-nowrap">
                          {KIND_LABELS[r.kind] || r.kind}
                          {r.confidence === "inferred" && (
                            <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-[var(--info-soft)] text-[#4B5BA6]"
                                  title="Method read from the entry description">inferred</span>
                          )}
                        </td>
                        <td className="p-2">{r.party || "—"}</td>
                        <td className="p-2 text-right font-mono whitespace-nowrap">{formatINR(r.amount)}</td>
                        <td className="p-2">{METHOD_LABELS[r.method] || String(r.method || "").replace(/_/g, " ")}</td>
                        <td className="p-2">{r.account_name || "—"}</td>
                        <td className="p-2 text-xs text-[var(--ink-2)] min-w-[240px]">{r.fix}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {report.method_account_mismatches.truncated && (
                <div className="text-xs text-[var(--ink-2)] mt-2">Showing the latest 500 findings. Correct these and run again to see the rest.</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
