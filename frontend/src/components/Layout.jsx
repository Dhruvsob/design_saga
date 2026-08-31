import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  SquaresFour, UsersThree, Briefcase, Kanban, Receipt, UserCircle,
  Files as FilesIcon, SignOut, MagnifyingGlass, Bell, CaretRight, ShieldCheck,
  IdentificationCard, Clock, Bank, HardHat, Buildings, Palette, Crown, CreditCard,
  Package, Wallet, List, X, CalendarBlank,
} from "@phosphor-icons/react";
import AIWidget from "./AIWidget";
import NotificationBell from "./NotificationBell";
import CommandPalette from "./CommandPalette";
import { useEffect, useState } from "react";

const NAV = [
  { to: "/dashboard",   label: "Dashboard",    section: "01", perm: "dashboard.read", Icon: SquaresFour },
  { to: "/crm",         label: "Leads / CRM",  section: "02", perm: "leads.read",     Icon: UsersThree, module: "crm" },
  { to: "/projects",    label: "Projects",     section: "03", perm: "projects.read",  Icon: Briefcase, module: "projects" },
  { to: "/tasks",       label: "Tasks",        section: "04", perm: "tasks.read",     Icon: Kanban, module: "tasks" },
  { to: "/calendar",    label: "Calendar",     section: "04b", perm: "dashboard.read", Icon: CalendarBlank },
  { to: "/clients",     label: "Clients",      section: "05", perm: "clients.read",   Icon: UserCircle, module: "clients" },
  { to: "/vendors",     label: "Vendors",      section: "06", perm: "vendors.read",   Icon: HardHat },
  { to: "/purchase-orders", label: "Purchase Orders", section: "07", perm: "vendors.read", Icon: Package, module: "purchase_orders" },
  { to: "/invoices",    label: "Invoices",     section: "08", perm: "invoices.read",  Icon: Receipt, module: "invoices" },
  { to: "/quotations",  label: "Quotations",   section: "09", perm: "quotations.read", Icon: FilesIcon, module: "quotations" },
  { to: "/expenses",    label: "Expenses",     section: "10", perm: "dashboard.read", Icon: Wallet, module: "expenses" },
  { to: "/employees",   label: "Employees",    section: "11", perm: "employees.read", Icon: IdentificationCard, module: "employees" },
  { to: "/attendance",  label: "Attendance",   section: "12", perm: "dashboard.read", Icon: Clock, module: "attendance" },
  { to: "/holidays",    label: "Holidays",     section: "12b", perm: "dashboard.read", Icon: Clock, module: "attendance" },
  { to: "/accounting",  label: "Accounting",   section: "13", perm: "finance.read",   Icon: Bank, module: "accounting" },
  { to: "/loans",       label: "Loans & EMI",  section: "14", perm: "finance.read",   Icon: CreditCard, module: "loans" },
  { to: "/settings/company", label: "Company", section: "15", perm: "*.*",           Icon: Palette, admin: true },
  { to: "/admin/rbac",  label: "Team & Roles", section: "16", perm: "users.read",     Icon: ShieldCheck, admin: true },
];

const fmtClock = (d) =>
  d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });

export default function Layout({ children }) {
  const { user, logout, hasPerm, currentOrg, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [now, setNow] = useState(new Date());
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close the mobile drawer on route change
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(t);
  }, []);

  // Filter nav by permission + module feature flag + admin flag.
  const enabledModules = currentOrg?.features?.modules || {};
  const visibleNav = NAV.filter((n) => {
    if (n.admin && !(user?.role === "Admin" || isSuperAdmin)) return false;
    if (n.module && enabledModules[n.module] === false) return false;
    return hasPerm(n.perm);
  });

  const currentNav = visibleNav.find((n) => location.pathname.startsWith(n.to));
  const brandName = currentOrg?.display_name || currentOrg?.name || "DESIGN SAGA";
  const brandTagline = currentOrg?.branding?.tagline || "STUDIO OS · v0.2";
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

        <nav className="flex-1 p-3 space-y-0.5">
          <div className="overline px-3 py-3 text-[#A8A296]">NAVIGATE</div>
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
                  <span className="font-mono text-[10px] text-[#B0AA9E] w-5">00</span>
                  <Crown size={17} weight={isActive ? "fill" : "regular"} />
                  <span className="flex-1">Super Admin</span>
                  {isActive && <CaretRight size={12} weight="bold" />}
                </>
              )}
            </NavLink>
          )}
          {visibleNav.map(({ to, label, section, Icon }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={`nav-${to.replace("/", "")}`}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg transition-all relative ${
                  isActive
                    ? "bg-[#F3EFE9] text-[#1A1A1A] font-semibold"
                    : "text-[#6B6B6B] hover:bg-black/[0.04] hover:text-[#1A1A1A] hover:translate-x-0.5"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <div className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-[#8B7F6A]" />}
                  <span className="font-mono text-[10px] text-[#B0AA9E] w-5">{section}</span>
                  <Icon size={17} weight={isActive ? "fill" : "regular"} className={isActive ? "text-[#76705E]" : "text-[#9B9B9B] group-hover:text-[#6B6B6B]"} />
                  <span className="flex-1">{label}</span>
                  {isActive && <CaretRight size={12} weight="bold" className="text-[#76705E]" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Pro tip card */}
        <div className="mx-3 mb-3 p-4 rounded-xl border border-[#E8E6E1] bg-white hover:shadow-sm transition">
          <div className="eyebrow text-[9px] text-[#8a6f24] mb-2">PRO TIP</div>
          <p className="text-xs leading-relaxed text-[#4A4A4A]">
            Press <kbd className="inline-block px-1.5 py-0.5 rounded bg-[#F5F4F0] border border-[#E8E6E1] font-mono text-[10px] text-[#2C2C2C]">⌘ K</kbd> anywhere for quick actions.
          </p>
        </div>

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
            onClick={logout}
            data-testid="sidebar-logout-btn"
            className="w-full flex items-center justify-center gap-2 text-xs font-semibold py-2.5 rounded-xl border border-[#E8E6E1] bg-white text-[#6B6B6B] hover:text-[#1A1A1A] hover:border-[#8B7F6A] transition"
          >
            <SignOut size={14} /> Sign out
          </button>
        </div>
      </aside>

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
          <div className="hidden md:flex items-center gap-3 text-sm text-[#6B6B6B]">
            <span className="overline">{(brandName || "").toUpperCase()}</span>
            <CaretRight size={10} className="text-[#9B9B9B]" />
            <span className="text-[#2C2C2C] font-semibold">{currentNav?.label || "Page"}</span>
          </div>

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

          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-2 overline">
              <span className="live-dot" />
              <span>{now.toDateString().toUpperCase()} · {fmtClock(now)}</span>
            </div>
            <NotificationBell />
          </div>
        </header>

        <div className="p-4 lg:p-8 fade-in">{children}</div>
      </main>

      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />
      <AIWidget />
    </div>
  );
}
