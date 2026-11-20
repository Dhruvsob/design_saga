import { useEffect, useRef } from "react";

// GOV.UK-style error summary: on a failed save, one box at the top of the form
// lists every problem, takes focus (screen readers announce it), and each
// entry jumps to its field. What the person typed stays in the form.
export default function ErrorSummary({ items, formRef, labels = {} }) {
  const ref = useRef(null);
  // labels: a map { field: "Label" } or a function field => label (for lines).
  const labelFor = typeof labels === "function" ? labels : (field) => labels[field];
  useEffect(() => {
    if (items?.length) ref.current?.focus();
  }, [items]);
  if (!items?.length) return null;
  const go = (field) => (event) => {
    event.preventDefault();
    const el = formRef?.current?.querySelector(`[name="${field}"]`);
    if (el) {
      el.focus();
      el.scrollIntoView?.({ block: "center" });
    }
  };
  return (
    <div ref={ref} tabIndex={-1} role="alert" aria-labelledby="error-summary-title" data-testid="error-summary"
         className="col-span-full border-2 border-[var(--danger)] bg-[var(--danger-soft)] p-3 focus:outline-none focus:ring-2 focus:ring-[var(--danger)]">
      <h3 id="error-summary-title" className="font-semibold text-[var(--danger)]">There is a problem</h3>
      <ul className="mt-1 list-disc pl-5 text-sm text-[var(--danger)]">
        {items.map((it, i) => (
          <li key={`${it.field || "form"}-${i}`}>
            {it.field && labelFor(it.field)
              ? <a href={`#${it.field}`} onClick={go(it.field)} className="underline underline-offset-2">{labelFor(it.field)}: {it.text}</a>
              : it.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
