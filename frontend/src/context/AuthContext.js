import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "../lib/api";

const AuthContext = createContext(null);

/** Check "resource.action" against a permissions array supporting wildcards. */
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
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id first.
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

  const hasPerm = useCallback(
    (perm) => checkPerm(user?.permissions, perm),
    [user]
  );

  return (
    <AuthContext.Provider value={{ user, setUser, loading, logout, refresh: checkAuth, hasPerm }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
