import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "../lib/api";

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
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    await api.post("/auth/logout");
    setUser(null);
    window.location.href = "/";
  };

  const loginWithPassword = async (identifier, password) => {
    const { data } = await api.post("/auth/login-password", { identifier, password });
    setUser(data.user);
    return data.user;
  };

  const hasPerm = useCallback((perm) => checkPerm(user?.permissions, perm), [user]);
  const isPending = user?.approval_status === "pending";
  // Rejected takes effect only when the user is not simply "still pending".
  // A pending user has is_active=false too, so guard against mis-branding them.
  const isRejected =
    user?.approval_status === "rejected" ||
    (user?.is_active === false && user?.approval_status !== "pending");

  return (
    <AuthContext.Provider
      value={{ user, setUser, loading, logout, refresh: checkAuth, hasPerm,
               loginWithPassword, isPending, isRejected }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
