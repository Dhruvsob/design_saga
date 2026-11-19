import { useEffect, useState } from "react";
import { Image as ImageIcon } from "@phosphor-icons/react";
import api from "../lib/api";

/**
 * An image served by an authenticated API route (e.g. product library photos).
 * Loaded with the user's session as a blob, so it works with bearer-token sessions
 * too, then shown from an object URL that is released when the component goes away.
 */
export default function AuthImage({ src, alt = "", className = "", fallbackClassName = "" }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!src) return undefined;
    let alive = true;
    let objectUrl = null;
    setUrl(null);
    setFailed(false);
    const path = src.startsWith("/api/") ? src.slice(4) : src;
    api.get(path, { responseType: "blob" })
      .then(({ data }) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(data);
        setUrl(objectUrl);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (!src || failed || !url) {
    return (
      <div className={`flex items-center justify-center bg-[var(--surface-2)] text-[var(--ink-3)] ${fallbackClassName || className}`}
           aria-hidden={!src || failed ? "true" : undefined}>
        <ImageIcon size={28} className={src && !failed ? "animate-pulse" : ""} />
      </div>
    );
  }
  return <img src={url} alt={alt} className={className} />;
}
