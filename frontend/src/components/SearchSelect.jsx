import { useMemo, useRef, useState } from "react";
import { readOptions } from "../lib/selectOptions";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { CaretDown, Check } from "@phosphor-icons/react";

const SEARCH_THRESHOLD = 7;

/**
 * Drop-in searchable replacement for a native <select> over long lists
 * (clients, projects, vendors, employees, accounts). Accepts the same
 * <option> children and calls onChange({ target: { value, name } }) so
 * existing handlers keep working unchanged.
 */
export default function SearchSelect({
  value, onChange, children, className = "", required = false, disabled = false,
  name, id, title, placeholder, "aria-label": ariaLabel, "data-testid": testId,
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const options = useMemo(() => readOptions(children), [children]);
  const current = String(value ?? "");
  const selected = options.find((o) => o.value === current);
  const emptyOption = options.find((o) => o.value === "");
  const label = selected && selected.value !== "" ? selected.label
    : (placeholder || emptyOption?.label || "Select…");
  const groups = useMemo(() => {
    const map = new Map();
    options.forEach((o) => {
      if (!map.has(o.group)) map.set(o.group, []);
      map.get(o.group).push(o);
    });
    return [...map.entries()];
  }, [options]);

  const choose = (option) => {
    setOpen(false);
    if (option.value !== current) onChange?.({ target: { value: option.value, name }, currentTarget: { value: option.value, name } });
    triggerRef.current?.focus();
  };

  return (
    <div className="relative min-w-0">
      <Popover open={open} onOpenChange={(next) => !disabled && setOpen(next)}>
        <PopoverTrigger asChild>
          <button
            ref={triggerRef}
            type="button"
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-label={ariaLabel || title || placeholder || emptyOption?.label}
            aria-required={required || undefined}
            title={title}
            disabled={disabled}
            data-testid={testId}
            data-value={current}
            onKeyDown={(e) => { if (e.key === "ArrowDown" && !open) { e.preventDefault(); setOpen(true); } }}
            className={`${className} flex items-center justify-between gap-2 text-left w-full ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
          >
            <span className={`truncate ${selected && selected.value !== "" ? "" : "text-[#9B9B9B]"}`}>{label}</span>
            <CaretDown size={12} aria-hidden="true" className="shrink-0 text-[#9B9B9B]" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="p-0 z-[80]"
                        style={{ width: "max(var(--radix-popover-trigger-width), 240px)" }}>
          <Command loop>
            {options.length > SEARCH_THRESHOLD && (
              <CommandInput placeholder="Type to search…" className="!border-0 !shadow-none !ring-0 !outline-none bg-transparent" data-testid={testId ? `${testId}-search` : undefined} />
            )}
            <CommandList className="max-h-72">
              <CommandEmpty>No matches</CommandEmpty>
              {groups.map(([group, items]) => (
                <CommandGroup key={group || "_"} heading={group || undefined}>
                  {items.map((o) => (
                    <CommandItem
                      key={o.value || "__empty__"}
                      value={`${o.label} ${o.value}`}
                      keywords={[o.label]}
                      disabled={o.disabled}
                      onSelect={() => choose(o)}
                      className={o.value === "" ? "text-[#9B9B9B]" : ""}
                    >
                      <Check size={12} aria-hidden="true"
                             className={`mr-2 shrink-0 ${o.value === current ? "opacity-100" : "opacity-0"}`} />
                      <span className="truncate">{o.label || "—"}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {/* Keeps native form validation for required selects. */}
      <input
        tabIndex={-1}
        aria-hidden="true"
        name={name}
        required={required}
        value={current}
        onChange={() => {}}
        onFocus={() => triggerRef.current?.focus()}
        className="absolute inset-x-0 bottom-0 h-px opacity-0 pointer-events-none"
      />
    </div>
  );
}
