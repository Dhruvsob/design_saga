import { useEffect, useRef, useState } from "react";
import { Eraser, FloppyDisk } from "@phosphor-icons/react";

/**
 * Draw a signature with finger, mouse or Apple Pencil (iPad Safari).
 * - `touch-action: none` stops the page scrolling while you sign.
 * - Pencil pressure changes the line thickness; mouse/finger use a medium line.
 * - Saves a transparent PNG data URL (no white box, no JPEG needed).
 */
export default function SignaturePad({ onSave, saving = false, ink = "#1E2440" }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const last = useRef(null);
  const [empty, setEmpty] = useState(true);

  const setup = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const { width, height } = canvas.getBoundingClientRect();
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = ink;
    setEmpty(true);
  };
  useEffect(() => { setup(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const point = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const pressure = e.pointerType === "pen" ? (e.pressure || 0.5) : 0.5;
    return { x: e.clientX - rect.left, y: e.clientY - rect.top, w: 1.4 + pressure * 3.2 };
  };
  const down = (e) => {
    e.preventDefault();
    canvasRef.current.setPointerCapture?.(e.pointerId);
    drawing.current = true;
    last.current = point(e);
  };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext("2d");
    const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];   // smooth Pencil strokes
    for (const ev of events) {
      const p = point(ev);
      const prev = last.current;
      const mid = { x: (prev.x + p.x) / 2, y: (prev.y + p.y) / 2 };
      ctx.lineWidth = (prev.w + p.w) / 2;
      ctx.beginPath();
      ctx.moveTo(prev.x, prev.y);
      ctx.quadraticCurveTo(prev.x, prev.y, mid.x, mid.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      last.current = p;
    }
    setEmpty(false);
  };
  const up = () => { drawing.current = false; last.current = null; };

  return (
    <div className="space-y-2" data-testid="signature-pad">
      <canvas
        ref={canvasRef}
        className="w-full h-44 rounded-lg border border-dashed border-[var(--line-strong)] bg-white cursor-crosshair"
        style={{ touchAction: "none" }}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={up}
        aria-label="Signature pad: sign here with Apple Pencil, finger or mouse"
        data-testid="signature-canvas"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-[var(--ink-3)]">Sign inside the box. Apple Pencil pressure is used.</span>
        <div className="flex gap-2">
          <button type="button" className="btn-ghost text-xs" onClick={setup} disabled={empty}><Eraser size={13} /> Clear</button>
          <button type="button" className="btn-primary text-xs" disabled={empty || saving}
            onClick={() => onSave(canvasRef.current.toDataURL("image/png"))} data-testid="signature-save">
            <FloppyDisk size={13} /> {saving ? "Saving…" : "Save signature"}
          </button>
        </div>
      </div>
    </div>
  );
}
