import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Sessions live only in the HttpOnly, Secure, SameSite cookie so injected
// script cannot read them. A localStorage Bearer mirror is available only as
// an explicit opt-in (REACT_APP_BEARER_FALLBACK=true) for split-origin setups.
const BEARER_FALLBACK = process.env.REACT_APP_BEARER_FALLBACK === "true";
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

api.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token && !config.headers?.Authorization) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
