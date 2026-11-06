/**
 * Page header used by every top-level page.
 * The header breadcrumb already shows the section, so this shows the page
 * name, an optional count, one line of context and the page's actions.
 */
export default function PageHero({
  eyebrow,
  title,
  kicker,
  children,        // action buttons / right-side content
  count,           // optional record count
  testid,
}) {
  // Section paths ("FINANCE / ACCOUNTING") duplicate the breadcrumb; other
  // eyebrows (e.g. a task's status line) are real context and stay.
  const context = eyebrow && !/^[A-Z &]+ \/ [A-Z &]+$/.test(String(eyebrow).trim()) ? eyebrow : null;
  return (
    <div className="fade-in flex items-end justify-between flex-wrap gap-x-6 gap-y-3 pb-5 border-b border-[var(--line)]"
         data-testid={testid}>
      <div className="min-w-0">
        {context && <div className="text-xs font-medium text-[var(--ink-3)] mb-1.5">{context}</div>}
        <div className="flex items-center gap-2.5 flex-wrap">
          <h1 className="font-display font-bold text-[26px] sm:text-[28px] leading-tight tracking-tight text-[var(--ink)]">
            {title}
          </h1>
          {typeof count === "number" && (
            <span className="text-xs font-semibold text-[var(--ink-2)] bg-[var(--hover)] border border-[var(--line)] rounded-full px-2 py-0.5 tabular">
              {count}
            </span>
          )}
        </div>
        {kicker && <p className="text-[var(--ink-3)] mt-1 max-w-2xl text-sm">{kicker}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2 max-w-full">{children}</div>
    </div>
  );
}
