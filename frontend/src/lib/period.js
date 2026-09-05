// Shared date-period helpers for Accounting (Daybook + Account ledger).
// India financial year runs Apr 1 -> Mar 31.

export const PERIOD_PRESETS = [
  { id: "today", label: "Today" },
  { id: "week", label: "This Week" },
  { id: "month", label: "This Month" },
  { id: "last_month", label: "Last Month" },
  { id: "year", label: "This Year" },
  { id: "fy", label: "Financial Year" },
  { id: "all", label: "All Time" },
  { id: "custom", label: "Custom" },
];

// Local (not UTC) yyyy-mm-dd so "today" matches the user's calendar day.
export function ymd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Returns { from, to } as yyyy-mm-dd strings ("" means unbounded).
// For "custom" returns null so the caller keeps its own from/to.
export function computeRange(preset) {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth(); // 0-11
  switch (preset) {
    case "today": {
      const t = ymd(now);
      return { from: t, to: t };
    }
    case "week": {
      // Monday as first day of week
      const dow = (now.getDay() + 6) % 7;
      const start = new Date(now);
      start.setDate(now.getDate() - dow);
      return { from: ymd(start), to: ymd(now) };
    }
    case "month":
      return { from: ymd(new Date(y, m, 1)), to: ymd(now) };
    case "last_month": {
      const start = new Date(y, m - 1, 1);
      const end = new Date(y, m, 0); // day 0 of this month = last day of prev month
      return { from: ymd(start), to: ymd(end) };
    }
    case "year":
      return { from: ymd(new Date(y, 0, 1)), to: ymd(now) };
    case "fy": {
      // FY starts Apr 1. If we're in Jan/Feb/Mar (m < 3) the FY began last year.
      const fyStart = m >= 3 ? y : y - 1;
      return { from: ymd(new Date(fyStart, 3, 1)), to: ymd(new Date(fyStart + 1, 2, 31)) };
    }
    case "all":
      return { from: "", to: "" };
    default:
      return null; // custom
  }
}

// Human label for the active preset (used in headers/summaries).
export function periodLabel(preset, from, to) {
  if (preset === "custom") {
    if (from && to) return `${from} → ${to}`;
    if (from) return `From ${from}`;
    if (to) return `Until ${to}`;
    return "Custom";
  }
  const p = PERIOD_PRESETS.find((x) => x.id === preset);
  return p ? p.label : "All Time";
}
