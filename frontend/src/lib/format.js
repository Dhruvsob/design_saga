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
  const d = toDate(value);
  if (!d) return fallback;
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
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
  const d = toDate(value);
  if (!d) return "";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ₹ 1,23,456.78  (2 decimals only when needed)
export function formatINR(amount, { decimals } = {}) {
  const n = Number(amount);
  if (amount === null || amount === undefined || amount === "" || isNaN(n)) return "₹0";
  const opts = decimals != null
    ? { minimumFractionDigits: decimals, maximumFractionDigits: decimals }
    : { maximumFractionDigits: 2 };
  return `₹${n.toLocaleString("en-IN", opts)}`;
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
  const d = toDate(value) || new Date();
  const y = d.getFullYear();
  const startYear = d.getMonth() >= 3 ? y : y - 1; // month 3 = April
  return {
    start: `${startYear}-04-01`,
    end: `${startYear + 1}-03-31`,
    label: `FY ${startYear}-${String(startYear + 1).slice(-2)}`,
  };
}
