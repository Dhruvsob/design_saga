import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { installSubmitGuard } from "@/lib/submitGuard";
import { pendingWrites, onWritesIdle } from "@/lib/api";

installSubmitGuard(document, { pendingWrites, onWritesIdle });

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
