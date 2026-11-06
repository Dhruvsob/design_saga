import { DotsThreeVertical } from "@phosphor-icons/react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "./ui/dropdown-menu";

/**
 * One consistent ⋮ menu for record actions across the ERP.
 *
 *   <RowActions label="Invoice INV-1001" actions={[
 *     { label: "View", icon: Eye, onSelect: open },
 *     { label: "Edit", icon: PencilSimple, onSelect: edit, hidden: !canEdit },
 *     { divider: true },
 *     { label: "Delete", icon: Trash, onSelect: remove, danger: true, hidden: !canDelete },
 *   ]} />
 *
 * Pass only actions the backend supports; hide ones the user may not use.
 * Destructive actions still confirm in their own handler.
 */
export default function RowActions({ actions, label = "record", testid, align = "end" }) {
  const shown = (actions || []).filter((a) => a && !a.hidden);
  // drop leading/trailing/duplicate dividers left after hiding items
  const clean = shown.filter((a, i, arr) => !a.divider
    || (i > 0 && i < arr.length - 1 && !arr[i - 1].divider));
  if (!clean.some((a) => !a.divider)) return null;
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button type="button" className="btn-icon !w-8 !h-8" aria-label={`Actions for ${label}`}
                title="Actions" data-testid={testid} onClick={(e) => e.stopPropagation()}>
          <DotsThreeVertical size={18} weight="bold" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="min-w-[180px] rounded-xl border-[var(--line)] p-1.5 shadow-[var(--shadow-2)]"
                           onClick={(e) => e.stopPropagation()}>
        {clean.map((a, i) => (a.divider ? (
          <DropdownMenuSeparator key={`d${i}`} className="bg-[var(--line)]" />
        ) : (
          <DropdownMenuItem key={a.label}
                            onSelect={() => a.onSelect?.()}
                            disabled={a.disabled}
                            className={`gap-2.5 rounded-lg px-2.5 py-2 text-[13px] cursor-pointer ${a.danger
                              ? "text-[var(--danger)] focus:text-[var(--danger)] focus:bg-[var(--danger-soft)]"
                              : "text-[var(--ink)] focus:bg-[var(--hover)]"}`}
                            data-testid={a.testid}>
            {a.icon && <a.icon size={16} className={a.danger ? "" : "text-[var(--ink-3)]"} />}
            {a.label}
          </DropdownMenuItem>
        )))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
