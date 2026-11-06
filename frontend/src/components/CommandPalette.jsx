import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import {
  MagnifyingGlass, Briefcase, UserCircle, UsersThree, Kanban, HardHat,
  Receipt, IdentificationCard, Package, ArrowRight, Plus, Coins,
  CalendarBlank, FileText,
} from "@phosphor-icons/react";

const TYPE_META = {
  project:        { label: "PROJECT",  Icon: Briefcase },
  client:         { label: "CLIENT",   Icon: UserCircle },
  lead:           { label: "LEAD",     Icon: UsersThree },
  task:           { label: "TASK",     Icon: Kanban },
  vendor:         { label: "VENDOR",   Icon: HardHat },
  invoice:        { label: "INVOICE",  Icon: Receipt },
  employee:       { label: "EMPLOYEE", Icon: IdentificationCard },
  purchase_order: { label: "PO",       Icon: Package },
  transaction:    { label: "TXN",      Icon: Coins },
  quotation:      { label: "QUOTE",    Icon: FileText },
  calendar_event: { label: "EVENT",    Icon: CalendarBlank },
};

const QUICK_ACTIONS = [
  { id: "qa-lead",     label: "New lead",        hint: "CRM pipeline",     route: "/crm" },
  { id: "qa-project",  label: "New project",     hint: "Studio projects",  route: "/projects" },
  { id: "qa-client",   label: "New client",      hint: "Directory",        route: "/clients" },
  { id: "qa-task",     label: "New task",        hint: "Task board",       route: "/tasks" },
  { id: "qa-invoice",  label: "New invoice",     hint: "Billing",          route: "/invoices" },
  { id: "qa-expense",  label: "Submit expense",  hint: "Expense claims",   route: "/expenses" },
  { id: "qa-checkin",  label: "Attendance check-in", hint: "GPS check-in", route: "/attendance" },
  { id: "qa-settings", label: "Company settings", hint: "Control center",  route: "/settings/company" },
];

export default function CommandPalette({ open, setOpen }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);

  // ⌘K / Ctrl+K global shortcut + Esc to close
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  useEffect(() => {
    if (open) {
      setQ(""); setResults([]); setActive(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  // Debounced server search
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.trim().length < 2) { setResults([]); setLoading(false); return; }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/search", { params: { q: q.trim() } });
        setResults(data.results || []);
        setActive(0);
      } catch { setResults([]); }
      finally { setLoading(false); }
    }, 220);
    return () => clearTimeout(debounceRef.current);
  }, [q, open]);

  const filteredActions = q.trim().length
    ? QUICK_ACTIONS.filter((a) => a.label.toLowerCase().includes(q.trim().toLowerCase()))
    : QUICK_ACTIONS;

  const rows = [
    ...results.map((r) => ({ kind: "result", ...r })),
    ...filteredActions.map((a) => ({ kind: "action", ...a })),
  ];

  const go = useCallback((row) => {
    setOpen(false);
    navigate(row.route);
  }, [navigate, setOpen]);

  const onInputKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, rows.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && rows[active]) { e.preventDefault(); go(rows[active]); }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh] bg-black/30"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
      data-testid="command-palette-overlay"
    >
      <div className="w-full max-w-xl bg-white border border-[var(--ink)] shadow-2xl" data-testid="command-palette">
        {/* input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--line)]">
          <MagnifyingGlass size={16} className="text-[var(--ink-2)]" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Search projects, quotations, events, amounts…"
            className="flex-1 outline-none text-sm placeholder-[var(--ink-3)] bg-transparent"
            data-testid="command-palette-input"
          />
          <kbd className="px-1.5 py-0.5 bg-[var(--surface-2)] border border-[var(--line)] font-mono text-[10px] text-[var(--ink-2)]">ESC</kbd>
        </div>

        {/* results */}
        <div className="max-h-[420px] overflow-y-auto">
          {loading && (
            <div className="px-4 py-3 text-xs font-mono uppercase tracking-wider text-[var(--ink-3)]">Searching…</div>
          )}
          {!loading && q.trim().length >= 2 && results.length === 0 && (
            <div className="px-4 py-4 text-sm text-[var(--ink-2)]" data-testid="palette-no-results">
              No records match “{q.trim()}”.
            </div>
          )}

          {results.length > 0 && (
            <div className="py-1">
              <div className="overline px-4 pt-2 pb-1">RECORDS</div>
              {results.map((r, i) => {
                const meta = TYPE_META[r.type] || TYPE_META.project;
                const idx = i;
                return (
                  <button
                    key={`${r.type}-${r.id}`}
                    onClick={() => go(r)}
                    onMouseEnter={() => setActive(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition ${
                      active === idx ? "bg-[var(--hover)]" : "hover:bg-[var(--surface-2)]"
                    }`}
                    data-testid={`palette-result-${r.type}-${r.id}`}
                  >
                    <meta.Icon size={15} className="text-[var(--ink-2)] shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{r.title}</div>
                      {r.subtitle && <div className="text-xs text-[var(--ink-2)] truncate">{r.subtitle}</div>}
                    </div>
                    <span className="font-mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 bg-[var(--hover)] text-[var(--ink-2)]">
                      {meta.label}
                    </span>
                    {active === idx && <ArrowRight size={12} className="text-[var(--accent-strong)]" />}
                  </button>
                );
              })}
            </div>
          )}

          {filteredActions.length > 0 && (
            <div className="py-1 border-t border-[var(--line-soft)]">
              <div className="overline px-4 pt-2 pb-1">QUICK ACTIONS</div>
              {filteredActions.map((a, i) => {
                const idx = results.length + i;
                return (
                  <button
                    key={a.id}
                    onClick={() => go(a)}
                    onMouseEnter={() => setActive(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition ${
                      active === idx ? "bg-[var(--hover)]" : "hover:bg-[var(--surface-2)]"
                    }`}
                    data-testid={`palette-action-${a.id}`}
                  >
                    <Plus size={14} className="text-[var(--accent-strong)] shrink-0" />
                    <div className="flex-1">
                      <span className="text-sm font-semibold">{a.label}</span>
                      <span className="text-xs text-[var(--ink-3)] ml-2">{a.hint}</span>
                    </div>
                    {active === idx && <ArrowRight size={12} className="text-[var(--accent-strong)]" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-[var(--line)] flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-[var(--ink-3)]">
          <span>↑↓ Navigate</span><span>↵ Open</span><span>ESC Close</span>
        </div>
      </div>
    </div>
  );
}
