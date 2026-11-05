import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  SquaresFour, UsersThree, Briefcase, Kanban, Receipt, UserCircle,
  Files as FilesIcon, SignOut, MagnifyingGlass, Bell, CaretRight, ShieldCheck,
  IdentificationCard, Clock, Bank, HardHat, Buildings, Palette, Crown, CreditCard, CalendarCheck,
  Package, Wallet, List, X, CalendarBlank, ArrowsOut, ArrowsIn,
  Scroll, LockKey,
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

function NavItem({ to, label, Icon }) {
  return (
    <NavLink
      to={to}
      data-testid={`nav-${to.replace("/", "")}`}
      className={({ isActive }) =>
        `group flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-all relative ${
          isActive
            ? "bg-[#F3EFE9] text-[#1A1A1A] font-semibold"
            : "text-[#6B6B6B] hover:bg-black/[0.04] hover:text-[#1A1A1A]"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <div className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-[#8B7F6A]" />}
          <Icon size={17} aria-hidden="true" weight={isActive ? "fill" : "regular"} className={isActive ? "text-[#76705E]" : "text-[#9B9B9B] group-hover:text-[#6B6B6B]"} />
          <span className="flex-1">{label}</span>
          {isActive && <CaretRight size={12} weight="bold" aria-hidden="true" className="text-[#76705E]" />}
        </>
      )}
    </NavLink>
  );
}

const fmtClock = (d) => formatTime(d);

export default function Layout({ children }) {
  const { user, logout, hasPerm, currentOrg, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [now, setNow] = useState(new Date());
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pinSettingsOpen, setPinSettingsOpen] = useState(false);

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
        className={`w-64 shrink-0 flex flex-col text-[#6B6B6B] z-40
          fixed inset-y-0 left-0 h-full overflow-y-auto transform transition-transform duration-200
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0 lg:sticky lg:top-0 lg:min-h-screen lg:h-auto`}
        style={{ background: "var(--sidebar)", borderRight: "1px solid #E8E6E1" }}
        data-testid="app-sidebar"
      >
        <button
          onClick={() => navigate(isSuperAdmin ? "/super-admin" : "/dashboard")}
          className="p-6 flex items-center gap-3 text-left hover:bg-black/[0.03] transition group"
          style={{ borderBottom: "1px solid #E8E6E1" }}
          data-testid="sidebar-logo-btn"
        >
          {brandLogo ? (
            <img src={brandLogo} alt={brandName}
                 className="w-10 h-10 object-contain rounded-xl ring-1 ring-[#E8E6E1] bg-white transition-transform group-hover:scale-105" />
          ) : (
            <div className="relative w-10 h-10 rounded-xl flex items-center justify-center transition-transform group-hover:scale-105 shadow-sm"
                 style={{ background: "linear-gradient(135deg, #8B7F6A, #8a6f24)" }}>
              <span className="text-white font-display font-bold text-base">{brandInitials}</span>
              <div className="absolute -top-1 -right-1 w-2 h-2 bg-[#C9A84C] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
            </div>
          )}
          <div className="min-w-0">
            <div className="font-display font-bold tracking-tight text-base text-[#1A1A1A] truncate" data-testid="sidebar-brand-name">
              {brandName}<span className="text-[#76705E]">.</span>
            </div>
            <div className="eyebrow text-[9px] text-[#9B9B9B] truncate mt-0.5">{brandTagline}</div>
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

        <nav className="flex-1 p-3" aria-label="Main">
          {isSuperAdmin && (
            <NavLink
              to="/super-admin"
              data-testid="nav-super-admin"
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg transition-all relative mb-1 ${
                  isActive
                    ? "bg-[#C9A84C]/15 text-[#8a6f24] font-semibold"
                    : "text-[#6B6B6B] hover:bg-black/[0.04] hover:text-[#1A1A1A]"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <div className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-[#C9A84C]" />}
                  <Crown size={17} aria-hidden="true" weight={isActive ? "fill" : "regular"} />
                  <span className="flex-1">Super Admin</span>
                  {isActive && <CaretRight size={12} weight="bold" aria-hidden="true" />}
                </>
              )}
            </NavLink>
          )}
          {groups.map((g) => (
            <div key={g.id} className={g.label ? "mt-4" : ""} role="group" aria-labelledby={g.label ? `nav-group-${g.id}` : undefined}>
              {g.label && (
                <div id={`nav-group-${g.id}`} className="overline px-3 pb-1.5 text-[#A8A296]" data-testid={`nav-group-${g.id}`}>
                  {g.label}
                </div>
              )}
              <div className="space-y-0.5">
                {g.items.map((item) => <NavItem key={item.to} {...item} />)}
              </div>
            </div>
          ))}
        </nav>

        <div className="p-4" style={{ borderTop: "1px solid #E8E6E1" }}>
          <div className="flex items-center gap-3 mb-3">
            {user?.picture ? (
              <img src={user.picture} alt="" className="w-9 h-9 rounded-lg object-cover ring-1 ring-[#E8E6E1]" />
            ) : (
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-display font-bold text-xs" style={{ background: "var(--stone)" }}>
                {(user?.name || "?").slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-[#1A1A1A] truncate" data-testid="sidebar-user-name">{user?.name}</div>
              <div className="text-[10px] font-mono tracking-wider uppercase text-[#9B9B9B] flex items-center gap-1.5">
                <span className="live-dot" />
                {user?.role || "employee"}
              </div>
            </div>
          </div>
          <button
            onClick={() => setPinSettingsOpen(true)}
            data-testid="sidebar-app-lock-btn"
            className="w-full flex items-center justify-center gap-2 text-xs font-semibold py-2.5 mb-2 rounded-xl border border-[#E8E6E1] bg-white text-[#6B6B6B] hover:text-[#1A1A1A] hover:border-[#8B7F6A] transition"
          >
            <LockKey size={14} /> {user?.app_pin_enabled ? "App lock" : "Set app PIN"}
          </button>
          <button
            onClick={logout}
            data-testid="sidebar-logout-btn"
            className="w-full flex items-center justify-center gap-2 text-xs font-semibold py-2.5 rounded-xl border border-[#E8E6E1] bg-white text-[#6B6B6B] hover:text-[#1A1A1A] hover:border-[#8B7F6A] transition"
          >
            <SignOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      {pinSettingsOpen && <PinSecurityDialog onClose={() => setPinSettingsOpen(false)} />}

      {/* ============== MAIN ============== */}
      <main className="flex-1 min-w-0">
        {/* Top brand accent strip */}
        <div className="h-[3px] bg-gradient-to-r from-[#8B7F6A] via-[#C9A84C] to-[#8B7F6A] no-print" />

        <header className="h-16 px-4 lg:px-8 flex items-center justify-between sticky top-0 z-20 no-print glass-header">
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
          <nav aria-label="Breadcrumb" className="hidden md:flex items-center gap-3 text-sm text-[#6B6B6B]" data-testid="breadcrumb">
            <span className="overline">{(brandName || "").toUpperCase()}</span>
            {currentGroup?.label && (
              <>
                <CaretRight size={10} className="text-[#9B9B9B]" aria-hidden="true" />
                <span>{currentGroup.label}</span>
              </>
            )}
            <CaretRight size={10} className="text-[#9B9B9B]" aria-hidden="true" />
            <span className="text-[#2C2C2C] font-semibold" aria-current="page">{currentNav?.label || "Page"}</span>
          </nav>

          {/* search — opens the command palette */}
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-2 flex-1 max-w-md mx-2 lg:mx-8 px-3 py-2 rounded-xl border border-transparent hover:border-[#E8E6E1] hover:bg-white transition text-left"
            data-testid="top-search"
          >
            <MagnifyingGlass size={15} className="text-[#6B6B6B]" />
            <span className="flex-1 text-sm text-[#9B9B9B]">Search projects, clients, invoices…</span>
            <kbd className="hidden md:inline-block px-1.5 py-0.5 rounded bg-[#F5F4F0] border border-[#E8E6E1] font-mono text-[10px] text-[#6B6B6B]">⌘K</kbd>
          </button>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 overline">
              <span className="live-dot" />
              <span>{formatDate(now)} · {fmtClock(now)} IST</span>
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
          </div>
        </header>

        <div className="p-4 lg:p-8 fade-in">{children}</div>
      </main>

      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />
      <CalendarReminders />
    </div>
  );
}
