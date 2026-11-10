import { CaretRight, CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { dateForInput, formatDate, formatINR } from "../lib/format";

/**
 * Project overview without repetition: the tab bar is the navigation, the
 * lifecycle bar shows the stage and the Team card shows people, so this only
 * adds (1) the few facts shown nowhere else and (2) what needs attention now.
 */
const FEE_LABELS = {
  lump_sum: "Lump Sum",
  percentage_consultancy: "Consultancy %",
  turnkey: "Turnkey",
  per_sqft: "Per Sq Ft",
};

function projectFeeDisplay(p) {
  const fst = p.fee_structure_type;
  if (!fst) return null;
  const label = FEE_LABELS[fst] || fst;
  if (fst === "lump_sum" && p.fee_lump_sum_amount) return `${label} · ${formatINR(p.fee_lump_sum_amount)}`;
  if (fst === "percentage_consultancy" && p.fee_percentage) {
    const calc = p.fee_project_value ? formatINR(p.fee_project_value * p.fee_percentage / 100) : null;
    return `${label} · ${p.fee_percentage}%${calc ? ` = ${calc}` : ""}`;
  }
  if (fst === "turnkey" && p.fee_contract_value) return `${label} · ${formatINR(p.fee_contract_value)}`;
  if (fst === "per_sqft" && p.fee_rate_per_sqft) {
    const calc = p.site_area_sqft ? formatINR(p.site_area_sqft * p.fee_rate_per_sqft) : null;
    return `${label} · ₹${p.fee_rate_per_sqft}/sq ft${calc ? ` = ${calc}` : ""}`;
  }
  return label;
}

export function ProjectFacts({ p }) {
  const feeDisplay = projectFeeDisplay(p);
  const facts = [
    ["Client", p.client_name],
    ["Type", p.project_type],
    ["Area", p.site_area_sqft ? `${p.site_area_sqft} sq ft` : null],
    ["Location", p.site_address || p.location],
    ["Start", p.start_date ? formatDate(p.start_date) : null],
    ["Target end", p.end_date ? formatDate(p.end_date) : null],
    ...(feeDisplay ? [["Fee type", feeDisplay]] : []),
  ];
  return (
    <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-6 gap-y-4" data-testid="project-facts">
      {facts.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[10px] uppercase tracking-[0.18em] text-[var(--ink-3)]">{k}</dt>
          <dd className={`font-display text-lg leading-snug mt-1 break-words ${v ? "" : "text-[var(--ink-4)]"}`}>{v || "Not set"}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function ProjectAttention({ p, visibleTabs, onOpen, canSeeFinancials }) {
  const today = dateForInput(new Date());
  const tasks = p.tasks || [];
  const overdue = tasks.filter((t) => t.status !== "done" && t.due_date && t.due_date < today).length;
  const milestones = p.milestones || [];
  const dueMilestones = milestones.filter((m) => m.due_date && m.due_date <= today
    && Number(m.amount || 0) - Number(m.paid_amount || 0) > 0.009);
  const dueAmount = dueMilestones.reduce((s, m) => s + Number(m.amount || 0) - Number(m.paid_amount || 0), 0);
  const money = p.money || {};
  const outstanding = Number(money.still_to_receive ?? Math.max(0, Number(money.invoiced || 0) - Number(money.received || 0)));

  const items = [
    overdue > 0 && { tab: "Tasks", text: `${overdue} task${overdue > 1 ? "s are" : " is"} past due`, action: "Review tasks" },
    canSeeFinancials && dueMilestones.length > 0 && { tab: "Milestones",
      text: `${formatINR(dueAmount)} due from ${dueMilestones.length} milestone${dueMilestones.length > 1 ? "s" : ""}`, action: "Collect" },
    canSeeFinancials && outstanding > 0 && dueMilestones.length === 0 && { tab: "Milestones", text: `${formatINR(outstanding)} still to receive on this project`, action: "View fee milestones" },
    !p.project_manager && { tab: null, text: "No project manager assigned", action: null },
    p.has_phase_plan === false && { tab: "Phases", text: "No phase plan yet", action: "Plan phases" },
  ].filter(Boolean).filter((i) => !i.tab || visibleTabs.includes(i.tab));

  return (
    <section aria-labelledby="attention-title" data-testid="project-attention">
      <h2 id="attention-title" className="text-xs uppercase tracking-[0.18em] text-[var(--ink-3)] mb-2">Needs attention</h2>
      {items.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-[var(--success)]">
          <CheckCircle size={16} weight="fill" /> Nothing overdue on this project.
        </p>
      ) : (
        <ul className="divide-y divide-[var(--line-soft)] border-y border-[var(--line-soft)]">
          {items.map((i) => (
            <li key={i.text} className="flex items-center justify-between gap-3 py-2.5">
              <span className="flex items-center gap-2 text-sm">
                <WarningCircle size={16} className="text-[var(--warning)] shrink-0" /> {i.text}
              </span>
              {i.tab && (
                <button type="button" className="text-xs font-semibold text-[var(--accent-strong)] hover:text-[var(--ink)] inline-flex items-center gap-1 shrink-0"
                        onClick={() => onOpen(i.tab)} data-testid={`attention-${i.tab}`}>
                  {i.action} <CaretRight size={11} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
