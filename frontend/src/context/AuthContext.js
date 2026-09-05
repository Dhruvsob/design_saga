import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { setSessionToken } from "../lib/api";

const AuthContext = createContext(null);

function checkPerm(permissions, perm) {
  if (!permissions || !permissions.length) return false;
  if (permissions.includes("*.*")) return true;
  if (permissions.includes(perm)) return true;
  const resource = perm.split(".")[0];
  return permissions.includes(`${resource}.*`);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [currentOrg, setCurrentOrg] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchOrg = useCallback(async () => {
    try {
      const { data } = await api.get("/org/current");
      setCurrentOrg(data);
      // Apply CSS variables so any component can theme against org colors.
      if (data?.branding?.primary_color) {
        document.documentElement.style.setProperty(
          "--org-primary", data.branding.primary_color
        );
      }
      if (data?.branding?.accent_color) {
        document.documentElement.style.setProperty(
          "--org-accent", data.branding.accent_color
        );
      }
    } catch {
      setCurrentOrg(null);
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      // Fetch org branding for logged-in users (skip SuperAdmin without org context)
      if (data?.role !== "SuperAdmin" || data?.org_id) {
        await fetchOrg();
      }
    } catch {
      setUser(null);
      setCurrentOrg(null);
    } finally {
      setLoading(false);
    }
  }, [fetchOrg]);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* already invalid */ }
    setSessionToken(null);
    setUser(null);
    setCurrentOrg(null);
    window.location.href = "/";
  };

  const loginWithPassword = async (identifier, password) => {
    const { data } = await api.post("/auth/login-password", { identifier, password });
    if (data.session_token) setSessionToken(data.session_token);
    setUser(data.user);
    await fetchOrg();
    return data.user;
  };

  const hasPerm = useCallback((perm) => checkPerm(user?.permissions, perm), [user]);
  const isPending = user?.approval_status === "pending";
  const isRejected =
    user?.approval_status === "rejected" ||
    (user?.is_active === false && user?.approval_status !== "pending");
  const isSuperAdmin = user?.role === "SuperAdmin" || user?.is_super_admin === true;

  return (
    <AuthContext.Provider
      value={{
        user, setUser, loading, logout, refresh: checkAuth, hasPerm,
        loginWithPassword, isPending, isRejected, isSuperAdmin,
        currentOrg, refreshOrg: fetchOrg,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
