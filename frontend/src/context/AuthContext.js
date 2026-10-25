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
  const [pinLocked, setPinLocked] = useState(false);

  const broadcastPinState = useCallback((locked) => {
    try {
      localStorage.setItem("ds_app_pin_state", JSON.stringify({ locked, at: Date.now() }));
    } catch { /* storage unavailable */ }
  }, []);

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
      setPinLocked(Boolean(data?.app_pin_locked));
      // Fetch org branding for every logged-in user. fetchOrg() handles a
      // missing org gracefully (catches + sets null), and the backend resolves
      // a default org even for SuperAdmins without an org_id — so the Company
      // settings page loads instead of being stuck on a skeleton.
      if (!data?.app_pin_locked) await fetchOrg();
    } catch {
      setUser(null);
      setCurrentOrg(null);
      setPinLocked(false);
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

  useEffect(() => {
    const lock = () => {
      setPinLocked(true);
      setCurrentOrg(null);
    };
    const sync = (event) => {
      if (event.key !== "ds_app_pin_state" || !event.newValue) return;
      try {
        const locked = Boolean(JSON.parse(event.newValue).locked);
        setPinLocked(locked);
        if (locked) setCurrentOrg(null);
      } catch { /* ignore */ }
    };
    window.addEventListener("app-pin-locked", lock);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("app-pin-locked", lock);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    if (!user?.app_pin_enabled || pinLocked) return undefined;
    let lastActivity = Date.now();
    let lastTouch = 0;
    let locking = false;

    const lockLocally = () => {
      if (locking) return;
      locking = true;
      setPinLocked(true);
      setCurrentOrg(null);
      broadcastPinState(true);
      api.post("/auth/pin/lock").catch(() => {});
    };
    const activity = () => {
      const now = Date.now();
      if (now - lastActivity >= 60000) {
        lockLocally();
        return;
      }
      lastActivity = now;
      if (now - lastTouch < 25000) return;
      lastTouch = now;
      api.post("/auth/pin/touch").catch((error) => {
        if (error?.response?.status === 423) lockLocally();
      });
    };
    const checkIdle = () => {
      if (Date.now() - lastActivity >= 60000) lockLocally();
    };
    const events = ["pointerdown", "keydown", "touchstart", "scroll"];
    events.forEach((name) => window.addEventListener(name, activity, { passive: true }));
    const timer = window.setInterval(checkIdle, 1000);
    document.addEventListener("visibilitychange", checkIdle);
    return () => {
      events.forEach((name) => window.removeEventListener(name, activity));
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", checkIdle);
    };
  }, [user?.app_pin_enabled, pinLocked, broadcastPinState]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* already invalid */ }
    setSessionToken(null);
    setUser(null);
    setCurrentOrg(null);
    setPinLocked(false);
    window.location.href = "/";
  };

  const loginWithPassword = async (identifier, password) => {
    const { data } = await api.post("/auth/login-password", { identifier, password });
    if (data.session_token) setSessionToken(data.session_token);
    setUser(data.user);
    setPinLocked(Boolean(data.user?.app_pin_locked));
    if (!data.user?.app_pin_locked) await fetchOrg();
    return data.user;
  };

  const setupPin = async (pin, currentPin = null) => {
    const { data } = await api.post("/auth/pin/setup", {
      pin, current_pin: currentPin || null,
    });
    setUser((current) => current ? {
      ...current, app_pin_enabled: true, app_pin_locked: false,
    } : current);
    setPinLocked(false);
    broadcastPinState(false);
    return data;
  };

  const unlockPin = async (pin) => {
    const { data } = await api.post("/auth/pin/unlock", { pin });
    setUser((current) => current ? { ...current, app_pin_locked: false } : current);
    setPinLocked(false);
    broadcastPinState(false);
    await fetchOrg();
    return data;
  };

  const lockNow = async () => {
    setPinLocked(true);
    setCurrentOrg(null);
    broadcastPinState(true);
    try { await api.post("/auth/pin/lock"); } catch { /* server lease expires independently */ }
  };

  const disablePin = async (pin) => {
    const { data } = await api.post("/auth/pin/disable", { pin });
    setUser((current) => current ? {
      ...current, app_pin_enabled: false, app_pin_locked: false,
    } : current);
    setPinLocked(false);
    broadcastPinState(false);
    return data;
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
        pinLocked, setupPin, unlockPin, lockNow, disablePin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
