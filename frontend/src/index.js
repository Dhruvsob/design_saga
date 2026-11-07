import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { installSubmitGuard } from "@/lib/submitGuard";

// Ignore a harmless browser DataCloneError from PerformanceServerTiming
// (was an inline <script>, which the site's CSP correctly blocks).
window.addEventListener("error", (e) => {
  if (e.error instanceof DOMException && e.error.name === "DataCloneError"
      && e.message && e.message.includes("PerformanceServerTiming")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
}, true);
import { pendingWrites, onWritesIdle } from "@/lib/api";
import { toast } from "sonner";

// Safety net: a save/delete the screen didn't handle must never fail silently.
// Shows the server's own message (e.g. "Leave dates overlap"); 401/423 are handled
// by the session / App PIN flows, and screens that catch their errors never reach here.
window.addEventListener("unhandledrejection", (event) => {
  const err = event.reason;
  const status = err?.response?.status;
  if (!err?.isAxiosError || status === 401 || status === 423) return;
  // A refused *read* just means this person can't see that section; not an error to shout about.
  if (status === 403 && String(err.config?.method || "get").toLowerCase() === "get") return;
  const detail = err.response?.data?.detail;
  const text = typeof detail === "string" ? detail
    : Array.isArray(detail) ? detail.map((d) => d?.msg || String(d)).join(" · ")
    : status ? "The server could not complete that action. Please try again."
    : "No connection to the server. Check your internet and try again.";
  toast.error(text);
  event.preventDefault();
});

installSubmitGuard(document, { pendingWrites, onWritesIdle });

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
