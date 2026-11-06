import { useEffect, useState } from "react";
import { ArrowSquareOut, DownloadSimple, FilePdf, X } from "@phosphor-icons/react";
import api, { API } from "../lib/api";

/**
 * In-app PDF preview that works with the site's anti-clickjacking headers.
 *
 * API responses are sent with X-Frame-Options: DENY / frame-ancestors 'none',
 * so an <iframe src="/api/..pdf"> is refused by the browser. We fetch the PDF
 * with the user's session and show it from a blob: URL instead (allowed by the
 * page CSP's frame-src), with Open/Download fallbacks that always work.
 */
export function PdfFrame({ path, title, className = "w-full h-full" }) {
  const [url, setUrl] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    let objectUrl = null;
    setUrl(null);
    setError("");
    api.get(path, { responseType: "blob" })
      .then(({ data }) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
        setUrl(objectUrl);
      })
      .catch(() => alive && setError("The PDF could not be loaded. Try Open in new tab."));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (error) {
    return (
      <div className={`${className} flex flex-col items-center justify-center gap-3 text-sm text-[var(--ink-2)] bg-[var(--surface-2)]`} role="alert">
        <FilePdf size={36} className="text-[var(--danger)]" />
        {error}
        <a className="btn-ghost" href={`${API}${path}`} target="_blank" rel="noreferrer"><ArrowSquareOut size={14} /> Open in new tab</a>
      </div>
    );
  }
  if (!url) {
    return (
      <div className={`${className} flex items-center justify-center bg-[var(--surface-2)]`} aria-busy="true">
        <div className="flex flex-col items-center gap-3 text-sm text-[var(--ink-3)]">
          <span className="w-8 h-8 rounded-full border-2 border-[var(--line)] border-t-[var(--accent-strong)] animate-spin" />
          Preparing preview…
        </div>
      </div>
    );
  }
  return <iframe title={title} src={url} className={className} data-testid="pdf-frame" />;
}

/** Full-screen modal preview with header actions. */
export default function PdfPreviewModal({ path, title, filename, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-[2px] z-50 flex items-center justify-center p-2 sm:p-6"
         onClick={onClose} role="dialog" aria-modal="true" aria-label={title} data-testid="pdf-preview">
      <div className="bg-white w-full max-w-4xl h-[94vh] flex flex-col rounded-xl overflow-hidden shadow-2xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--line)]">
          <div className="min-w-0 flex items-center gap-2">
            <FilePdf size={18} className="text-[var(--accent-strong)] shrink-0" />
            <span className="font-semibold truncate">{title}</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <a className="btn-ghost text-xs" href={`${API}${path}`} target="_blank" rel="noreferrer">
              <ArrowSquareOut size={13} /> <span className="hidden sm:inline">Open</span>
            </a>
            <a className="btn-ghost text-xs" href={`${API}${path}`} download={filename || true}>
              <DownloadSimple size={13} /> <span className="hidden sm:inline">Download</span>
            </a>
            <button type="button" className="btn-icon" onClick={onClose} aria-label="Close preview" data-testid="pdf-preview-close">
              <X size={16} />
            </button>
          </div>
        </div>
        <PdfFrame path={path} title={title} className="w-full flex-1" />
      </div>
    </div>
  );
}
