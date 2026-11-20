import axios from "axios";
import { normalizeErrorDetail } from "./errors";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Sessions live only in the HttpOnly, Secure, SameSite cookie so injected
// script cannot read them. A localStorage Bearer mirror is available only as
// an explicit opt-in (VITE_BEARER_FALLBACK=true) for split-origin setups.
const BEARER_FALLBACK = import.meta.env.VITE_BEARER_FALLBACK === "true";
const STORAGE_KEY = "ds_session_token";

try {
  if (!BEARER_FALLBACK) localStorage.removeItem(STORAGE_KEY); // purge legacy copies
} catch {
  /* storage unavailable */
}

export function setSessionToken(token) {
  if (!BEARER_FALLBACK) return;
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable — cookie-only mode */
  }
}

export function getSessionToken() {
  if (!BEARER_FALLBACK) return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

// In-flight write requests, used by the global double-submit guard.
const WRITE_METHODS = new Set(["post", "put", "patch", "delete"]);
let pendingWriteCount = 0;
const idleListeners = new Set();
export const pendingWrites = () => pendingWriteCount;
export function onWritesIdle(listener) {
  if (pendingWriteCount === 0) listener();
  else idleListeners.add(listener);
}
const writeFinished = (config) => {
  if (!config?.__countedWrite) return;
  pendingWriteCount = Math.max(0, pendingWriteCount - 1);
  if (pendingWriteCount === 0) {
    const listeners = [...idleListeners];
    idleListeners.clear();
    listeners.forEach((fn) => fn());
  }
};

api.interceptors.request.use((config) => {
  if (WRITE_METHODS.has(String(config.method || "get").toLowerCase())) {
    config.__countedWrite = true;
    pendingWriteCount += 1;
  }
  const token = getSessionToken();
  if (token && !config.headers?.Authorization) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => { writeFinished(response.config); return response; },
  (error) => {
    writeFinished(error?.config);
    normalizeErrorDetail(error);
    if (typeof window !== "undefined") {
      if (error?.response?.status === 423) {
        window.dispatchEvent(new CustomEvent("app-pin-locked"));
      } else if (error?.response?.status === 401 && !String(error?.config?.url || "").includes("/auth/pin/")) {
        // A PIN check never signs anyone out; wrong PINs are handled on the lock screen.
        // Keep protected routes from displaying stale data after server-side
        // expiry, password reset, tenant suspension or explicit revocation.
        window.dispatchEvent(new CustomEvent("session-invalid"));
      }
    }
    return Promise.reject(error);
  }
);

// A lookup list (clients, employees, vendors) that only fills a picker or a
// name column. Roles can lose access to one in Team & Roles (production: the
// studio's Designers have no client or employee access), and a 403 inside
// Promise.all used to reject the whole page load, leaving Projects and
// Quotations empty. Skip the call when the permission is missing and treat a
// failure as an empty list.
export const optionalList = (allowed, url, config) =>
  allowed ? api.get(url, config).catch(() => ({ data: [] })) : Promise.resolve({ data: [] });

export default api;
