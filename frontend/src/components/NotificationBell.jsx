import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { formatDate } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { Bell, Check, X, ArrowClockwise, SlidersHorizontal, CaretLeft } from "@phosphor-icons/react";

const PREFERENCE_LABELS = [
  ["tasks", "Tasks"],
  ["finance", "Finance"],
  ["attendance", "Attendance & leave"],
  ["calendar", "Calendar"],
];

const KIND_COLOR = {
  task_assigned: "bg-[var(--info-soft)] text-[var(--accent-strong)]",
  task_due: "bg-[var(--warning-soft)] text-[var(--warning)]",
  task_overdue: "bg-[var(--danger-soft)] text-[var(--danger)]",
  vendor_bill_due: "bg-[var(--warning-soft)] text-[var(--warning)]",
  vendor_bill_overdue: "bg-[var(--danger-soft)] text-[var(--danger)]",
  invoice_due: "bg-[var(--warning-soft)] text-[var(--warning)]",
  invoice_overdue: "bg-[var(--danger-soft)] text-[var(--danger)]",
  milestone_due: "bg-[var(--warning-soft)] text-[var(--warning)]",
  milestone_overdue: "bg-[var(--danger-soft)] text-[var(--danger)]",
  leave_request: "bg-[#F5EEF7] text-[#5B2A83]",
  leave_decided: "bg-[var(--success-soft)] text-[var(--success)]",
  account_approved: "bg-[var(--success-soft)] text-[var(--success)]",
  account_rejected: "bg-[var(--danger-soft)] text-[var(--danger)]",
  client_decision: "bg-[var(--info-soft)] text-[var(--accent-strong)]",
  info:"bg-[var(--line-soft)] text-[var(--ink)]",
};

const relativeTime = (iso) => {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const s = Math.round((now - then) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d}d ago`;
  return formatDate(iso);
};

export default function NotificationBell() {
  const { user, isPending, isRejected, pinLocked } = useAuth();
  // No polling while the App PIN lock is up (the server answers 423 anyway).
  const canPoll = !!user && !isPending && !isRejected && !pinLocked;
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [preferences, setPreferences] = useState(null);
  const boxRef = useRef(null);
  const timerRef = useRef(null);

  const load = async ({ force = false } = {}) => {
    if (!canPoll) return;
    // A hidden tab skips the 30 s refresh; it catches up as soon as it is shown.
    if (!force && typeof document !== "undefined" && document.visibilityState === "hidden") return;
    try {
      const { data } = await api.get("/notifications", { params: { limit: 30 } });
      setItems(data.notifications || []);
      setUnread(data.unread_count || 0);
    } catch {
      /* silently ignore — polling shouldn't spam errors */
    }
  };

  // Poll every 30 s while mounted AND user is fully approved.
  useEffect(() => {
    if (!canPoll) return;
    load({ force: true });
    timerRef.current = setInterval(load, 30_000);
    const onVisible = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timerRef.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canPoll]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const markRead = async (id) => {
    await api.post(`/notifications/${id}/read`);
    setItems((cur) => cur.map((n) => n.id === id ? { ...n, read: true } : n));
    setUnread((u) => Math.max(0, u - 1));
  };
  const dismiss = async (id) => {
    await api.delete(`/notifications/${id}`);
    setItems((cur) => cur.filter((n) => n.id !== id));
    setUnread((u) => {
      const n = items.find((x) => x.id === id);
      return n && !n.read ? Math.max(0, u - 1) : u;
    });
  };
  const markAll = async () => {
    setBusy(true);
    try {
      await api.post("/notifications/mark-all-read");
      setItems((cur) => cur.map((n) => ({ ...n, read: true })));
      setUnread(0);
    } finally { setBusy(false); }
  };
  const scan = async () => {
    setBusy(true);
    try {
      await load();
    } finally { setBusy(false); }
  };

  const openSettings = async () => {
    setBusy(true);
    try {
      const { data } = await api.get("/notifications/preferences");
      setPreferences(data);
      setSettingsOpen(true);
    } finally { setBusy(false); }
  };

  const savePreferences = async () => {
    if (!preferences) return;
    setBusy(true);
    try {
      const { data } = await api.put("/notifications/preferences", preferences);
      setPreferences(data);
      setSettingsOpen(false);
    } finally { setBusy(false); }
  };

  const sorted = useMemo(() =>
    [...items].sort((a, b) =>
      (a.read === b.read) ? (b.created_at || "").localeCompare(a.created_at || "")
                           : (a.read ? 1 : -1)
    ), [items]);

  return (
    <div className="relative" ref={boxRef}>
      <button
        className="btn-icon relative"
        onClick={() => setOpen(!open)}
        data-testid="top-notifications-btn"
        aria-label="Notifications"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span
            data-testid="notif-badge"
            className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 bg-[var(--danger)] text-white text-[10px] font-mono font-bold flex items-center justify-center rounded-full"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {/* Phones: the panel spans the screen under the top bar. Anchored to the
          bell (left of the lock button), a 380 px panel started off the left
          edge on every phone width (-22 px at 435 px, -45 px at 390 px). */}
      {open && (
        <div
          data-testid="notif-panel"
          className="fixed inset-x-3 top-[3.75rem] sm:absolute sm:inset-x-auto sm:top-auto sm:right-0 sm:mt-2 sm:w-[380px] max-h-[min(520px,calc(100dvh-5rem))] bg-white border border-[var(--line)] shadow-xl z-50 flex flex-col rounded-lg overflow-hidden"
        >
          {/* header */}
          <div className="p-4 border-b border-[var(--line)] flex items-center justify-between">
            <div>
              <div className="overline">{settingsOpen ? "NOTIFICATION SETTINGS" : "NOTIFICATIONS"}</div>
              <div className="text-xs text-[var(--ink-2)] mt-0.5">
                {settingsOpen ? "Choose alerts for this account." : (unread > 0 ? `${unread} unread` : "All caught up.")}
              </div>
            </div>
            <div className="flex items-center gap-1">
              {settingsOpen ? (
                <button
                  onClick={() => setSettingsOpen(false)} disabled={busy}
                  title="Back to notifications" className="btn-ghost text-xs"
                  data-testid="notif-settings-back"
                ><CaretLeft size={12} /> Back</button>
              ) : (<>
                <button
                  onClick={openSettings} disabled={busy}
                  title="Notification settings"
                  className="btn-ghost text-xs" data-testid="notif-settings-btn"
                ><SlidersHorizontal size={12} /></button>
                <button
                  onClick={scan} disabled={busy}
                  title="Refresh notifications"
                  className="btn-ghost text-xs" data-testid="notif-scan-btn"
                ><ArrowClockwise size={12} /></button>
                {unread > 0 && (
                  <button
                    onClick={markAll} disabled={busy}
                    className="btn-ghost text-xs" data-testid="notif-mark-all-btn"
                  ><Check size={12} /> All read</button>
                )}
              </>)}
            </div>
          </div>

          {/* list */}
          {settingsOpen ? (
            <div className="overflow-y-auto flex-1 p-4" data-testid="notif-settings-panel">
              <div className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
                {PREFERENCE_LABELS.map(([key, label]) => (
                  <label key={key} className="min-h-12 flex items-center justify-between gap-4 py-3 cursor-pointer">
                    <span className="text-sm font-semibold">{label}</span>
                    <input
                      type="checkbox"
                      checked={preferences?.[key] !== false}
                      onChange={(e) => setPreferences((cur) => ({ ...cur, [key]: e.target.checked }))}
                      className="h-4 w-4 accent-[var(--accent)]"
                      data-testid={`notif-pref-${key}`}
                    />
                  </label>
                ))}
              </div>
              <div className="text-xs text-[var(--ink-2)] mt-3">
                Account approval and security notices remain enabled.
              </div>
              <button
                onClick={savePreferences} disabled={busy || !preferences}
                className="btn-primary w-full mt-4" data-testid="notif-preferences-save"
              >Save preferences</button>
            </div>
          ) : <div className="overflow-y-auto flex-1">
            {sorted.length === 0 && (
              <div className="p-10 text-center">
                <Bell size={24} className="mx-auto text-[var(--ink-3)] mb-2" />
                <div className="overline mb-1">EMPTY</div>
                <div className="text-xs text-[var(--ink-2)]">No notifications yet.</div>
              </div>
            )}
            {sorted.map((n) => (
              <div
                key={n.id}
                data-testid={`notif-row-${n.id}`}
                className={`p-3 border-b border-[var(--line-soft)] hover:bg-[var(--surface-2)] transition ${
                  !n.read ? "bg-[var(--info-soft)]" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 mt-0.5 rounded ${KIND_COLOR[n.kind] || KIND_COLOR.info}`}>
                    {n.kind.replace(/_/g, " ")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm ${!n.read ? "font-semibold" : ""}`}>
                      {n.link ? (
                        <Link to={n.link} onClick={() => { markRead(n.id); setOpen(false); }}
                          className="hover:text-[var(--accent-strong)]">{n.title}</Link>
                      ) : n.title}
                    </div>
                    {n.body && <div className="text-xs text-[var(--ink-2)] mt-0.5">{n.body}</div>}
                    <div className="text-[10px] text-[var(--ink-3)] font-mono uppercase tracking-wider mt-1">
                      {relativeTime(n.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {!n.read && (
                      <button
                        onClick={() => markRead(n.id)} title="Mark read"
                        className="btn-ghost p-1" data-testid={`notif-read-${n.id}`}
                      ><Check size={11} /></button>
                    )}
                    <button
                      onClick={() => dismiss(n.id)} title="Dismiss"
                      className="btn-ghost p-1" data-testid={`notif-dismiss-${n.id}`}
                    ><X size={11} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>}
        </div>
      )}
    </div>
  );
}
