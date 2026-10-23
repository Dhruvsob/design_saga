export function safeExternalUrl(value) {
  if (typeof value !== "string" || value.length > 2048 || /[\u0000-\u001f]/.test(value)) return null;
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function safeFileUrl(value, portalToken = null) {
  if (typeof value === "string" && /^\/api\/(files|vendors)\//.test(value)) {
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin) return null;
      if (portalToken && /^\/api\/files\//.test(url.pathname)) {
        url.searchParams.set("token", portalToken);
      }
      return url.href;
    } catch {
      return null;
    }
  }
  return safeExternalUrl(value);
}
