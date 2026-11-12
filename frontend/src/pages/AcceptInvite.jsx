import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle, LockKey, Warning } from "@phosphor-icons/react";
import api from "../lib/api";

const STRONG = /^(?=.*[A-Za-z])(?=.*\d).{8,128}$/;

function detailText(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || String(e)).join(" · ");
  return detail.msg || fallback;
}

/** Public page behind a one-time link: a new workspace owner (or a user whose
 *  password was reset by platform support) chooses their own password. */
export default function AcceptInvite() {
  const { token } = useParams();
  const [invite, setInvite] = useState(null);
  const [state, setState] = useState("loading"); // loading | ready | invalid | done
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api.get(`/auth/invite/${encodeURIComponent(token)}`)
      .then(({ data }) => { if (alive) { setInvite(data); setState("ready"); } })
      .catch(() => { if (alive) setState("invalid"); });
    return () => { alive = false; };
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!STRONG.test(pw)) { setErr("Use at least 8 characters with letters and digits."); return; }
    if (pw !== pw2) { setErr("The two passwords do not match."); return; }
    setBusy(true);
    try {
      await api.post("/auth/invite/accept", { token, password: pw });
      setState("done");
    } catch (ex) {
      if (ex?.response?.status === 404) setState("invalid");
      else setErr(detailText(ex?.response?.data?.detail, "Could not set the password. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const isReset = invite?.purpose === "reset";
  return (
    <main className="min-h-screen flex items-center justify-center px-4 py-10" style={{ background: "var(--app)" }}>
      <div className="w-full max-w-[420px] card-flat p-7 sm:p-8 fade-up" data-testid="invite-page">
        <div className="overline mb-3 text-[var(--accent-strong)]">
          {isReset ? "Reset password" : "Welcome"}
        </div>

        {state === "loading" && <div className="overline live-dot">CHECKING LINK</div>}

        {state === "invalid" && (
          <div data-testid="invite-invalid">
            <h1 className="font-display font-bold tracking-tighter text-2xl mb-2 text-[var(--ink)]">This link no longer works</h1>
            <p className="text-sm text-[var(--ink-2)] leading-relaxed mb-6">
              Set-password links work once and expire after 72 hours. Ask your workspace
              administrator or platform support for a new link.
            </p>
            <Link to="/login" className="btn-ghost w-full justify-center py-2.5">Go to sign in</Link>
          </div>
        )}

        {state === "done" && (
          <div data-testid="invite-done">
            <CheckCircle size={32} weight="duotone" className="text-[var(--success)] mb-3" />
            <h1 className="font-display font-bold tracking-tighter text-2xl mb-2 text-[var(--ink)]">Password set</h1>
            <p className="text-sm text-[var(--ink-2)] leading-relaxed mb-6">
              Sign in with <b>{invite?.email}</b> and your new password. You will then set a
              6-digit App PIN for this device.
            </p>
            <Link to="/login" className="btn-primary w-full justify-center py-2.5" data-testid="invite-signin">
              Sign in
            </Link>
          </div>
        )}

        {state === "ready" && invite && (
          <>
            <h1 className="font-display font-bold tracking-tighter text-2xl mb-2 text-[var(--ink)]">
              {isReset ? "Choose a new password" : `Set up your ${invite.workspace || "workspace"} account`}
            </h1>
            <p className="text-sm text-[var(--ink-2)] leading-relaxed mb-6">
              {invite.name ? `${invite.name}, choose` : "Choose"} a password for <b>{invite.email}</b>.
              Only you will know it.
            </p>
            <form onSubmit={submit} className="space-y-3">
              <input type="email" value={invite.email || ""} autoComplete="username" readOnly hidden />
              <label className="block">
                <span className="sr-only">New password</span>
                <div className="relative">
                  <LockKey size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--ink-3)] pointer-events-none" />
                  <input required type="password" autoComplete="new-password" minLength={8} maxLength={128}
                         className="input-flat w-full pl-9" placeholder="New password"
                         value={pw} onChange={(e) => setPw(e.target.value)} data-testid="invite-password" />
                </div>
              </label>
              <label className="block">
                <span className="sr-only">Confirm password</span>
                <div className="relative">
                  <LockKey size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--ink-3)] pointer-events-none" />
                  <input required type="password" autoComplete="new-password" minLength={8} maxLength={128}
                         className="input-flat w-full pl-9" placeholder="Confirm password"
                         value={pw2} onChange={(e) => setPw2(e.target.value)} data-testid="invite-password-confirm" />
                </div>
              </label>
              <p className="text-[11px] text-[var(--ink-3)]">At least 8 characters, with letters and digits.</p>
              {err && (
                <div role="alert" className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 rounded-lg flex items-center gap-2">
                  <Warning size={13} /> {err}
                </div>
              )}
              <button type="submit" disabled={busy} className="btn-primary w-full justify-center py-2.5" data-testid="invite-submit">
                {busy ? "Saving…" : "Set password"}
              </button>
            </form>
            {invite.expires_at && (
              <p className="mt-4 text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">
                Link expires {new Date(invite.expires_at).toLocaleString()}
              </p>
            )}
          </>
        )}
      </div>
    </main>
  );
}
