import { useEffect } from "react";
import { BrowserRouter, Routes, Route, useLocation, Navigate, useNavigate } from "react-router-dom";
import "@/App.css";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import Dashboard from "./pages/Dashboard";
import Leads from "./pages/Leads";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import Tasks from "./pages/Tasks";
import TaskDetail from "./pages/TaskDetail";
import Attendance from "./pages/Attendance";
import Accounting from "./pages/Accounting";
import Clients from "./pages/Clients";
import Invoices from "./pages/Invoices";
import QuotationsAdv from "./pages/QuotationsAdv";
import QuotationBuilder from "./pages/QuotationBuilder";
import RBACAdmin from "./pages/RBACAdmin";
import Employees from "./pages/Employees";
import EmployeeDetail from "./pages/EmployeeDetail";
import Vendors from "./pages/Vendors";
import VendorDetail from "./pages/VendorDetail";
import ClientPortal from "./pages/ClientPortal";
import Layout from "./components/Layout";

function ProtectedShell({ children, requirePerm }) {
  const { user, loading, hasPerm } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!loading && !user) navigate("/", { replace: true });
  }, [user, loading, navigate]);
  if (loading) return <div className="min-h-screen flex items-center justify-center overline">LOADING…</div>;
  if (!user) return null;
  if (requirePerm && !hasPerm(requirePerm)) {
    return (
      <Layout>
        <div className="max-w-lg mx-auto text-center py-24" data-testid="access-denied">
          <div className="overline mb-3">403 · ACCESS RESTRICTED</div>
          <h1 className="font-display font-bold tracking-tighter text-4xl mb-3">Not for your eyes.</h1>
          <p className="text-[#5C5C5C]">Your role doesn&apos;t include the <code className="font-mono text-[#002FA7]">{requirePerm}</code> permission. Ask an Admin.</p>
        </div>
      </Layout>
    );
  }
  return <Layout>{children}</Layout>;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<PublicRoot />} />
      <Route path="/portal/:token" element={<ClientPortal />} />
      <Route path="/dashboard" element={<ProtectedShell><Dashboard /></ProtectedShell>} />
      <Route path="/crm" element={<ProtectedShell><Leads /></ProtectedShell>} />
      <Route path="/projects" element={<ProtectedShell><Projects /></ProtectedShell>} />
      <Route path="/projects/:id" element={<ProtectedShell><ProjectDetail /></ProtectedShell>} />
      <Route path="/tasks" element={<ProtectedShell><Tasks /></ProtectedShell>} />
      <Route path="/tasks/:id" element={<ProtectedShell><TaskDetail /></ProtectedShell>} />
      <Route path="/clients" element={<ProtectedShell><Clients /></ProtectedShell>} />
      <Route path="/invoices" element={<ProtectedShell><Invoices docType="invoice" /></ProtectedShell>} />
      <Route path="/quotations" element={<ProtectedShell><QuotationsAdv /></ProtectedShell>} />
      <Route path="/quotations/:id" element={<ProtectedShell requirePerm="quotations.read"><QuotationBuilder /></ProtectedShell>} />
      <Route path="/employees" element={<ProtectedShell requirePerm="employees.read"><Employees /></ProtectedShell>} />
      <Route path="/employees/:id" element={<ProtectedShell requirePerm="employees.read"><EmployeeDetail /></ProtectedShell>} />
      <Route path="/vendors" element={<ProtectedShell requirePerm="vendors.read"><Vendors /></ProtectedShell>} />
      <Route path="/vendors/:id" element={<ProtectedShell requirePerm="vendors.read"><VendorDetail /></ProtectedShell>} />
      <Route path="/attendance" element={<ProtectedShell><Attendance /></ProtectedShell>} />
      <Route path="/accounting" element={<ProtectedShell requirePerm="finance.read"><Accounting /></ProtectedShell>} />
      <Route path="/admin/rbac" element={<ProtectedShell requirePerm="users.read"><RBACAdmin /></ProtectedShell>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function PublicRoot() {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center overline">LOADING…</div>;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
