/**
 * Global double-submit guard (UX-05).
 *
 * While a form's save request is in flight, a second submit of the same form
 * is swallowed before React sees it, and the form's submit buttons are
 * disabled and marked busy. Released when the API reports no pending write
 * requests (or after a short grace period when the handler sent none, e.g. a
 * client-side validation message). Opt out with `data-allow-resubmit`.
 */
const GRACE_MS = 400;
const SAFETY_MS = 30_000;

export function installSubmitGuard(doc, { pendingWrites, onWritesIdle }) {
  if (!doc || doc.__submitGuardInstalled) return;
  doc.__submitGuardInstalled = true;

  doc.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form || form.tagName !== "FORM" || form.hasAttribute("data-allow-resubmit")) return;
    if (form.dataset.submitting === "1") {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    form.dataset.submitting = "1";
    form.setAttribute("aria-busy", "true");
    const buttons = [...form.querySelectorAll('button[type="submit"], button:not([type])')]
      .filter((button) => !button.disabled);
    buttons.forEach((button) => { button.disabled = true; button.dataset.guardDisabled = "1"; });

    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      delete form.dataset.submitting;
      form.removeAttribute("aria-busy");
      buttons.forEach((button) => {
        if (button.dataset.guardDisabled === "1") {
          button.disabled = false;
          delete button.dataset.guardDisabled;
        }
      });
    };
    setTimeout(() => {
      if (pendingWrites() === 0) release();
      else onWritesIdle(release);
    }, GRACE_MS);
    setTimeout(release, SAFETY_MS);
  }, true);
}
