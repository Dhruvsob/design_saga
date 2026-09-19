import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Bell } from "@phosphor-icons/react";
import api from "../lib/api";

// App-wide calendar reminder poller. Renders nothing — it periodically asks the
// backend for the current user's imminent events (based on each event's
// reminder_minutes) and surfaces them as a toast + an optional short sound.
// Dedup is per (event, date) in localStorage so a reminder is shown once.

const POLL_MS = 60000;

function playBeep() {
  try {
    if ((localStorage.getItem("cal_reminder_sound") ?? "on") === "off") return;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const t = ctx.currentTime;
    const blip = (freq, start, dur, peak) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = freq;
      g.gain.value = 0.0001;
      o.connect(g);
      g.connect(ctx.destination);
      g.gain.exponentialRampToValueAtTime(peak, start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
      o.start(start);
      o.stop(start + dur + 0.02);
    };
    blip(880, t, 0.32, 0.2);
    blip(1175, t + 0.38, 0.3, 0.15);
    setTimeout(() => { try { ctx.close(); } catch { /* ignore */ } }, 1200);
  } catch {
    /* autoplay blocked or unsupported — reminders still show as toasts */
  }
}

const shownKey = (id, date) => `calrem_${date}_${id}`;

export default function CalendarReminders() {
  const navigate = useNavigate();
  const timer = useRef(null);

  useEffect(() => {
    let alive = true;

    const check = async () => {
      try {
        const { data } = await api.get("/calendar/reminders/due");
        if (!alive) return;
        for (const r of data?.reminders || []) {
          const key = shownKey(r.id, r.date);
          try {
            if (localStorage.getItem(key)) continue;
            localStorage.setItem(key, "1");
          } catch {
            /* storage unavailable — allow through */
          }
          const when =
            r.minutes_until > 0
              ? `in ${r.minutes_until} min`
              : r.minutes_until === 0
                ? "now"
                : "just started";
          toast(`Reminder: ${r.title}`, {
            description: `${r.start_time || ""}${r.location ? " · " + r.location : ""} · ${when}`,
            icon: <Bell size={16} />,
            duration: 12000,
            action: { label: "Open", onClick: () => navigate("/calendar") },
          });
          playBeep();
        }
      } catch {
        /* not authenticated / no permission — ignore silently */
      }
    };

    check();
    timer.current = setInterval(check, POLL_MS);
    return () => {
      alive = false;
      if (timer.current) clearInterval(timer.current);
    };
  }, [navigate]);

  return null;
}
