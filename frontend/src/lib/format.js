// ---------------------------------------------------------------------------
// India-style formatting helpers — single source of truth for the whole ERP.
//   • Dates  → DD/MM/YYYY
//   • Times  → IST (Asia/Kolkata)
//   • Money  → ₹ / INR (en-IN grouping)
//   • Financial year → 1 Apr – 31 Mar
// Keep these pure + defensive: bad/empty inputs return "" (or a fallback) so
// callers can drop them in JSX without guards.
// ---------------------------------------------------------------------------

const IST_TZ = "Asia/Kolkata";

// Parse loose inputs (Date | ISO string | "YYYY-MM-DD" | epoch) → Date | null
function toDate(value) {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date) return isNaN(value) ? null : value;
  // Pure date "YYYY-MM-DD" → treat as calendar date (no TZ shift surprises)
  if (typeof value === "string") {
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) {
      const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
      return isNaN(d) ? null : d;
    }
  }
  const d = new Date(value);
  return isNaN(d) ? null : d;
}

const pad = (n) => String(n).padStart(2, "0");

// DD/MM/YYYY
export function formatDate(value, fallback = "—") {
  if (typeof value === "string") {
    const calendar = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (calendar) {
      const year = Number(calendar[1]);
      const month = Number(calendar[2]);
      const day = Number(calendar[3]);
      const check = new Date(Date.UTC(year, month - 1, day));
      if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1
          || check.getUTCDate() !== day) return fallback;
      return `${calendar[3]}/${calendar[2]}/${calendar[1]}`;
    }
  }
  const d = toDate(value);
  if (!d) return fallback;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: IST_TZ, day: "2-digit", month: "2-digit", year: "numeric",
    }).format(d);
  } catch {
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
  }
}

// DD/MM/YYYY, HH:MM (24h) rendered in IST
export function formatDateTime(value, fallback = "—") {
  const d = toDate(value);
  if (!d) return fallback;
  try {
    const date = new Intl.DateTimeFormat("en-GB", {
      timeZone: IST_TZ, day: "2-digit", month: "2-digit", year: "numeric",
    }).format(d);
    const time = new Intl.DateTimeFormat("en-GB", {
      timeZone: IST_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
    return `${date}, ${time}`;
  } catch {
    return `${formatDate(d)}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}

// HH:MM (24h) in IST
export function formatTime(value, fallback = "—") {
  const d = toDate(value);
  if (!d) return fallback;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: IST_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
  } catch {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}

// "DD Mon YYYY" (e.g. 05 Sep 2026) — for headers where slashes feel heavy
export function formatDateLong(value, fallback = "—") {
  const d = toDate(value);
  if (!d) return fallback;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: IST_TZ, day: "2-digit", month: "short", year: "numeric",
    }).format(d);
  } catch {
    return formatDate(d, fallback);
  }
}

// yyyy-mm-dd for <input type="date"> values (never throws)
export function dateForInput(value) {
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const d = toDate(value);
  if (!d) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: IST_TZ, day: "2-digit", month: "2-digit", year: "numeric",
    }).formatToParts(d);
    const part = (type) => parts.find((item) => item.type === type)?.value;
    return `${part("year")}-${part("month")}-${part("day")}`;
  } catch {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
}

// ₹ 1,23,456.78  (2 decimals only when needed)
export function formatINR(amount, { decimals } = {}) {
  const n = Number(amount);
  if (amount === null || amount === undefined || amount === "" || isNaN(n)) return "₹0";
  const opts = decimals != null
    ? { minimumFractionDigits: decimals, maximumFractionDigits: decimals }
    : { maximumFractionDigits: 2 };
  return `${n < 0 ? "−" : ""}₹${Math.abs(n).toLocaleString("en-IN", opts)}`;   // −₹5,000, never ₹-5,000
}

// Employee display name from either `name` or first/last parts (defensive).
export function empName(e) {
  if (!e) return "";
  if (e.name) return e.name;
  const full = [e.first_name, e.last_name].filter(Boolean).join(" ").trim();
  return full || e.employee_id || e.email || "";
}

// Indian financial year for a given date → { start, end, label } (Apr 1 – Mar 31)
export function financialYear(value = new Date()) {
  const calendarDate = dateForInput(value) || dateForInput(new Date());
  const [y, month] = calendarDate.split("-").map(Number);
  const startYear = month >= 4 ? y : y - 1;
  return {
    start: `${startYear}-04-01`,
    end: `${startYear + 1}-03-31`,
    label: `FY ${startYear}-${String(startYear + 1).slice(-2)}`,
  };
}

/**
 * Round to paise with half-up semantics, matching backend core/money.py.
 * The exponent shift avoids binary-float drift (2.675 -> 2.68, not 2.67).
 */
export function roundPaise(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  const sign = n < 0 ? -1 : 1;
  return sign * Number(`${Math.round(Number(`${Math.abs(n)}e2`))}e-2`);
}


// Codes stored in the database ("partially_paid", "pending_l1", "ProjectManager")
// shown as words people use. Unknown codes are humanised, never shown raw.
const STATUS_WORDS = {
  partially_paid: "Part paid", partially_received: "Part received", pending_l1: "Awaiting manager",
  pending_l2: "Awaiting finance", receipt_required: "Receipt needed", pending_approval: "Awaiting approval",
  in_progress: "In progress", on_hold: "On hold", bank_transfer: "Bank transfer", walk_in: "Walk-in",
  site_visit: "Site visit", week_off: "Week off", half_day: "Half day", paid_leave: "Paid leave",
  unpaid_leave: "Unpaid leave", comp_off: "Comp off", ProjectManager: "Project Manager",
  SuperAdmin: "Super Admin", full_time: "Full time", part_time: "Part time",
};
export function statusLabel(code) {
  if (code === null || code === undefined || code === "") return "—";
  const key = String(code);
  if (STATUS_WORDS[key]) return STATUS_WORDS[key];
  const words = key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
