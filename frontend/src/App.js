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
import Clients from "./pages/Clients";
import Invoices from "./pages/Invoices";
import QuotationsAdv from "./pages/QuotationsAdv";
import QuotationBuilder from "./pages/QuotationBuilder";
import ClientPortal from "./pages/ClientPortal";
import Layout from "./components/Layout";

function ProtectedShell({ children }) {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!loading && !user) navigate("/", { replace: true });
  }, [user, loading, navigate]);
  if (loading) return <div className="min-h-screen flex items-center justify-center overline">LOADING…</div>;
  if (!user) return null;
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
      <Route path="/clients" element={<ProtectedShell><Clients /></ProtectedShell>} />
      <Route path="/invoices" element={<ProtectedShell><Invoices docType="invoice" /></ProtectedShell>} />
      <Route path="/quotations" element={<ProtectedShell><QuotationsAdv /></ProtectedShell>} />
      <Route path="/quotations/:id" element={<ProtectedShell><QuotationBuilder /></ProtectedShell>} />
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
