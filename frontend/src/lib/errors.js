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
