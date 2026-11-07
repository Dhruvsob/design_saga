import { useEffect, useMemo, useState } from "react";
import { CaretLeft, CaretRight } from "@phosphor-icons/react";

/**
 * Page a list on screen so long tables stay fast.
 *
 *   const { pageRows, pager } = usePaged(filtered, { key: "invoices" });
 *   ...rows: pageRows.map(...)
 *   {pager}
 *
 * Goes back to page 1 whenever the list changes length (new filter/search).
 */
export function usePaged(rows, { size = 50, key } = {}) {
  const list = Array.isArray(rows) ? rows : [];
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(list.length / size));
  useEffect(() => { setPage(1); }, [list.length]);
  const current = Math.min(page, pages);
  const pageRows = useMemo(
    () => list.slice((current - 1) * size, current * size),
    [list, current, size],
  );
  const pager = <Pager page={current} pages={pages} total={list.length} size={size} onPage={setPage} testid={key ? `pager-${key}` : "pager"} />;
  return { pageRows, pager, page: current, pages };
}

export default function Pager({ page, pages, total, size, onPage, testid = "pager" }) {
  if (total <= size) return null;
  const from = (page - 1) * size + 1;
  const to = Math.min(total, page * size);
  return (
    <nav className="flex items-center justify-between gap-3 px-3 py-2.5 text-xs text-[var(--ink-2)] border-t border-[var(--line-soft)]"
         aria-label="Pages" data-testid={testid}>
      <span className="tabular-nums" data-testid={`${testid}-range`}>
        Showing {from.toLocaleString("en-IN")}–{to.toLocaleString("en-IN")} of {total.toLocaleString("en-IN")}
      </span>
      <div className="flex items-center gap-1">
        <button type="button" className="btn-icon !w-8 !h-8" disabled={page <= 1}
                onClick={() => onPage(page - 1)} aria-label="Previous page" data-testid={`${testid}-prev`}>
          <CaretLeft size={14} />
        </button>
        <span className="tabular-nums px-1">Page {page} of {pages}</span>
        <button type="button" className="btn-icon !w-8 !h-8" disabled={page >= pages}
                onClick={() => onPage(page + 1)} aria-label="Next page" data-testid={`${testid}-next`}>
          <CaretRight size={14} />
        </button>
      </div>
    </nav>
  );
}
