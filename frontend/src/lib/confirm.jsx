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

export function ConfirmHost() {
  const [request, setRequest] = useState(null);

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
    request.resolve(value);
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
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => finish(false)} data-testid="confirm-cancel">{request.cancelLabel || "Cancel"}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => finish(true)}
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
