import { Plus } from "@phosphor-icons/react";

/**
 * Table placeholders shared by list pages.
 *
 *   {!loaded && <SkeletonRows cols={7} />}
 *   {loaded && rows.length === 0 && <EmptyRow cols={7} title="No vendors yet" hint="..." actionLabel="Add vendor" onAction={open} />}
 *
 * Shows shimmer rows while data loads (instead of a false "nothing here"),
 * and one clear next step when a list is really empty.
 */
export function SkeletonRows({ cols, rows = 5 }) {
  const widths = ["w-24", "w-40", "w-28", "w-20", "w-32", "w-16"];
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className="border-t border-[var(--line-soft)]" data-testid={r === 0 ? "table-loading" : undefined} aria-hidden="true">
          {Array.from({ length: cols }).map((__, c) => (
            <td key={c} className="p-3"><div className={`skeleton h-3 rounded ${widths[(r + c) % widths.length]}`} /></td>
          ))}
        </tr>
      ))}
      <tr className="sr-only"><td colSpan={cols} role="status">Loading…</td></tr>
    </>
  );
}

export function EmptyRow({ cols, icon: Icon, title, hint, actionLabel, onAction, testid = "table-empty" }) {
  return (
    <tr>
      <td colSpan={cols} className="px-6 py-12 text-center" data-testid={testid}>
        {Icon && (
          <div className="mx-auto mb-3 w-11 h-11 rounded-full bg-[var(--surface-2)] flex items-center justify-center">
            <Icon size={22} className="text-[var(--ink-3)]" />
          </div>
        )}
        <div className="font-semibold text-[var(--ink)]">{title}</div>
        {hint && <p className="mt-1 text-sm text-[var(--ink-2)] max-w-md mx-auto">{hint}</p>}
        {actionLabel && onAction && (
          <button type="button" onClick={onAction} className="btn-primary mt-4 inline-flex items-center gap-1.5" data-testid={`${testid}-action`}>
            <Plus size={14} weight="bold" /> {actionLabel}
          </button>
        )}
      </td>
    </tr>
  );
}
