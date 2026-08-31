import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Bearer-token fallback: some browsers/proxies drop the httpOnly session
// cookie (e.g. Partitioned-cookie policies). We mirror the session token in
// localStorage and always send it as an Authorization header — the backend
// accepts either.
export function setSessionToken(token) {
  try {
    if (token) localStorage.setItem("ds_session_token", token);
    else localStorage.removeItem("ds_session_token");
  } catch {
    /* storage unavailable — cookie-only mode */
  }
}

export function getSessionToken() {
  try {
    return localStorage.getItem("ds_session_token");
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
