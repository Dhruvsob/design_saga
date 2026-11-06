import {
  CalendarCheck, CaretRight, ClockCounterClockwise, FolderSimple, Globe, ListChecks,
  Receipt, Stack, Truck, Wallet,
} from "@phosphor-icons/react";
import { formatDate, formatINR } from "../lib/format";

/**
 * Project home: key facts at a glance and one tile per area of the project
 * with a live count. Tiles open the matching tab; financial tiles appear
 * only for people who may see project money.
 */
export function ProjectFacts({ p }) {
  const team = [...(p.project_manager ? [p.project_manager] : []), ...(p.team || [])];
  const facts = [
    ["Client", p.client_name || "—"],
    ["Type", p.project_type || "—"],
    ["Area", p.site_area_sqft ? `${p.site_area_sqft} sq ft` : "—"],
    ["Location", p.site_address || p.location || "—"],
    ["Started", p.start_date ? formatDate(p.start_date) : "—"],
    ["Stage", p.stage || "—"],
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-x-6 gap-y-4 border-b border-[#E8E6E1] pb-6" data-testid="project-facts">
      {facts.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[#6E6A63]">{k}</div>
          <div className="font-display text-lg leading-snug mt-1 break-words">{v}</div>
        </div>
      ))}
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-[0.18em] text-[#6E6A63]">Team</div>
        <div className="flex -space-x-2 mt-1.5">
          {team.length === 0 && <span className="font-display text-lg">—</span>}
          {team.slice(0, 5).map((m) => (
            <span key={m.id} title={m.name}
                  className="w-8 h-8 rounded-full bg-[#3F3B33] text-white text-[11px] font-semibold flex items-center justify-center ring-2 ring-white">
              {(m.name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
            </span>
          ))}
          {team.length > 5 && (
            <span className="w-8 h-8 rounded-full bg-[#EFEDE6] text-[11px] font-semibold flex items-center justify-center ring-2 ring-white">
              +{team.length - 5}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProjectHub({ p, visibleTabs, onOpen, canSeeFinancials, onCopyPortal }) {
  const tasks = p.tasks || [];
  const done = tasks.filter((t) => t.status === "done").length;
  const open = tasks.length - done;
  const overdue = tasks.filter((t) => t.status !== "done" && t.due_date && t.due_date < new Date().toISOString().slice(0, 10)).length;
  const milestones = p.milestones || [];
  const dueAmount = milestones.reduce((s, m) => s + Math.max(0, Number(m.amount || 0) - Number(m.paid_amount || 0)), 0);
  const pos = (p.purchase_orders || []).length;
  const bills = (p.vendor_bills || []).length;
  const files = (p.files || []).length;
  const invoices = (p.invoices || []).length;
  const fin = p.financials || {};

  const tiles = [
    { tab: "Phases", Icon: Stack, title: "Phases", sub: "Plan, dates and deliverables" },
    { tab: "Tasks", Icon: ListChecks, title: "Tasks",
      sub: tasks.length ? `${open} open · ${done} done${overdue ? ` · ${overdue} overdue` : ""}` : "No tasks yet",
      warn: overdue > 0 },
    canSeeFinancials && { tab: "Milestones", Icon: Wallet, title: "Payment milestones",
      sub: milestones.length ? `${milestones.length} milestone${milestones.length > 1 ? "s" : ""} · ${formatINR(dueAmount)} to collect` : "Set the fee and bill each stage" },
    { tab: "Vendors", Icon: Truck, title: "Vendors & procurement",
      sub: pos + bills ? `${pos} PO${pos === 1 ? "" : "s"} · ${bills} bill${bills === 1 ? "" : "s"}` : "Nothing ordered yet" },
    { tab: "Files", Icon: FolderSimple, title: "Files & drawings", sub: files ? `${files} file${files === 1 ? "" : "s"}` : "No files yet" },
    canSeeFinancials && { tab: "Invoices", Icon: Receipt, title: "Invoices",
      sub: invoices ? `${invoices} invoice${invoices === 1 ? "" : "s"} · ${formatINR(fin.outstanding || 0)} outstanding` : "Nothing invoiced yet",
      warn: Number(fin.outstanding) > 0 },
    { tab: "Activity", Icon: ClockCounterClockwise, title: "Activity", sub: "Every change, in order" },
  ].filter(Boolean).filter((t) => visibleTabs.includes(t.tab));

  return (
    <section aria-labelledby="project-hub-title" data-testid="project-hub">
      <h2 id="project-hub-title" className="font-display text-2xl mb-4">In this project</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {tiles.map(({ tab, Icon, title, sub, warn }) => (
          <button key={tab} type="button" onClick={() => onOpen(tab)} data-testid={`hub-${tab}`}
                  className="group text-left flex items-center gap-4 p-4 rounded-xl border border-[#E8E6E1] bg-white hover:border-[#76705E] hover:shadow-[0_8px_24px_-16px_rgba(17,17,17,0.35)] transition">
            <span className="w-11 h-11 rounded-lg bg-[#F5EFE6] text-[#8a6f24] flex items-center justify-center shrink-0">
              <Icon size={20} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-[15px]">{title}</span>
              <span className={`block text-xs mt-0.5 line-clamp-2 ${warn ? "text-[#B4541C]" : "text-[#6E6A63]"}`}>{sub}</span>
            </span>
            <CaretRight size={14} className="text-[#B8B3A8] group-hover:text-[#76705E] group-hover:translate-x-0.5 transition shrink-0" />
          </button>
        ))}
        {onCopyPortal && (
          <button type="button" onClick={onCopyPortal} data-testid="hub-portal"
                  className="group text-left flex items-center gap-4 p-4 rounded-xl border border-[#E8E6E1] bg-white hover:border-[#76705E] transition">
            <span className="w-11 h-11 rounded-lg bg-[#EEF3EE] text-[#1D633E] flex items-center justify-center shrink-0"><Globe size={20} /></span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-[15px]">Client portal</span>
              <span className="block text-xs mt-0.5 text-[#6E6A63]">Copy the link to share progress</span>
            </span>
            <CalendarCheck size={14} className="text-[#B8B3A8] shrink-0" />
          </button>
        )}
      </div>
    </section>
  );
}
