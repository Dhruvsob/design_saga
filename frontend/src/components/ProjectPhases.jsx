import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckSquare, Square, Warning } from "@phosphor-icons/react";
import api from "../lib/api";
import { dateForInput, formatDate, formatINR, roundPaise } from "../lib/format";

const STATUS = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
];
const STATUS_STYLE = {
  not_started: "bg-[var(--hover)] text-[var(--ink-2)]",
  in_progress: "bg-[var(--warning-soft)] text-[var(--warning)]",
  done: "bg-[var(--success-soft)] text-[var(--success)]",
};

/**
 * Project phase plan (PRJ-01): apply an architecture template, then track
 * each phase's status, dates and deliverables. Fee amounts are shown only to
 * users who can see project financials.
 */
export default function ProjectPhases({ projectId, project, canEdit, canSeeFinancials, onChanged }) {
  const [data, setData] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [choice, setChoice] = useState(project?.engagement_type === "turnkey" ? "turnkey" : "consultancy");
  const [startDate, setStartDate] = useState(project?.start_date || dateForInput(new Date()));
  const [withMilestones, setWithMilestones] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const { data: res } = await api.get(`/projects/${projectId}/phases`);
      setData(res);
      if (!res.phases.length) {
        const { data: tpl } = await api.get("/project-phase-templates");
        setTemplates(tpl);
      }
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not load the phase plan. Try again.");
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [projectId]);

  const apply = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const { data: res } = await api.post(`/projects/${projectId}/phases/apply`, {
        template: choice, start_date: startDate, create_fee_milestones: withMilestones,
      });
      setData(res);
      toast.success(res.milestones_created
        ? `Phase plan created with ${res.milestones_created} fee milestones`
        : "Phase plan created");
      if (res.milestones_created) onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not apply the template");
    } finally { setBusy(false); }
  };

  const patch = async (phase, body) => {
    try {
      const { data: res } = await api.patch(`/projects/${projectId}/phases/${phase.id}`, body);
      setData(res);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update the phase");
    }
  };

  const toggleDeliverable = (phase, id) => patch(phase, {
    deliverables: phase.deliverables.map((d) => (d.id === id ? { ...d, done: !d.done } : d)),
  });

  if (error) {
    return (
      <div className="card-flat" role="alert">
        <p className="text-sm text-[var(--danger)]">{error}</p>
        <button type="button" className="btn-ghost mt-3" onClick={load}>Retry</button>
      </div>
    );
  }
  if (!data) return <div className="card-flat text-sm text-[var(--ink-3)]" aria-busy="true">Loading phase plan…</div>;

  const budget = Number(project?.budget || 0);

  if (!data.phases.length) {
    const selected = templates.find((t) => t.key === choice);
    return (
      <div className="card-flat" data-testid="phase-setup">
        <div className="overline">PHASE PLAN</div>
        <h3 className="font-display font-bold text-xl mt-1">Plan this project in phases</h3>
        <p className="text-sm text-[var(--ink-2)] mt-1 max-w-2xl">
          Start from a standard architecture workflow. Phases, dates and deliverables stay fully editable afterwards.
        </p>
        {!canEdit ? (
          <p className="text-sm text-[var(--ink-3)] mt-4">No phase plan yet. Someone who can edit projects can create one.</p>
        ) : (
          <form onSubmit={apply} className="mt-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3" role="radiogroup" aria-label="Phase template">
              {templates.map((t) => (
                <label key={t.key} data-testid={`template-${t.key}`}
                       className={`block p-4 rounded-lg border cursor-pointer transition ${choice === t.key
                         ? "border-[var(--accent-strong)] bg-[var(--surface-2)]" : "border-[var(--line)] bg-white hover:border-[var(--accent-strong)]"}`}>
                  <span className="flex items-center gap-2">
                    <input type="radio" name="template" value={t.key} checked={choice === t.key}
                           onChange={() => setChoice(t.key)} />
                    <span className="font-semibold">{t.label}</span>
                  </span>
                  <span className="block text-xs text-[var(--ink-3)] mt-1">
                    {t.phases.length} phases · about {t.total_weeks} weeks · {t.description}
                  </span>
                </label>
              ))}
            </div>
            {selected && (
              <ol className="text-sm grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1" aria-label="Phases in this template">
                {selected.phases.map((ph, i) => (
                  <li key={ph.name} className="flex justify-between gap-3 border-b border-[var(--line-soft)] py-1">
                    <span>{i + 1}. {ph.name}</span>
                    <span className="text-[var(--ink-3)] whitespace-nowrap">{ph.weeks} wk · {ph.fee_pct}% fee</span>
                  </li>
                ))}
              </ol>
            )}
            <div className="flex flex-wrap items-end gap-4">
              <label className="text-xs">Start date
                <input type="date" className="input-flat mt-1 block" value={startDate} required
                       onChange={(e) => setStartDate(e.target.value)} data-testid="phase-start" />
              </label>
              {canSeeFinancials && (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={withMilestones} disabled={budget <= 0}
                         onChange={(e) => setWithMilestones(e.target.checked)} data-testid="phase-milestones" />
                  Create fee milestones from phases
                  <span className="text-xs text-[var(--ink-3)]">
                    {budget > 0 ? `(fee ${formatINR(budget)})` : "(set a project fee first)"}
                  </span>
                </label>
              )}
              <button type="submit" className="btn-primary" disabled={busy} data-testid="phase-apply">
                {busy ? "Creating…" : "Create phase plan"}
              </button>
            </div>
          </form>
        )}
      </div>
    );
  }

  const s = data.summary;
  return (
    <div className="space-y-4" data-testid="phase-plan">
      <div className="card-flat">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="overline">PHASE PLAN · {s.done} OF {s.total} DONE</div>
            <div className="text-sm mt-1">
              {s.current_phase ? <>Current phase: <strong>{s.current_phase}</strong></> : "All phases complete"}
              <span className="text-[var(--ink-3)]"> · Deliverables {s.deliverables_done}/{s.deliverables_total}</span>
            </div>
          </div>
          <div className="text-2xl font-display font-bold" data-testid="phase-progress">{s.progress_pct}%</div>
        </div>
        <div className="mt-3 h-2 rounded-full bg-[var(--line-soft)] overflow-hidden" aria-hidden="true">
          <div className="h-full bg-[var(--accent-strong)]" style={{ width: `${s.progress_pct}%` }} />
        </div>
        {s.overdue_phases.length > 0 && (
          <p className="mt-3 text-sm text-[var(--warning)] flex items-center gap-2" role="status">
            <Warning size={16} aria-hidden="true" /> Past planned end: {s.overdue_phases.join(", ")}
          </p>
        )}
      </div>

      <ol className="space-y-3">
        {data.phases.map((ph, index) => (
          <li key={ph.id} className="card-flat" data-testid={`phase-${index}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs text-[var(--ink-3)]">Phase {index + 1}</div>
                <h4 className="font-semibold text-base">{ph.name}</h4>
                <div className="text-xs text-[var(--ink-2)] mt-1">
                  Planned {formatDate(ph.planned_start)} – {formatDate(ph.planned_end)}
                  {ph.actual_start && <> · Started {formatDate(ph.actual_start)}</>}
                  {ph.actual_end && <> · Finished {formatDate(ph.actual_end)}</>}
                  {canSeeFinancials && (
                    <> · {ph.fee_pct}% fee{budget > 0 && <> ({formatINR(roundPaise(budget * ph.fee_pct / 100))})</>}</>
                  )}
                </div>
              </div>
              {canEdit ? (
                <select aria-label={`Status of ${ph.name}`} className={`input-flat !w-auto text-sm ${STATUS_STYLE[ph.status]}`}
                        value={ph.status} onChange={(e) => patch(ph, { status: e.target.value })}
                        data-testid={`phase-status-${index}`}>
                  {STATUS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              ) : (
                <span className={`text-xs px-2 py-1 rounded ${STATUS_STYLE[ph.status]}`}>
                  {STATUS.find((o) => o.value === ph.status)?.label}
                </span>
              )}
            </div>
            {canEdit && (
              <div className="flex flex-wrap gap-3 mt-3">
                <label className="text-xs">Planned start
                  <input type="date" className="input-flat mt-1 block" value={ph.planned_start || ""}
                         onChange={(e) => e.target.value && patch(ph, { planned_start: e.target.value })} />
                </label>
                <label className="text-xs">Planned end
                  <input type="date" className="input-flat mt-1 block" value={ph.planned_end || ""}
                         onChange={(e) => e.target.value && patch(ph, { planned_end: e.target.value })} />
                </label>
              </div>
            )}
            {(ph.deliverables || []).length > 0 && (
              <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-1" aria-label={`Deliverables for ${ph.name}`}>
                {ph.deliverables.map((d) => (
                  <li key={d.id}>
                    <button type="button" disabled={!canEdit} onClick={() => toggleDeliverable(ph, d.id)}
                            aria-pressed={d.done} data-testid={`deliverable-${d.id}`}
                            className={`flex items-center gap-2 text-sm text-left w-full px-2 py-1 rounded ${canEdit ? "hover:bg-[var(--hover)]" : ""}`}>
                      {d.done
                        ? <CheckSquare size={16} weight="fill" className="text-[var(--success)] shrink-0" aria-hidden="true" />
                        : <Square size={16} className="text-[var(--ink-3)] shrink-0" aria-hidden="true" />}
                      <span className={d.done ? "line-through text-[var(--ink-3)]" : ""}>{d.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
