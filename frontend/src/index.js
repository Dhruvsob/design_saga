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

installSubmitGuard(document, { pendingWrites, onWritesIdle });

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
