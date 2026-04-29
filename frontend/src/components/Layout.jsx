import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  SquaresFour, UsersThree, Briefcase, Kanban, Receipt, UserCircle,
  Files as FilesIcon, SignOut, MagnifyingGlass, Bell,
} from "@phosphor-icons/react";
import AIWidget from "./AIWidget";

const NAV = [
  { to: "/dashboard", label: "Dashboard", Icon: SquaresFour },
  { to: "/crm", label: "Leads / CRM", Icon: UsersThree },
  { to: "/projects", label: "Projects", Icon: Briefcase },
  { to: "/tasks", label: "Tasks", Icon: Kanban },
  { to: "/clients", label: "Clients", Icon: UserCircle },
  { to: "/invoices", label: "Invoices", Icon: Receipt },
  { to: "/quotations", label: "Quotations", Icon: FilesIcon },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex bg-white">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-[#E5E5E5] flex flex-col min-h-screen sticky top-0" data-testid="app-sidebar">
        <button
          onClick={() => navigate("/dashboard")}
          className="p-6 border-b border-[#E5E5E5] flex items-center gap-3 text-left hover:bg-[#FAFAFA] transition"
          data-testid="sidebar-logo-btn"
        >
          <div className="w-8 h-8 bg-[#002FA7] flex items-center justify-center">
            <span className="text-white font-display font-bold text-xs">DS</span>
          </div>
          <div>
            <div className="font-display font-bold tracking-tight text-sm">DESIGN SAGA</div>
            <div className="overline text-[10px]">STUDIO OS</div>
          </div>
        </button>

        <nav className="flex-1 p-4 space-y-1">
          <div className="overline px-3 py-2">NAVIGATE</div>
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={`nav-${to.replace("/", "")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 text-sm transition border-l-2 ${
                  isActive
                    ? "border-[#002FA7] bg-[#F5F5F5] text-[#002FA7] font-semibold"
                    : "border-transparent text-[#0A0A0A] hover:bg-[#FAFAFA]"
                }`
              }
            >
              <Icon size={18} weight="regular" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[#E5E5E5]">
          <div className="flex items-center gap-3 mb-3">
            {user?.picture ? (
              <img src={user.picture} alt="" className="w-8 h-8 object-cover" />
            ) : (
              <div className="w-8 h-8 bg-[#E5E5E5]" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate" data-testid="sidebar-user-name">{user?.name}</div>
              <div className="text-[10px] font-mono tracking-wider uppercase text-[#5C5C5C]">{user?.role || "employee"}</div>
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

      {/* Main */}
      <main className="flex-1 min-w-0">
        <header className="h-16 border-b border-[#E5E5E5] px-8 flex items-center justify-between sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2 flex-1 max-w-xl">
            <MagnifyingGlass size={16} className="text-[#5C5C5C]" />
            <input
              data-testid="top-search"
              placeholder="Search projects, clients, invoices…"
              className="bg-transparent flex-1 outline-none text-sm placeholder-[#5C5C5C]"
            />
          </div>
          <div className="flex items-center gap-4">
            <div className="overline hidden md:block">{new Date().toDateString()}</div>
            <button className="p-2 hover:bg-[#FAFAFA] transition" data-testid="top-notifications-btn">
              <Bell size={18} />
            </button>
          </div>
        </header>

        <div className="p-8">{children}</div>
      </main>

      <AIWidget />
    </div>
  );
}
