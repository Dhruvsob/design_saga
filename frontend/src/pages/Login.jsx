import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../lib/api";
import { forgetWorkspace, isWorkspaceSlug, rememberedWorkspace, rememberWorkspace } from "../lib/workspace";
import { GoogleLogo, LockKey, User, Warning } from "@phosphor-icons/react";

/** The studio this device last signed in to (or `?workspace=<short-name>`),
 *  shown so staff recognise their own workspace on the shared Gamaa sign-in. */
function useWorkspaceBrand() {
  const [params] = useSearchParams();
  const [ws, setWs] = useState(null);
  const asked = params.get("workspace");
  useEffect(() => {
    const slug = isWorkspaceSlug(asked) ? asked : rememberedWorkspace();
    if (!slug) return undefined;
    let alive = true;
    api.get(`/org/public/${slug}`)
      .then(({ data }) => {
        if (!alive) return;
        setWs(data);
        if (asked) rememberWorkspace(slug);
      })
      .catch((e) => { if (e?.response?.status === 404) forgetWorkspace(); });
    return () => { alive = false; };
  }, [asked]);
  const clear = () => { forgetWorkspace(); setWs(null); };
  return [ws, clear];
}

function initialsOf(name) {
  return String(name || "").split(/\s+/).filter(Boolean).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase() || "G";
}

function extractError(detail, fallback = "Something went wrong.") {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (e?.msg ? e.msg : String(e))).join(" · ");
  }
  return typeof detail === "object" ? (detail.msg || fallback) : String(detail);
}

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
  const { loading, user, loginWithPassword } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [ws, clearWs] = useWorkspaceBrand();
  const [logoFailed, setLogoFailed] = useState(false);
  const wsName = ws?.display_name || ws?.name || "";
  const wsLogo = !logoFailed && ws?.branding?.logo_url;

  const handleGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handlePasswordLogin = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await loginWithPassword(identifier.trim(), password, ws?.slug);
      window.location.href = "/dashboard";
    } catch (ex) {
      setErr(extractError(ex?.response?.data?.detail, "Login failed"));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--app)" }}>
        <div className="overline live-dot">LOADING</div>
      </div>
    );
  }

  if (user) {
    window.location.href = "/dashboard";
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">

      {/* ===== LEFT PANEL: cream — form ===== */}
      <div
        className="flex flex-col justify-between w-full lg:max-w-[520px] min-h-screen p-10 lg:p-14 fade-up"
        style={{ background: "var(--app)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0" data-testid="login-brand">
            {wsLogo ? (
              <img src={wsLogo} alt="" aria-hidden="true" onError={() => setLogoFailed(true)}
                   className="w-10 h-10 rounded-xl object-contain bg-white border border-[var(--line)] p-1 shrink-0" />
            ) : (
              <div
                className="relative w-10 h-10 flex items-center justify-center rounded-xl shrink-0"
                style={{
                  background: "linear-gradient(145deg, #9A8F7A 0%, #76705E 100%)",
                  boxShadow: "0 4px 14px -4px rgba(91,78,58,0.5), inset 0 1px 0 rgba(255,255,255,0.22)",
                }}
              >
                <span className="text-white font-display font-bold text-sm select-none">{wsName ? initialsOf(wsName) : "G"}</span>
                <span
                  className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-[var(--success)] rounded-full border-2 border-white"
                  style={{ animation: "pulse-dot 2s ease-in-out infinite" }}
                />
              </div>
            )}
            <div className="min-w-0">
              <div className="font-display font-bold tracking-tight text-[18px] leading-tight text-[var(--ink)] truncate" data-testid="login-brand-name">
                {wsName || "Gamaa"}
              </div>
              <div className="text-[9px] font-mono tracking-[0.18em] uppercase text-[var(--ink-3)]">
                {wsName ? "Studio workspace · on Gamaa" : "Architecture & Interior ERP"}
              </div>
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)]" style={{ animation: "pulse-dot 2s ease-in-out infinite" }} />
            System Online
          </div>
        </div>

        {/* Form section */}
        <div className="max-w-[400px]">
          <div className="overline mb-4 text-[var(--accent-strong)]">{wsName ? "Studio sign-in" : "Studio Login"}</div>
          <h1 className="font-display font-bold tracking-tighter text-[2.5rem] leading-[1.1] mb-3 text-[var(--ink)]">
            {wsName ? (<>Sign in to<br /><span className="break-words">{wsName}</span></>) : (<>Your studio,<br />in one place.</>)}
          </h1>
          <p className="text-sm text-[var(--ink-2)] leading-relaxed mb-8 max-w-[320px]">
            {wsName ? (
              <>Not your studio?{" "}
                <button type="button" onClick={clearWs} className="underline underline-offset-4 hover:text-[var(--ink)]"
                        data-testid="login-other-workspace">Use another workspace</button>
              </>
            ) : "Projects, clients, finances and team — a single calm workspace for architecture & interior design firms."}
          </p>

          {/* Google SSO */}
          <button
            data-testid="login-google-btn"
            type="button"
            onClick={handleGoogle}
            className="btn-primary w-full justify-center gap-2.5 py-3 mb-5"
            style={{ fontSize: 14 }}
          >
            <GoogleLogo size={17} weight="bold" />
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-5">
            <div className="h-px flex-1 bg-[var(--line)]" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">or Studio ID</span>
            <div className="h-px flex-1 bg-[var(--line)]" />
          </div>

          {/* ID + Password form */}
          <form onSubmit={handlePasswordLogin} className="space-y-3" data-testid="password-login-form">
            <div className="relative">
              <User size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--ink-3)] pointer-events-none" />
              <input
                required
                data-testid="login-identifier"
                className="input-flat w-full pl-9"
                placeholder="Email or Employee ID"
                aria-label="Email or Employee ID"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="relative">
              <LockKey size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--ink-3)] pointer-events-none" />
              <input
                required
                type="password"
                data-testid="login-password"
                className="input-flat w-full pl-9"
                placeholder="Password"
                aria-label="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {err && (
              <div
                className="border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2 rounded-lg flex items-center gap-2"
                data-testid="login-error"
                role="alert"
              >
                <Warning size={13} /> {err}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              data-testid="login-password-btn"
              className="btn-ghost w-full justify-center py-2.5"
            >
              {busy ? "Signing in…" : "Sign in with password"}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-widest text-[var(--ink-3)]">
          <span>© {new Date().getFullYear()} Gamaa</span>
          <span className="h-3 w-px bg-[var(--line)]" />
          <Link to="/privacy" className="hover:text-[var(--ink)] transition-colors">Privacy</Link>
          <span className="h-3 w-px bg-[var(--line)]" />
          <span>v0.2</span>
        </div>
      </div>

      {/* ===== RIGHT PANEL: brand brown — marketing ===== */}
      <div
        className="hidden lg:flex flex-1 flex-col justify-between p-14 relative overflow-hidden"
        style={{ background: "linear-gradient(150deg, #76705E 0%, #5F5A4B 45%, #2C2820 100%)" }}
        aria-hidden="true"
      >
        {/* Subtle pattern: faint architectural grid lines */}
        <svg className="absolute inset-0 w-full h-full opacity-[0.07]" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path d="M 48 0 L 0 0 0 48" fill="none" stroke="white" strokeWidth="0.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>

        {/* Top: tagline */}
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-white/50 mb-3">Architecture ERP</div>
          <div className="text-sm text-white/70 font-mono leading-relaxed">
            Manage every project from first brief<br />to final handover — in one system.
          </div>
        </div>

        {/* Middle: feature list */}
        <div className="space-y-3">
          {[
            { label: "Project & Phase Management", desc: "Full lifecycle from concept to delivery" },
            { label: "CRM & Collections", desc: "Clients, quotations, invoices, reminders" },
            { label: "Design Studio", desc: "Drawings, files, site visits & snag lists" },
            { label: "Procurement & Vendors", desc: "POs, bills, vendor incentives, payouts" },
            { label: "Team & Payroll", desc: "Attendance, leaves, payroll & expense claims" },
            { label: "Full Accounting", desc: "Books, reports, period close & GST ready" },
          ].map((f) => (
            <div key={f.label} className="flex items-start gap-3">
              <span className="mt-[3px] w-1.5 h-1.5 rounded-full bg-[var(--accent-soft)] shrink-0" />
              <div>
                <div className="text-sm font-semibold text-white/90">{f.label}</div>
                <div className="text-xs text-white/50">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Bottom: quote */}
        <div>
          <div className="h-px bg-white/20 mb-6 max-w-xs" />
          <p className="font-display tracking-tighter text-2xl xl:text-3xl leading-tight text-white/90 max-w-sm mb-4">
            &ldquo;Good design is obvious.<br />Great design is&nbsp;transparent.&rdquo;
          </p>
          <p className="text-xs text-white/50 font-mono tracking-widest">— Jakob Nielsen</p>
          <p className="mt-6 text-[10px] font-mono uppercase tracking-widest text-white/30">
            Trusted by architecture &amp; interior design studios
          </p>
        </div>
      </div>

    </div>
  );
}
