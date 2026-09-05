import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Bell, Check, X, ArrowClockwise } from "@phosphor-icons/react";

const KIND_COLOR = {
  task_assigned: "bg-[#EEF2FF] text-[#8B7F6A]",
  task_due: "bg-[#FFF4E5] text-[#7A4E1A]",
  task_overdue: "bg-[#FCEEEC] text-[#B22B22]",
  vendor_bill_due: "bg-[#FFF4E5] text-[#7A4E1A]",
  vendor_bill_overdue: "bg-[#FCEEEC] text-[#B22B22]",
  invoice_due: "bg-[#FFF4E5] text-[#7A4E1A]",
  invoice_overdue: "bg-[#FCEEEC] text-[#B22B22]",
  milestone_due: "bg-[#FFF4E5] text-[#7A4E1A]",
  milestone_overdue: "bg-[#FCEEEC] text-[#B22B22]",
  leave_request: "bg-[#F5EEF7] text-[#5B2A83]",
  leave_decided: "bg-[#EFF7EF] text-[#1D633E]",
  account_approved: "bg-[#EFF7EF] text-[#1D633E]",
  account_rejected: "bg-[#FCEEEC] text-[#B22B22]",
  info: "bg-[#F2F2F2] text-[#0A0A0A]",
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
  return new Date(iso).toLocaleDateString();
};

export default function NotificationBell() {
  const { user, isPending, isRejected } = useAuth();
  const canPoll = !!user && !isPending && !isRejected;
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef(null);
  const timerRef = useRef(null);

  const load = async () => {
    if (!canPoll) return;
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
    load();
    timerRef.current = setInterval(load, 30_000);
    return () => clearInterval(timerRef.current);
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
      await api.post("/notifications/scan");
      await load();
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
            className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 bg-[#B22B22] text-white text-[10px] font-mono font-bold flex items-center justify-center rounded-full"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          data-testid="notif-panel"
          className="absolute right-0 mt-2 w-[380px] max-h-[520px] bg-white border border-[#E5E5E5] shadow-xl z-50 flex flex-col"
        >
          {/* header */}
          <div className="p-4 border-b border-[#E5E5E5] flex items-center justify-between">
            <div>
              <div className="overline">NOTIFICATIONS</div>
              <div className="text-xs text-[#5C5C5C] mt-0.5">
                {unread > 0 ? `${unread} unread` : "All caught up."}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={scan} disabled={busy}
                title="Refresh & scan for new alerts"
                className="btn-ghost text-xs" data-testid="notif-scan-btn"
              ><ArrowClockwise size={12} /></button>
              {unread > 0 && (
                <button
                  onClick={markAll} disabled={busy}
                  className="btn-ghost text-xs" data-testid="notif-mark-all-btn"
                ><Check size={12} /> All read</button>
              )}
            </div>
          </div>

          {/* list */}
          <div className="overflow-y-auto flex-1">
            {sorted.length === 0 && (
              <div className="p-10 text-center">
                <Bell size={24} className="mx-auto text-[#9A9A9A] mb-2" />
                <div className="overline mb-1">EMPTY</div>
                <div className="text-xs text-[#5C5C5C]">No notifications yet. Try Scan to check for due items.</div>
              </div>
            )}
            {sorted.map((n) => (
              <div
                key={n.id}
                data-testid={`notif-row-${n.id}`}
                className={`p-3 border-b border-[#F0F0F0] hover:bg-[#FAFAFA] transition ${
                  !n.read ? "bg-[#F7F9FE]" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 mt-0.5 ${KIND_COLOR[n.kind] || KIND_COLOR.info}`}>
                    {n.kind.replace(/_/g, " ")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm ${!n.read ? "font-semibold" : ""}`}>
                      {n.link ? (
                        <Link to={n.link} onClick={() => { markRead(n.id); setOpen(false); }}
                          className="hover:text-[#8B7F6A]">{n.title}</Link>
                      ) : n.title}
                    </div>
                    {n.body && <div className="text-xs text-[#5C5C5C] mt-0.5">{n.body}</div>}
                    <div className="text-[10px] text-[#9A9A9A] font-mono uppercase tracking-wider mt-1">
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
          </div>
        </div>
      )}
    </div>
  );
}
