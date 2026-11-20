// One readable message from any API failure.
//  - "detail" string                -> as is
//  - {message} object               -> its message
//  - FastAPI validation list (422)  -> "Expected time: Time must be HH:MM ..." (field + reason)
//  - no response at all             -> connection message
const FIELD = (loc) => {
  const name = Array.isArray(loc) ? loc[loc.length - 1] : null;
  if (!name || name === "body" || typeof name !== "string") return "";
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1) + ": ";
};

export function errText(e, fallback = "Something went wrong. Please try again.") {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d.trim()) return d;
  if (d && typeof d === "object" && !Array.isArray(d) && typeof d.message === "string") return d.message;
  if (Array.isArray(d) && d.length) {
    return d.map((x) => (x?.msg ? `${FIELD(x.loc)}${String(x.msg).replace(/^Value error, /, "")}` : String(x))).join(" · ");
  }
  if (e && !e.response && (e.code === "ERR_NETWORK" || e.message === "Network Error")) {
    return "No connection to the server. Check your internet and try again.";
  }
  return fallback;
}

// FastAPI validation errors (422) arrive as a list of objects. Screens pass
// `detail` straight to a toast, and rendering a list of objects throws ("Objects
// are not valid as a React child"), taking the page down. The API layer calls
// this once so every screen gets readable text; the raw list stays in `errors`.
export function normalizeErrorDetail(error) {
  const data = error?.response?.data;
  if (data && typeof data === "object" && Array.isArray(data.detail)) {
    const text = errText(error);
    data.errors = data.detail;
    data.detail = text;
  }
  return error;
}

// One entry per problem for ErrorSummary: field-level validation errors keep
// their field name (so the summary can jump to it); anything else is one line.
export function errorItems(error, fallback = "Something went wrong. Please try again.") {
  const data = error?.response?.data;
  const list = Array.isArray(data?.errors) ? data.errors : Array.isArray(data?.detail) ? data.detail : null;
  if (list && list.length) {
    return list.map((x) => {
      // Full path without "body": "first_name", or "items.2.rate" for a line.
      const loc = (Array.isArray(x?.loc) ? x.loc : []).filter((p) => p !== "body");
      const field = loc.length ? loc.join(".") : null;
      return { field, text: String(x?.msg || x).replace(/^Value error, /, "") };
    });
  }
  return [{ field: null, text: errText(error, fallback) }];
}
