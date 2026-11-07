import { useState } from "react";
import { createPortal } from "react-dom";
import { NavLink } from "react-router-dom";
import { toast } from "sonner";
import { FilePdf, WhatsappLogo, X } from "@phosphor-icons/react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { askForm } from "../lib/confirm";
import { formatDate, formatINR } from "../lib/format";
import PdfPreviewModal from "./PdfPreview";

export const inr = (n) => formatINR(n);

/**
 * Invoices | Payment Reminders | Collections Due | Received Payments.
 * Documents (invoices, reminders) never move money; only Record Payment in
 * Collections Due does, and Received Payments lists what it posted.
 */
export function MoneyInTabs() {
  const { hasPerm } = useAuth();
  const finance = hasPerm("finance.read");
  const tabs = [
    { to: "/invoices", label: "Invoices", end: true },
    finance && { to: "/invoices/reminders", label: "Payment Reminders" },
    finance && { to: "/accounting?tab=receivables", label: "Collections Due" },
    finance && { to: "/invoices/received", label: "Received Payments" },
  ].filter(Boolean);
  return (
    <nav className="flex flex-wrap gap-1 border-b border-[var(--line)]" aria-label="Money in" data-testid="money-in-tabs">
      {tabs.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end}
          className={({ isActive }) => {
            const active = isActive && (t.to.includes("?") ? window.location.search.includes("tab=receivables") : true);
            return `px-3 py-2 text-sm -mb-px border-b-2 transition-colors ${active
              ? "border-[var(--accent-strong)] text-[var(--ink)] font-semibold"
              : "border-transparent text-[var(--ink-2)] hover:text-[var(--ink)]"}`;
          }}>
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}

const inAWeek = () => {
  const d = new Date(Date.now() + 5.5 * 3600e3 + 7 * 86400e3);
  return d.toISOString().slice(0, 10);
};

/** Ask for a pay-by date, create the reminder, then offer PDF + WhatsApp. */
export function useReminderFlow(onCreated) {
  const [ready, setReady] = useState(null);
  const start = async (row) => {
    const values = await askForm({
      title: "Payment reminder",
      body: `${row.party || "Client"} · ${inr(row.outstanding)} due. This creates a reminder PDF and WhatsApp message only. It is not a receipt and posts nothing to Accounting.`,
      fields: [
        { name: "due_by", label: "Please pay by", type: "date", required: true, defaultValue: row.due_by || inAWeek() },
        { name: "message", label: "Note to add (optional)", multiline: true, placeholder: "e.g. Kindly clear before handover." },
      ],
      confirmLabel: "Create reminder",
    });
    if (!values) return;
    try {
      const { data } = await api.post("/accounting/reminders", {
        source_type: row.source_type, source_id: row.source_id, due_by: values.due_by, message: values.message || null,
      });
      setReady(data);
      onCreated?.(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not create the reminder");
    }
  };
  const element = ready ? <ReminderReady reminder={ready} onClose={() => setReady(null)} /> : null;
  return [start, element];
}

export function whatsappClick(reminder) {
  api.post(`/accounting/reminders/${reminder.id}/shared`).catch(() => {});
}

export function ReminderReady({ reminder, onClose }) {
  const [preview, setPreview] = useState(false);
  return createPortal(
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true" data-testid="reminder-ready">
      <div className="bg-white border border-[var(--line)] rounded-xl w-full max-w-md p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="overline">REMINDER {reminder.number}</div>
            <h3 className="font-display font-bold text-xl mt-1">{inr(reminder.amount_due)} due by {formatDate(reminder.due_by)}</h3>
            <p className="text-sm text-[var(--ink-2)] mt-1">{reminder.party_name || "Client"}{reminder.project_name ? ` · ${reminder.project_name}` : ""}</p>
          </div>
          <button type="button" className="btn-ghost" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button type="button" className="btn-ghost justify-center" onClick={() => setPreview(true)} data-testid="reminder-pdf">
            <FilePdf size={15} /> Reminder PDF
          </button>
          <a className="btn-primary justify-center" href={reminder.whatsapp_url} target="_blank" rel="noreferrer"
             onClick={() => whatsappClick(reminder)} data-testid="reminder-whatsapp">
            <WhatsappLogo size={15} /> Send on WhatsApp
          </a>
        </div>
        {!reminder.has_whatsapp_number && (
          <p className="text-xs text-[var(--warning)]">No mobile number is saved for this client, so WhatsApp will ask you to pick the chat.</p>
        )}
        <p className="text-xs text-[var(--ink-3)]">Nothing was posted to Accounting. When the money arrives, use Receive in Collections Due.</p>
      </div>
      {preview && <PdfPreviewModal path={`/accounting/reminders/${reminder.id}/pdf`} title={`Payment reminder ${reminder.number}`}
                                   filename={`${reminder.number}.pdf`} onClose={() => setPreview(false)} />}
    </div>,
    document.body,
  );
}
