import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  SquaresFour, UsersThree, Briefcase, Kanban, Receipt, UserCircle,
  Files as FilesIcon, SignOut, MagnifyingGlass, Bell, CaretRight, ShieldCheck,
  IdentificationCard, Clock, Bank,
} from "@phosphor-icons/react";
import AIWidget from "./AIWidget";
import { useEffect, useState } from "react";

const NAV = [
  { to: "/dashboard",   label: "Dashboard",    section: "01", perm: "dashboard.read", Icon: SquaresFour },
  { to: "/crm",         label: "Leads / CRM",  section: "02", perm: "leads.read",     Icon: UsersThree },
  { to: "/projects",    label: "Projects",     section: "03", perm: "projects.read",  Icon: Briefcase },
  { to: "/tasks",       label: "Tasks",        section: "04", perm: "tasks.read",     Icon: Kanban },
  { to: "/clients",     label: "Clients",      section: "05", perm: "clients.read",   Icon: UserCircle },
  { to: "/invoices",    label: "Invoices",     section: "06", perm: "invoices.read",  Icon: Receipt },
  { to: "/quotations",  label: "Quotations",   section: "07", perm: "quotations.read", Icon: FilesIcon },
  { to: "/employees",   label: "Employees",    section: "08", perm: "employees.read", Icon: IdentificationCard },
  { to: "/attendance",  label: "Attendance",   section: "09", perm: "dashboard.read", Icon: Clock },
  { to: "/accounting",  label: "Accounting",   section: "10", perm: "finance.read",   Icon: Bank },
  { to: "/admin/rbac",  label: "Team & Roles", section: "11", perm: "users.read",     Icon: ShieldCheck, admin: true },
];

const fmtClock = (d) =>
  d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });

export default function Layout({ children }) {
  const { user, logout, hasPerm } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(t);
  }, []);

  // Filter nav by permission (respect explicit admin-only flag too).
  const visibleNav = NAV.filter((n) => {
    if (n.admin && user?.role !== "Admin") return false;
    return hasPerm(n.perm);
  });

  const currentNav = visibleNav.find((n) => location.pathname.startsWith(n.to));

  return (
    <div className="min-h-screen flex bg-white">
      {/* ============== SIDEBAR ============== */}
      <aside className="w-64 shrink-0 border-r border-[#E5E5E5] flex flex-col min-h-screen sticky top-0 bg-white" data-testid="app-sidebar">
        <button
          onClick={() => navigate("/dashboard")}
          className="p-6 border-b border-[#E5E5E5] flex items-center gap-3 text-left hover:bg-[#FAFAFA] transition group"
          data-testid="sidebar-logo-btn"
        >
          <div className="relative w-9 h-9 bg-[#002FA7] flex items-center justify-center transition-transform group-hover:scale-105">
            <span className="text-white font-display font-bold text-sm">DS</span>
            <div className="absolute -top-1 -right-1 w-2 h-2 bg-[#1D633E] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
          </div>
          <div>
            <div className="font-display font-bold tracking-tight text-sm">DESIGN SAGA</div>
            <div className="eyebrow text-[10px] text-[#5C5C5C]">STUDIO OS · v0.2</div>
          </div>
        </button>

        <nav className="flex-1 p-3 space-y-0.5">
          <div className="overline px-3 py-3">NAVIGATE</div>
          {visibleNav.map(({ to, label, section, Icon }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={`nav-${to.replace("/", "")}`}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 text-sm transition-all relative ${
                  isActive
                    ? "bg-[#F5F5F5] text-[#002FA7] font-semibold"
                    : "text-[#0A0A0A] hover:bg-[#FAFAFA] hover:translate-x-0.5"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[#002FA7]" />}
                  <span className="font-mono text-[10px] text-[#9A9A9A] w-5">{section}</span>
                  <Icon size={17} weight={isActive ? "fill" : "regular"} />
                  <span className="flex-1">{label}</span>
                  {isActive && <CaretRight size={12} weight="bold" />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Pro tip card */}
        <div className="mx-3 mb-3 p-4 border border-[#E5E5E5] bg-[#FAFAFA] hover:bg-white transition">
          <div className="eyebrow text-[9px] text-[#002FA7] mb-2">PRO TIP</div>
          <p className="text-xs leading-relaxed text-[#0A0A0A]">
            Press <kbd className="inline-block px-1.5 py-0.5 bg-white border border-[#E5E5E5] font-mono text-[10px]">⌘ K</kbd> anywhere for quick actions.
          </p>
        </div>

        <div className="p-4 border-t border-[#E5E5E5]">
          <div className="flex items-center gap-3 mb-3">
            {user?.picture ? (
              <img src={user.picture} alt="" className="w-9 h-9 object-cover ring-1 ring-[#E5E5E5]" />
            ) : (
              <div className="w-9 h-9 bg-[#0A0A0A] flex items-center justify-center text-white font-display font-bold text-xs">
                {(user?.name || "?").slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate" data-testid="sidebar-user-name">{user?.name}</div>
              <div className="text-[10px] font-mono tracking-wider uppercase text-[#5C5C5C] flex items-center gap-1.5">
                <span className="live-dot" />
                {user?.role || "employee"}
              </div>
            </div>
          </div>
          <button
            onClick={logout}
            data-testid="sidebar-logout-btn"
            className="w-full btn-ghost justify-center text-xs"
          >
            <SignOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      {/* ============== MAIN ============== */}
      <main className="flex-1 min-w-0">
        {/* Top brand accent strip */}
        <div className="h-[3px] bg-gradient-to-r from-[#002FA7] via-[#0A0A0A] to-[#002FA7] no-print" />

        <header className="h-16 border-b border-[#E5E5E5] px-8 flex items-center justify-between sticky top-0 bg-white/95 backdrop-blur-sm z-20 no-print">
          {/* breadcrumb */}
          <div className="flex items-center gap-3 text-sm text-[#5C5C5C]">
            <span className="overline">DESIGN SAGA</span>
            <CaretRight size={10} className="text-[#9A9A9A]" />
            <span className="text-[#0A0A0A] font-semibold">{currentNav?.label || "Page"}</span>
          </div>

          {/* search */}
          <div className="flex items-center gap-2 flex-1 max-w-md mx-8 px-3 py-2 border border-transparent hover:border-[#E5E5E5] focus-within:border-[#002FA7] transition">
            <MagnifyingGlass size={15} className="text-[#5C5C5C]" />
            <input
              data-testid="top-search"
              placeholder="Search projects, clients, invoices…"
              className="bg-transparent flex-1 outline-none text-sm placeholder-[#9A9A9A]"
            />
            <kbd className="hidden md:inline-block px-1.5 py-0.5 bg-[#FAFAFA] border border-[#E5E5E5] font-mono text-[10px] text-[#5C5C5C]">⌘K</kbd>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-2 overline">
              <span className="live-dot" />
              <span>{now.toDateString().toUpperCase()} · {fmtClock(now)}</span>
            </div>
            <button className="btn-icon" data-testid="top-notifications-btn" aria-label="Notifications">
              <Bell size={16} />
            </button>
          </div>
        </header>

        <div className="p-8 fade-in">{children}</div>
      </main>

      <AIWidget />
    </div>
  );
}
