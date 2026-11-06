import { useEffect, useState } from "react";
import api from "../lib/api";
import { ClockCounterClockwise } from "@phosphor-icons/react";

const ACTION_LABELS = {
  "project.create": "created this project",
  "project.update": "edited project details",
  "project.stage_change": "moved the stage",
  "project.archive": "archived this project",
  "project.restore": "restored this project",
  "client.update": "edited client details",
  "client.archive": "archived this client",
  "client.restore": "restored this client",
  "lead.convert": "converted the lead",
};

const ACTION_COLORS = {
  create: "#1E6A45", update: "#9C4A28", stage_change: "#9C4A28",
  archive: "#B3261E", restore: "#1E6A45", convert: "#2E5694",
};

const fmtWhen = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) +
    " · " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
};

export default function ActivityTimeline({ entityType, entityId }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/activity/${entityType}/${entityId}`)
      .then((r) => setRows(r.data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [entityType, entityId]);

  return (
    <div className="border border-[var(--line)]" data-testid="activity-timeline">
      <div className="p-4 border-b border-[var(--line)] bg-[var(--surface-2)] flex items-center gap-2">
        <ClockCounterClockwise size={14} />
        <span className="overline">ACTIVITY</span>
        <span className="font-mono text-xs text-[var(--ink-3)] ml-auto">{rows.length}</span>
      </div>
      <div className="max-h-96 overflow-y-auto">
        {loading && <div className="p-4 text-xs font-mono uppercase tracking-wider text-[var(--ink-3)]">Loading…</div>}
        {!loading && rows.length === 0 && (
          <div className="p-6 text-center text-sm text-[var(--ink-3)]">
            No recorded activity yet. Edits, stage changes and archive actions will appear here.
          </div>
        )}
        <div className="relative">
          {rows.map((r, i) => {
            const verb = r.action?.split(".").pop() || "update";
            const color = ACTION_COLORS[verb] || "#4A4741";
            return (
              <div key={r.id || i} className="flex gap-3 px-4 py-3 border-b border-[var(--line-soft)]" data-testid={`activity-row-${i}`}>
                <div className="flex flex-col items-center pt-1">
                  <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                  {i < rows.length - 1 && <div className="w-px flex-1 bg-[var(--line)] mt-1" />}
                </div>
                <div className="flex-1 min-w-0 pb-1">
                  <div className="text-sm">
                    <span className="font-semibold">{r.actor_email?.split("@")[0] || "someone"}</span>{" "}
                    <span className="text-[var(--ink-2)]">{ACTION_LABELS[r.action] || r.action}</span>
                    {r.meta?.stage && <span className="ml-1 font-mono text-xs text-[var(--accent-strong)]">→ {r.meta.stage}</span>}
                  </div>
                  {r.meta?.fields && (
                    <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-3)] mt-0.5">
                      {r.meta.fields.join(" · ")}
                    </div>
                  )}
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-3)] mt-0.5">
                    {fmtWhen(r.at)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
