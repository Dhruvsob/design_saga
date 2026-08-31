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
  create: "#1D633E", update: "#8B7F6A", stage_change: "#8B7F6A",
  archive: "#B22B22", restore: "#1D633E", convert: "#8A6DFF",
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
    <div className="border border-[#E5E5E5]" data-testid="activity-timeline">
      <div className="p-4 border-b border-[#E5E5E5] bg-[#FAFAFA] flex items-center gap-2">
        <ClockCounterClockwise size={14} />
        <span className="overline">ACTIVITY</span>
        <span className="font-mono text-xs text-[#9A9A9A] ml-auto">{rows.length}</span>
      </div>
      <div className="max-h-96 overflow-y-auto">
        {loading && <div className="p-4 text-xs font-mono uppercase tracking-wider text-[#9A9A9A]">Loading…</div>}
        {!loading && rows.length === 0 && (
          <div className="p-6 text-center text-sm text-[#9A9A9A]">
            No recorded activity yet. Edits, stage changes and archive actions will appear here.
          </div>
        )}
        <div className="relative">
          {rows.map((r, i) => {
            const verb = r.action?.split(".").pop() || "update";
            const color = ACTION_COLORS[verb] || "#5C5C5C";
            return (
              <div key={r.id || i} className="flex gap-3 px-4 py-3 border-b border-[#F0F0F0]" data-testid={`activity-row-${i}`}>
                <div className="flex flex-col items-center pt-1">
                  <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                  {i < rows.length - 1 && <div className="w-px flex-1 bg-[#E5E5E5] mt-1" />}
                </div>
                <div className="flex-1 min-w-0 pb-1">
                  <div className="text-sm">
                    <span className="font-semibold">{r.actor_email?.split("@")[0] || "someone"}</span>{" "}
                    <span className="text-[#5C5C5C]">{ACTION_LABELS[r.action] || r.action}</span>
                    {r.meta?.stage && <span className="ml-1 font-mono text-xs text-[#8B7F6A]">→ {r.meta.stage}</span>}
                  </div>
                  {r.meta?.fields && (
                    <div className="text-[10px] font-mono uppercase tracking-wider text-[#9A9A9A] mt-0.5">
                      {r.meta.fields.join(" · ")}
                    </div>
                  )}
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#9A9A9A] mt-0.5">
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
