import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import {
  MagnifyingGlass, Briefcase, UserCircle, UsersThree, Kanban, HardHat,
  Receipt, IdentificationCard, Package, ArrowRight, Plus, Coins,
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
      <div className="w-full max-w-xl bg-white border border-[#0A0A0A] shadow-2xl" data-testid="command-palette">
        {/* input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#E5E5E5]">
          <MagnifyingGlass size={16} className="text-[#5C5C5C]" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Search projects, clients, invoices, expenses, amounts…"
            className="flex-1 outline-none text-sm placeholder-[#9A9A9A] bg-transparent"
            data-testid="command-palette-input"
          />
          <kbd className="px-1.5 py-0.5 bg-[#FAFAFA] border border-[#E5E5E5] font-mono text-[10px] text-[#5C5C5C]">ESC</kbd>
        </div>

        {/* results */}
        <div className="max-h-[420px] overflow-y-auto">
          {loading && (
            <div className="px-4 py-3 text-xs font-mono uppercase tracking-wider text-[#9A9A9A]">Searching…</div>
          )}
          {!loading && q.trim().length >= 2 && results.length === 0 && (
            <div className="px-4 py-4 text-sm text-[#5C5C5C]" data-testid="palette-no-results">
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
                      active === idx ? "bg-[#F5F4F0]" : "hover:bg-[#FAFAFA]"
                    }`}
                    data-testid={`palette-result-${r.type}-${r.id}`}
                  >
                    <meta.Icon size={15} className="text-[#5C5C5C] shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{r.title}</div>
                      {r.subtitle && <div className="text-xs text-[#5C5C5C] truncate">{r.subtitle}</div>}
                    </div>
                    <span className="font-mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 bg-[#F5F5F5] text-[#5C5C5C]">
                      {meta.label}
                    </span>
                    {active === idx && <ArrowRight size={12} className="text-[#8B7F6A]" />}
                  </button>
                );
              })}
            </div>
          )}

          {filteredActions.length > 0 && (
            <div className="py-1 border-t border-[#F0F0F0]">
              <div className="overline px-4 pt-2 pb-1">QUICK ACTIONS</div>
              {filteredActions.map((a, i) => {
                const idx = results.length + i;
                return (
                  <button
                    key={a.id}
                    onClick={() => go(a)}
                    onMouseEnter={() => setActive(idx)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition ${
                      active === idx ? "bg-[#F5F4F0]" : "hover:bg-[#FAFAFA]"
                    }`}
                    data-testid={`palette-action-${a.id}`}
                  >
                    <Plus size={14} className="text-[#8B7F6A] shrink-0" />
                    <div className="flex-1">
                      <span className="text-sm font-semibold">{a.label}</span>
                      <span className="text-xs text-[#9A9A9A] ml-2">{a.hint}</span>
                    </div>
                    {active === idx && <ArrowRight size={12} className="text-[#8B7F6A]" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-[#E5E5E5] flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-[#9A9A9A]">
          <span>↑↓ Navigate</span><span>↵ Open</span><span>ESC Close</span>
        </div>
      </div>
    </div>
  );
}
