// Remembers, on this device only, which workspace last signed in here so the
// shared Gamaa sign-in page can greet returning users with their studio's name
// and logo. Purely cosmetic: sign-in never depends on it.
const KEY = "gamaa.workspace";
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,62}$/;

export function rememberedWorkspace() {
  try {
    const slug = localStorage.getItem(KEY) || "";
    return SLUG_RE.test(slug) ? slug : "";
  } catch {
    return "";
  }
}

export function rememberWorkspace(slug) {
  if (!SLUG_RE.test(String(slug || ""))) return;
  try { localStorage.setItem(KEY, slug); } catch { /* storage unavailable */ }
}

export function forgetWorkspace() {
  try { localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

export function isWorkspaceSlug(slug) {
  return SLUG_RE.test(String(slug || ""));
}
