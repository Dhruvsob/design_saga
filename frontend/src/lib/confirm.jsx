import { useEffect, useState } from "react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../components/ui/alert-dialog";

/**
 * Styled, accessible replacement for window.confirm().
 *
 *   if (!await confirmAction("Delete this holiday?")) return;
 *   await confirmAction({ title, body, confirmLabel, danger })
 *
 * A plain message is split into a title (first line/sentence) and body; the
 * confirm button turns red for destructive wording. Resolves true/false.
 */
let open = null;
const queue = [];

const DESTRUCTIVE = /\b(delete|remove|reverse|terminate|archive|cancel|deactivate|disconnect|reset|suspend|disable)\b/i;

function normalise(input) {
  if (typeof input === "object" && input) return input;
  const text = String(input ?? "").trim();
  const [first, ...rest] = text.split(/\n+/);
  let title = first;
  let body = rest.join("\n").trim();
  const m = first.match(/^(.+?\?)\s+(.+)$/);
  if (m && first.length > 70) {
    title = m[1];
    body = [m[2], body].filter(Boolean).join("\n");
  }
  const verb = (title.match(DESTRUCTIVE) || [])[1];
  return {
    title, body,
    danger: Boolean(verb),
    confirmLabel: verb ? verb[0].toUpperCase() + verb.slice(1).toLowerCase() : "Continue",
    cancelLabel: verb && verb.toLowerCase() === "cancel" ? "Go back" : "Cancel",
  };
}

export function confirmAction(input) {
  return new Promise((resolve) => {
    const request = { ...normalise(input), resolve };
    if (open) open(request);
    else queue.push(request);
  });
}

/**
 * In-app form dialog replacing window.prompt() chains.
 *
 *   const v = await askForm({ title: "Add warning", confirmLabel: "Save", fields: [
 *     { name: "reason", label: "Reason", required: true },
 *     { name: "note", label: "Note (optional)", multiline: true },
 *   ]});
 *   if (!v) return;            // cancelled
 */
export function askForm({ title, body, fields, confirmLabel = "Save", danger = false }) {
  return new Promise((resolve) => {
    const request = { title, body, fields, confirmLabel, danger, cancelLabel: "Cancel", form: true, resolve };
    if (open) open(request);
    else queue.push(request);
  });
}

export function ConfirmHost() {
  const [request, setRequest] = useState(null);
  const [values, setValues] = useState({});
  const [missing, setMissing] = useState([]);

  useEffect(() => {
    if (!request?.form) return;
    setValues(Object.fromEntries(request.fields.map((f) => [f.name, f.defaultValue ?? ""])));
    setMissing([]);
  }, [request]);

  useEffect(() => {
    open = (req) => setRequest((cur) => {
      if (cur) { queue.push(req); return cur; }
      return req;
    });
    if (queue.length) setRequest(queue.shift());
    return () => { open = null; };
  }, []);

  const finish = (value) => {
    // the action click and the dialog's close event both arrive; settle once
    if (!request || request.settled) return;
    request.settled = true;
    if (request.form) {
      const clean = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, typeof v === "string" ? v.trim() : v]));
      request.resolve(value ? clean : null);
    } else {
      request.resolve(value);
    }
    setRequest(queue.length ? queue.shift() : null);
  };

  return (
    <AlertDialog open={Boolean(request)} onOpenChange={(isOpen) => { if (!isOpen) finish(false); }}>
      {request && (
        <AlertDialogContent className="max-w-md" data-testid="confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display text-xl leading-snug">{request.title}</AlertDialogTitle>
            {request.body ? (
              <AlertDialogDescription className="whitespace-pre-line text-sm text-[var(--ink-2)]">{request.body}</AlertDialogDescription>
            ) : (
              <AlertDialogDescription className="sr-only">Please confirm this action.</AlertDialogDescription>
            )}
          </AlertDialogHeader>
          {request.form && (
            <div className="space-y-3" data-testid="form-dialog">
              {request.fields.map((f, i) => {
                const Tag = f.multiline ? "textarea" : "input";
                const bad = missing.includes(f.name);
                return (
                  <label key={f.name} className="block text-xs font-semibold text-[var(--ink-2)]">
                    {f.label}{f.required && <span className="text-[var(--danger)]"> *</span>}
                    {f.options ? (
                      <select autoFocus={i === 0} className={`input-flat mt-1 w-full font-normal ${bad ? "!border-[var(--danger)]" : ""}`}
                              value={values[f.name] ?? ""}
                              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                              data-testid={`form-field-${f.name}`}>
                        {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    ) : (
                      <Tag autoFocus={i === 0} type={f.multiline ? undefined : (f.type || "text")} rows={f.multiline ? 3 : undefined}
                           className={`input-flat mt-1 w-full font-normal ${bad ? "!border-[var(--danger)]" : ""}`}
                           placeholder={f.placeholder} value={values[f.name] ?? ""}
                           onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                           data-testid={`form-field-${f.name}`} />
                    )}
                    {f.hint && <span className="block mt-1 font-normal text-[var(--ink-3)]">{f.hint}</span>}
                    {bad && <span className="block mt-1 font-normal text-[var(--danger)]">Required</span>}
                  </label>
                );
              })}
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => finish(false)} data-testid="confirm-cancel">{request.cancelLabel || "Cancel"}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                if (request.form) {
                  const need = request.fields.filter((f) => f.required && !String(values[f.name] ?? "").trim()).map((f) => f.name);
                  if (need.length) { e.preventDefault(); setMissing(need); return; }
                }
                finish(true);
              }}
              className={request.danger ? "bg-[var(--danger)] hover:bg-[#8F1F18] text-white" : ""}
              data-testid="confirm-ok">
              {request.confirmLabel || "Continue"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}
