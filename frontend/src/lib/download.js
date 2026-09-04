import { API, getSessionToken } from "./api";

// Authenticated file download (CSV/PDF). Sends the bearer token so it works
// even when the httpOnly session cookie is dropped by the browser.
export async function downloadFile(path, filename) {
  const token = getSessionToken();
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
