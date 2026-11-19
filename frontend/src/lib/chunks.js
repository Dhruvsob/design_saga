// Each deploy replaces the hashed page bundles, so a tab opened before a deploy
// asks for files that no longer exist the first time it opens another page.
// Reload once to pick up the new version; never loop (a failed write to
// sessionStorage, or a second failure within a minute, shows the error instead).
const KEY = "gamaa.chunk-reload-at";

export const isChunkError = (e) =>
  /dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i
    .test(String(e?.message || e || ""));

export function reloadForNewVersion() {
  try {
    const last = Number(window.sessionStorage.getItem(KEY)) || 0;
    if (Date.now() - last < 60_000) return false;
    window.sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    return false;
  }
  window.location.reload();
  return true;
}

// Wraps a lazy page factory: on a stale-bundle failure, reload once and keep
// the loading state until the reload lands; otherwise rethrow for the boundary.
export const withChunkReload = (factory) => () =>
  factory().catch((e) => {
    if (isChunkError(e) && reloadForNewVersion()) return new Promise(() => {});
    throw e;
  });
