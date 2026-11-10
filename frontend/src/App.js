import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, useLocation, Navigate, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";
import "@/App.css";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import Layout from "./components/Layout";
import { MandatoryPinSetupOverlay, PinLockOverlay } from "./components/AppPinLock";
import { ConfirmHost } from "./lib/confirm";

// lazy() plus .preload(), so a page's code can download while the PIN screen is up.
const lazyPage = (factory) => Object.assign(lazy(factory), { preload: factory });

const Dashboard = lazyPage(() => import("./pages/Dashboard"));
const Leads = lazyPage(() => import("./pages/Leads"));
const Projects = lazyPage(() => import("./pages/Projects"));
const ProjectDetail = lazyPage(() => import("./pages/ProjectDetail"));
const Tasks = lazyPage(() => import("./pages/TasksBoard"));
const TaskDetail = lazyPage(() => import("./pages/TaskDetail"));
const Attendance = lazyPage(() => import("./pages/Attendance"));
const Holidays = lazyPage(() => import("./pages/Holidays"));
const LiveMap = lazyPage(() => import("./pages/LiveMap"));
const Payroll = lazyPage(() => import("./pages/Payroll"));
const Accounting = lazyPage(() => import("./pages/Accounting"));
const Clients = lazyPage(() => import("./pages/Clients"));
const ClientDetail = lazyPage(() => import("./pages/ClientDetail"));
const Invoices = lazyPage(() => import("./pages/Invoices"));
const PaymentReminders = lazyPage(() => import("./pages/PaymentReminders"));
const ReceivedPayments = lazyPage(() => import("./pages/ReceivedPayments"));
const QuotationsAdv = lazyPage(() => import("./pages/QuotationsAdv"));
const QuotationBuilder = lazyPage(() => import("./pages/QuotationBuilder"));
const RBACAdmin = lazyPage(() => import("./pages/RBACAdmin"));
const Employees = lazyPage(() => import("./pages/Employees"));
const EmployeeDetail = lazyPage(() => import("./pages/EmployeeDetail"));
const Vendors = lazyPage(() => import("./pages/Vendors"));
const VendorDetail = lazyPage(() => import("./pages/VendorDetail"));
const ClientPortal = lazyPage(() => import("./pages/ClientPortal"));
const Loans = lazyPage(() => import("./pages/Loans"));
const PurchaseOrders = lazyPage(() => import("./pages/PurchaseOrders"));
const Expenses = lazyPage(() => import("./pages/Expenses"));
const SuperAdminPanel = lazyPage(() => import("./pages/SuperAdminPanel"));
const CalendarPage = lazyPage(() => import("./pages/Calendar"));
const CompanySettings = lazyPage(() => import("./pages/CompanySettings"));
const AuditLog = lazyPage(() => import("./pages/AuditLog"));
const PrivacyPolicy = lazyPage(() => import("./pages/PrivacyPolicy"));
const LandingPage = lazyPage(() => import("./pages/LandingPage"));

const PageFallback = () => (
  <div className="min-h-[40vh] flex items-center justify-center overline">LOADING...</div>
);

function ProtectedShell({ children, requirePerm, requireSuperAdmin }) {
  const { user, loading, pinLocked, hasPerm, isPending, isRejected, isSuperAdmin, logout, isSuspended } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!loading && !user) navigate("/login", { replace: true });
  }, [user, loading, navigate]);
  const lockedOut = Boolean(pinLocked || user?.app_pin_setup_required);
  const page = children?.type;
  useEffect(() => {
    if (lockedOut) page?.preload?.();
  }, [lockedOut, page]);
  if (loading) return <div className="min-h-screen flex items-center justify-center overline">LOADING…</div>;
  if (!user) return null;
  // Suspended workspace: show a clear message before the user is confused.
  if (isSuspended) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white px-6">
        <div className="max-w-lg text-center" data-testid="suspended-workspace-screen">
          <div className="overline mb-4 text-[var(--warning)]">WORKSPACE SUSPENDED</div>
          <h1 className="font-display font-bold tracking-tighter text-5xl mb-4">Access paused.</h1>
          <p className="text-[var(--ink-2)] mb-6">
            Your workspace has been suspended by the platform administrator. This usually happens when a subscription payment is overdue. Please contact support to restore access.
          </p>
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--ink-3)] mb-6">
            Signed in as <span className="text-[var(--ink)]">{user.email}</span>
          </div>
          <button onClick={logout} className="btn-primary" data-testid="suspended-signout-btn">
            Sign out
          </button>
        </div>
      </div>
    );
  }

  // Pending / rejected: block ERP access entirely.
  if (isPending || isRejected) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white px-6">
        <div className="max-w-lg text-center" data-testid="pending-approval-screen">
          <div className="overline mb-4">
            {isRejected ? "ACCOUNT DEACTIVATED" : "AWAITING ADMIN APPROVAL"}
          </div>
          <h1 className="font-display font-bold tracking-tighter text-5xl mb-4">
            {isRejected ? "Not on the roster." : "You're on the list."}
          </h1>
          <p className="text-[var(--ink-2)] mb-6">
            {isRejected
              ? "Your account has been deactivated by an administrator. Please contact your studio owner to restore access."
              : "Your account is awaiting Admin approval. You'll get access as soon as it's granted."}
          </p>
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--ink-3)] mb-6">
            Signed in as <span className="text-[var(--ink)]">{user.email}</span>
          </div>
          <button onClick={logout} className="btn-primary" data-testid="pending-signout-btn">
            Sign out
          </button>
        </div>
      </div>
    );
  }

  // Unmount protected screens while locked so previously loaded business data
  // is not left rendered beneath the opaque lock screen.
  if (pinLocked || user.app_pin_setup_required) return <div className="min-h-screen bg-[var(--surface-2)]" aria-hidden="true" />;

  if (requireSuperAdmin && !isSuperAdmin) {
    return (
      <Layout>
        <div className="max-w-lg mx-auto text-center py-24" data-testid="access-denied-sa">
          <div className="overline mb-3">403 · SUPER ADMIN ONLY</div>
          <h1 className="font-display font-bold tracking-tighter text-4xl mb-3">Platform zone.</h1>
          <p className="text-[var(--ink-2)]">This area is reserved for the platform owner.</p>
        </div>
      </Layout>
    );
  }

  if (requirePerm && !hasPerm(requirePerm)) {
    return (
      <Layout>
        <div className="max-w-lg mx-auto text-center py-24" data-testid="access-denied">
          <div className="overline mb-3">403 · ACCESS RESTRICTED</div>
          <h1 className="font-display font-bold tracking-tighter text-4xl mb-3">Not for your eyes.</h1>
          <p className="text-[var(--ink-2)]">Your role doesn&apos;t include the <code className="font-mono text-[var(--accent-strong)]">{requirePerm}</code> permission. Ask an Admin.</p>
        </div>
      </Layout>
    );
  }
  return <Layout>{children}</Layout>;
}

function AppRouter() {
  const location = useLocation();
  useEffect(() => {
    if (!location.hash) window.scrollTo({ top: 0, behavior: "instant" });
  }, [location.pathname]);
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Suspense fallback={<PageFallback />}><Routes>
      <Route path="/" element={<PublicRoot />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/portal/:token" element={<ClientPortal />} />
      <Route path="/dashboard" element={<ProtectedShell><Dashboard /></ProtectedShell>} />
      <Route path="/crm" element={<ProtectedShell requirePerm="leads.read"><Leads /></ProtectedShell>} />
      <Route path="/projects" element={<ProtectedShell requirePerm="projects.read"><Projects /></ProtectedShell>} />
      <Route path="/projects/:id" element={<ProtectedShell requirePerm="projects.read"><ProjectDetail /></ProtectedShell>} />
      <Route path="/tasks" element={<ProtectedShell requirePerm="tasks.read"><Tasks /></ProtectedShell>} />
      <Route path="/tasks/:id" element={<ProtectedShell requirePerm="tasks.read"><TaskDetail /></ProtectedShell>} />
      <Route path="/calendar" element={<ProtectedShell requirePerm="calendar.read"><CalendarPage /></ProtectedShell>} />
      <Route path="/clients" element={<ProtectedShell requirePerm="clients.read"><Clients /></ProtectedShell>} />
      <Route path="/clients/:id" element={<ProtectedShell requirePerm="clients.read"><ClientDetail /></ProtectedShell>} />
      <Route path="/invoices" element={<ProtectedShell requirePerm="invoices.read"><Invoices docType="invoice" /></ProtectedShell>} />
      <Route path="/invoices/:id" element={<Navigate to="/invoices" replace />} />
      <Route path="/invoices/reminders" element={<ProtectedShell requirePerm="finance.read"><PaymentReminders /></ProtectedShell>} />
      <Route path="/invoices/received" element={<ProtectedShell requirePerm="finance.read"><ReceivedPayments /></ProtectedShell>} />
      <Route path="/quotations" element={<ProtectedShell requirePerm="quotations.read"><QuotationsAdv /></ProtectedShell>} />
      <Route path="/quotations/:id" element={<ProtectedShell requirePerm="quotations.read"><QuotationBuilder /></ProtectedShell>} />
      <Route path="/employees" element={<ProtectedShell requirePerm="employees.read"><Employees /></ProtectedShell>} />
      <Route path="/employees/:id" element={<ProtectedShell requirePerm="employees.read"><EmployeeDetail /></ProtectedShell>} />
      <Route path="/vendors" element={<ProtectedShell requirePerm="vendors.read"><Vendors /></ProtectedShell>} />
      <Route path="/vendors/:id" element={<ProtectedShell requirePerm="vendors.read"><VendorDetail /></ProtectedShell>} />
      <Route path="/attendance" element={<ProtectedShell requirePerm="attendance.read"><Attendance /></ProtectedShell>} />
      <Route path="/holidays" element={<ProtectedShell requirePerm="holidays.read"><Holidays /></ProtectedShell>} />
      <Route path="/live-map" element={<ProtectedShell requirePerm="attendance.approve"><LiveMap /></ProtectedShell>} />
      <Route path="/payroll" element={<ProtectedShell requirePerm="payroll.read"><Payroll /></ProtectedShell>} />
      <Route path="/accounting" element={<ProtectedShell requirePerm="finance.read"><Accounting /></ProtectedShell>} />
      <Route path="/loans" element={<ProtectedShell requirePerm="loans.read"><Loans /></ProtectedShell>} />
      <Route path="/purchase-orders" element={<ProtectedShell requirePerm="purchase_orders.read"><PurchaseOrders /></ProtectedShell>} />
      <Route path="/expenses" element={<ProtectedShell requirePerm="expenses.read"><Expenses /></ProtectedShell>} />
      <Route path="/admin/rbac" element={<ProtectedShell requirePerm="users.read"><RBACAdmin /></ProtectedShell>} />
      <Route path="/settings/company" element={<ProtectedShell requirePerm="*.*"><CompanySettings /></ProtectedShell>} />
      <Route path="/settings/audit" element={<ProtectedShell requirePerm="*.*"><AuditLog /></ProtectedShell>} />
      <Route path="/super-admin" element={<ProtectedShell requireSuperAdmin><SuperAdminPanel /></ProtectedShell>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes></Suspense>
  );
}

function PublicRoot() {
  const { user, loading, isPending, isRejected, isSuperAdmin } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center overline">LOADING…</div>;
  // Pending/rejected users land in ProtectedShell to see the notice consistently.
  if (user && (isPending || isRejected)) return <Navigate to="/dashboard" replace />;
  if (user && isSuperAdmin && !user.org_id) return <Navigate to="/super-admin" replace />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <LandingPage />;
}

function LoginRoute() {
  const { user, loading, isPending, isRejected, isSuperAdmin } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center overline">LOADING…</div>;
  if (user && (isPending || isRejected)) return <Navigate to="/dashboard" replace />;
  if (user && isSuperAdmin && !user.org_id) return <Navigate to="/super-admin" replace />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <MandatoryPinSetupOverlay />
          <PinLockOverlay />
        </BrowserRouter>
      </AuthProvider>
      <ConfirmHost />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            borderRadius: "0.75rem",
            border: "1px solid #E8E6E1",
            fontSize: "13px",
            fontFamily: "'Inter', sans-serif",
            color: "#2C2C2C",
            boxShadow: "0 10px 30px -12px rgba(17,17,17,0.18)",
          },
        }}
      />
    </div>
  );
}

export default App;
