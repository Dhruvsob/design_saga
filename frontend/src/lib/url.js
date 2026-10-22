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
