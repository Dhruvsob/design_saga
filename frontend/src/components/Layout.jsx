import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  SquaresFour, UsersThree, Briefcase, Kanban, Receipt, UserCircle,
  Files as FilesIcon, SignOut, MagnifyingGlass, Bell, CaretRight, ShieldCheck,
  IdentificationCard, Clock, Bank, HardHat, Buildings, Palette, Crown, CreditCard, CalendarCheck,
  Package, Wallet, List, X, CalendarBlank, ArrowsOut, ArrowsIn,
  Scroll, LockKey, CaretDoubleLeft, CaretDoubleRight,
} from "@phosphor-icons/react";
import NotificationBell from "./NotificationBell";
import CommandPalette from "./CommandPalette";
import CalendarReminders from "./CalendarReminders";
import { useEffect, useState } from "react";
import { formatDate, formatTime } from "../lib/format";
import { PinSecurityDialog } from "./AppPinLock";
import { visibleNavGroups } from "../lib/navigation";

// Grouped by how an architecture practice works, not by backend module.
// URLs, permissions and module flags are unchanged; empty groups are hidden.
const NAV_GROUPS = [
  { id: "home", label: null, items: [
    { to: "/dashboard",   label: "Dashboard",    perm: "dashboard.read", Icon: SquaresFour },
  ] },
  { id: "sales", label: "Sales", items: [
    { to: "/crm",         label: "Leads",        perm: "leads.read",     Icon: UsersThree, module: "crm" },
    { to: "/clients",     label: "Clients",      perm: "clients.read",   Icon: UserCircle, module: "clients" },
    { to: "/quotations",  label: "Quotations",   perm: "quotations.read", Icon: FilesIcon, module: "quotations" },
  ] },
  { id: "projects", label: "Projects", items: [
    { to: "/projects",    label: "Projects",     perm: "projects.read",  Icon: Briefcase, module: "projects" },
    { to: "/tasks",       label: "Tasks",        perm: "tasks.read",     Icon: Kanban, module: "tasks" },
    { to: "/calendar",    label: "Calendar",     perm: "calendar.read",  Icon: CalendarBlank },
  ] },
  { id: "procurement", label: "Procurement", items: [
    { to: "/vendors",     label: "Vendors",      perm: "vendors.read",   Icon: HardHat },
    { to: "/purchase-orders", label: "Purchase Orders", perm: "purchase_orders.read", Icon: Package, module: "purchase_orders" },
  ] },
  { id: "finance", label: "Finance", items: [
    { to: "/invoices",    label: "Invoices",     perm: "invoices.read",  Icon: Receipt, module: "invoices" },
    { to: "/accounting",  label: "Accounting",   perm: "finance.read",   Icon: Bank, module: "accounting" },
    { to: "/expenses",    label: "Expenses",     perm: "expenses.read",  Icon: Wallet, module: "expenses" },
    { to: "/loans",       label: "Loans & EMI",  perm: "loans.read",     Icon: CreditCard, module: "loans" },
  ] },
  { id: "people", label: "People", items: [
    { to: "/employees",   label: "Employees",    perm: "employees.read", Icon: IdentificationCard, module: "employees" },
    { to: "/attendance",  label: "Attendance",   perm: "attendance.read", Icon: Clock, module: "attendance" },
    { to: "/holidays",    label: "Holidays",     perm: "holidays.read",  Icon: CalendarCheck, module: "attendance" },
  ] },
  { id: "admin", label: "Administration", items: [
    { to: "/settings/company", label: "Company",  perm: "*.*",           Icon: Palette },
    { to: "/admin/rbac",  label: "Team & Roles", perm: "users.read",     Icon: ShieldCheck },
    { to: "/settings/audit", label: "Audit Log", perm: "*.*",            Icon: Scroll },
  ] },
];

function NavItem({ to, label, Icon, rail }) {
  return (
    <NavLink
      to={to}
      title={rail ? label : undefined}
      aria-label={rail ? label : undefined}
      data-testid={`nav-${to.replace("/", "")}`}
      className={({ isActive }) =>
        `group relative flex items-center gap-3 h-9 rounded-lg text-[13.5px] transition-colors duration-150 ${
          rail ? "justify-center px-0" : "px-3"
        } ${
          isActive
            ? "bg-[var(--surface)] text-[var(--ink)] font-semibold"
            : "text-[var(--ink-2)] hover:bg-[var(--sidebar-2)] hover:text-[var(--ink)]"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="nav-active-bar" aria-hidden="true" />}
          <Icon size={18} aria-hidden="true" weight={isActive ? "fill" : "regular"}
                className={`shrink-0 transition-colors ${isActive ? "text-[var(--accent-strong)]" : "text-[var(--ink-3)] group-hover:text-[var(--ink-2)]"}`} />
          {!rail && <span className="flex-1 truncate">{label}</span>}
        </>
      )}
    </NavLink>
  );
}

function readPref(key, fallback) {
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
}
function writePref(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

const fmtClock = (d) => formatTime(d);

export default function Layout({ children }) {
  const { user, logout, hasPerm, currentOrg, isSuperAdmin, lockNow } = useAuth();
  const pinEnabled = Boolean(user?.app_pin_enabled);
  const subState = currentOrg?.subscription_state;
  const lockApp = () => (pinEnabled ? lockNow() : setPinSettingsOpen(true));
  useEffect(() => {
    // Ctrl/Cmd + Shift + L locks the app from anywhere
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "L" || e.key === "l") && pinEnabled) {
        e.preventDefault();
        lockNow();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pinEnabled, lockNow]);
  const navigate = useNavigate();
  const location = useLocation();
  const [now, setNow] = useState(new Date());
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pinSettingsOpen, setPinSettingsOpen] = useState(false);
  const [rail, setRail] = useState(() => readPref("ds_sidebar_rail", false));
  const toggleRail = () => setRail((r) => { writePref("ds_sidebar_rail", !r); return !r; });

  // Close the mobile drawer on route change
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(t);
  }, []);

  // Track browser full-screen state so the icon reflects reality (Esc, F11 etc.)
  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = () => {
    try {
      if (document.fullscreenElement) {
        document.exitFullscreen?.();
      } else {
        document.documentElement.requestFullscreen?.();
      }
    } catch { /* fullscreen not supported — no-op */ }
  };

  // Filter nav by permission + module feature flag. Admin links follow the
  // same permissions the backend enforces rather than the role's name.
  const enabledModules = currentOrg?.features?.modules || {};
  const groups = visibleNavGroups(NAV_GROUPS, hasPerm, enabledModules);
  let currentNav = null;
  let currentGroup = null;
  for (const g of groups) {
    const hit = g.items.find((n) => location.pathname.startsWith(n.to));
    if (hit) { currentNav = hit; currentGroup = g; break; }
  }
  const brandName = currentOrg?.display_name || currentOrg?.name || "DESIGN SAGA";
  const brandTagline = currentOrg?.branding?.tagline || "STUDIO MANAGEMENT";
  const brandColor = currentOrg?.branding?.primary_color || "#8B7F6A";
  const brandLogo = currentOrg?.branding?.logo_url;
  const brandInitials = (brandName || "DS").split(/\s+/).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase().slice(0, 2);

  return (
    <div className="min-h-screen flex" style={{ background: "var(--app)" }}>
      {/* mobile backdrop */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/30 z-30 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}
      {/* ============== SIDEBAR ============== */}
      <aside
        className={`sidebar-taupe shrink-0 flex flex-col text-[var(--ink-2)] z-40 w-64 ${rail ? "lg:w-[76px]" : "lg:w-64"}
          fixed inset-y-0 left-0 h-full transform transition-[transform,width] duration-200 ease-out
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0 lg:sticky lg:top-0 lg:h-screen`}
        style={{ borderRight: "1px solid var(--line)" }}
        data-testid="app-sidebar"
      >
        {/* brand */}
        <button
          onClick={() => navigate(isSuperAdmin ? "/super-admin" : "/dashboard")}
          className={`flex items-center gap-3 text-left hover:bg-[var(--sidebar-2)] transition-colors group shrink-0 ${rail ? "lg:justify-center lg:px-0 px-4 py-4" : "px-4 py-4 pr-14 lg:pr-4"}`}
          style={{ borderBottom: "1px solid var(--line)" }}
          title={rail ? brandName : undefined}
          data-testid="sidebar-logo-btn"
        >
          {brandLogo ? (
            <span className="h-12 min-w-[48px] max-w-[64px] px-1.5 rounded-xl bg-[#FAF9F6] flex items-center justify-center shrink-0 shadow-sm">
              <img src={brandLogo} alt="" aria-hidden="true" data-testid="sidebar-logo"
                   className="h-10 w-auto max-w-[56px] object-contain transition-transform duration-200 group-hover:scale-[1.04]" />
            </span>
          ) : (
            <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 bg-[#FAF9F6] shadow-sm">
              <span className="text-[var(--logo-brown-ink)] font-display font-bold text-[20px] leading-none">{brandInitials}</span>
            </div>
          )}
          <div className={`min-w-0 ${rail ? "lg:hidden" : ""}`}>
            <div className="font-display font-bold text-[17px] leading-tight text-[var(--ink)] truncate" data-testid="sidebar-brand-name">
              {brandName}
            </div>
            <div className="text-[10.5px] uppercase tracking-[0.14em] text-[var(--ink-3)] truncate mt-0.5">{brandTagline}</div>
          </div>
        </button>

        <button
          type="button"
          className="lg:hidden absolute top-3 right-3 btn-icon"
          onClick={() => setMobileOpen(false)}
          aria-label="Close menu"
          data-testid="mobile-menu-close"
        >
          <X size={18} />
        </button>

        {/* menu: the only part that scrolls */}
        <nav className={`flex-1 overflow-y-auto overscroll-contain py-3 ${rail ? "lg:px-2 px-3" : "px-3"}`} aria-label="Main">
          {isSuperAdmin && (
            <div className="mb-2">
              <NavItem to="/super-admin" label="Super Admin" Icon={Crown} rail={rail} />
            </div>
          )}
          {groups.map((g) => {
            return (
              <div key={g.id} className={g.label ? "mt-3" : ""} role="group" aria-labelledby={g.label ? `nav-group-${g.id}` : undefined}>
                {g.label && (rail ? (
                  <div className="hidden lg:block mx-3 my-2 border-t border-[var(--line)]" aria-hidden="true" />
                ) : null)}
                {g.label && (
                  <div id={`nav-group-${g.id}`}
                       className={`px-3 pt-1 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-3)] ${rail ? "lg:hidden" : ""}`}
                       data-testid={`nav-group-${g.id}`}>
                    {g.label}
                  </div>
                )}
                <div className="space-y-0.5">
                  {g.items.map((item) => <NavItem key={item.to} {...item} rail={rail} />)}
                </div>
              </div>
            );
          })}
        </nav>

        {/* profile + controls */}
        <div className="shrink-0 p-3 space-y-1" style={{ borderTop: "1px solid var(--line)" }}>
          <div className={`flex items-center gap-2.5 rounded-lg p-1.5 ${rail ? "lg:flex-col lg:gap-1.5" : ""}`}>
            {user?.picture ? (
              <img src={user.picture} alt="" className="w-9 h-9 rounded-lg object-cover ring-1 ring-[var(--line)] shrink-0" />
            ) : (
              <div className="w-9 h-9 rounded-lg flex items-center justify-center font-display font-bold text-sm bg-[#FAF9F6] text-[#5F5A4B] shrink-0"
                   title={rail ? user?.name : undefined}>
                {(user?.name || "?").slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className={`min-w-0 flex-1 ${rail ? "lg:hidden" : ""}`}>
              <div className="text-[13px] font-semibold text-[var(--ink)] truncate" data-testid="sidebar-user-name">{user?.name}</div>
              <div className="text-[11px] text-[var(--ink-3)] capitalize truncate">{user?.role || "employee"}</div>
            </div>
            <button type="button" onClick={() => setPinSettingsOpen(true)} className="btn-icon !w-8 !h-8 shrink-0"
                    aria-label="App PIN and security settings" title="App PIN settings"
                    data-testid="sidebar-app-lock-btn">
              <ShieldCheck size={16} />
            </button>
            <button type="button" onClick={logout} className="btn-icon !w-8 !h-8 shrink-0"
                    aria-label="Sign out" title="Sign out" data-testid="sidebar-logout-btn">
              <SignOut size={16} />
            </button>
          </div>
          <button type="button" onClick={toggleRail}
                  className={`hidden lg:flex w-full items-center gap-2 h-8 rounded-lg text-xs text-[var(--ink-3)] hover:bg-[var(--sidebar-2)] hover:text-[var(--ink)] transition-colors ${rail ? "justify-center" : "px-3"}`}
                  aria-label={rail ? "Expand sidebar" : "Collapse sidebar"} title={rail ? "Expand sidebar" : "Collapse sidebar"}
                  data-testid="sidebar-collapse-btn">
            {rail ? <CaretDoubleRight size={14} /> : <><CaretDoubleLeft size={14} /> Collapse</>}
          </button>
        </div>
      </aside>

      {pinSettingsOpen && <PinSecurityDialog onClose={() => setPinSettingsOpen(false)} />}

      {/* ============== MAIN ============== */}
      <main className="flex-1 min-w-0">

        <header className="h-14 px-4 lg:px-8 flex items-center justify-between sticky top-0 z-20 no-print glass-header">
          {/* mobile menu */}
          <button
            className="lg:hidden btn-icon mr-2"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            data-testid="mobile-menu-btn"
          >
            <List size={18} />
          </button>
          {/* breadcrumb */}
          <nav aria-label="Breadcrumb" className="hidden md:flex items-center gap-3 text-sm text-[var(--ink-2)]" data-testid="breadcrumb">
            <NavLink to="/dashboard" className="text-[var(--ink-3)] hover:text-[var(--ink)] hover:underline underline-offset-4" data-testid="crumb-home">{brandName}</NavLink>
            {currentGroup?.label && currentGroup.label !== currentNav?.label && (
              <>
                <CaretRight size={10} className="text-[var(--ink-3)]" aria-hidden="true" />
                <span>{currentGroup.label}</span>
              </>
            )}
            <CaretRight size={10} className="text-[var(--ink-3)]" aria-hidden="true" />
            {currentNav && location.pathname !== currentNav.to ? (
              <>
                {/* on a detail page the list name links back to the list */}
                <NavLink to={currentNav.to} end className="hover:text-[var(--ink)] hover:underline underline-offset-4" data-testid="crumb-list">{currentNav.label}</NavLink>
                <CaretRight size={10} className="text-[var(--ink-3)]" aria-hidden="true" />
                <span className="text-[var(--ink)] font-semibold" aria-current="page">Details</span>
              </>
            ) : (
              <span className="text-[var(--ink)] font-semibold" aria-current="page">{currentNav?.label || "Page"}</span>
            )}
          </nav>

          {/* search — opens the command palette */}
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-2 flex-1 max-w-md mx-2 lg:mx-8 px-3 h-9 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] hover:bg-white hover:border-[var(--line-strong)] transition-colors text-left"
            data-testid="top-search"
          >
            <MagnifyingGlass size={15} className="text-[var(--ink-2)]" />
            <span className="flex-1 text-sm text-[var(--ink-3)]">Search projects, clients, invoices…</span>
            <kbd className="hidden md:inline-block px-1.5 py-0.5 rounded bg-[var(--hover)] border border-[var(--line)] font-mono text-[10px] text-[var(--ink-2)]">⌘K</kbd>
          </button>

          <div className="flex items-center gap-3">
            <div className="hidden xl:block text-xs text-[var(--ink-3)] tabular whitespace-nowrap">
              {formatDate(now)} · {fmtClock(now)}
            </div>
            <button
              onClick={toggleFullscreen}
              className="btn-icon"
              aria-label={isFullscreen ? "Exit full screen" : "Enter full screen"}
              title={isFullscreen ? "Exit full screen" : "Full screen"}
              data-testid="fullscreen-toggle"
            >
              {isFullscreen ? <ArrowsIn size={18} /> : <ArrowsOut size={18} />}
            </button>
            <NotificationBell />
            <button
              type="button"
              onClick={lockApp}
              className="btn-icon"
              aria-label={pinEnabled ? "Lock the app now" : "Set up app lock"}
              title={pinEnabled ? "Lock now (Ctrl+Shift+L)" : "Set up app lock"}
              data-testid="header-lock-btn"
            >
              <LockKey size={18} weight={pinEnabled ? "regular" : "duotone"} />
            </button>
          </div>
        </header>

        {subState?.read_only && (
          <div role="status" className="px-4 lg:px-8 py-2.5 bg-[var(--danger-soft)] border-b border-[#F1D3CC] text-sm text-[#7A2A1C] flex items-center gap-2 no-print" data-testid="read-only-banner">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--danger)] shrink-0" />
            <span><strong>Read-only mode.</strong> {subState.ended_on ? `The plan ended on ${formatDate(subState.ended_on)}. ` : ""}Your work is preserved and can be viewed or downloaded, but editing is paused until the studio owner renews the plan.</span>
          </div>
        )}
        {!subState?.read_only && subState?.status === "trial" && subState?.days_left != null && subState.days_left <= 7 && (
          <div role="status" className="px-4 lg:px-8 py-2 bg-[var(--warning-soft)] border-b border-[#F3E2C2] text-xs text-[var(--warning)] no-print" data-testid="trial-banner">
            Trial ends {subState.days_left === 0 ? "today" : `in ${subState.days_left} day${subState.days_left === 1 ? "" : "s"}`} ({formatDate(subState.trial_ends_on)}). Your data stays safe; editing pauses when it ends.
          </div>
        )}
        <div className="p-4 lg:p-8 fade-in">{children}</div>
      </main>

      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />
      <CalendarReminders />
    </div>
  );
}
