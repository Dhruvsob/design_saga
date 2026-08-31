import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import {
  ArrowRight, GoogleLogo, Sparkle, ShieldCheck, LockKey, User, Warning,
} from "@phosphor-icons/react";

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
      await loginWithPassword(identifier.trim(), password);
      window.location.href = "/dashboard";
    } catch (ex) {
      setErr(extractError(ex?.response?.data?.detail, "Login failed"));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="overline live-dot">LOADING</div>
      </div>
    );
  }

  if (user) {
    window.location.href = "/dashboard";
    return null;
  }

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-white">
      {/* ============== LEFT: form ============== */}
      <div className="flex flex-col justify-between p-10 lg:p-16 border-r border-[#E5E5E5] relative overflow-hidden">
        <div className="absolute inset-0 dotted-bg opacity-30 pointer-events-none" />

        <div className="relative flex items-center justify-between fade-up">
          <div className="flex items-center gap-3">
            <div className="relative w-9 h-9 bg-[#8B7F6A] flex items-center justify-center">
              <span className="text-white font-display font-bold text-sm">DS</span>
              <div className="absolute -top-1 -right-1 w-2 h-2 bg-[#1D633E] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
            </div>
            <span className="font-display font-bold tracking-tighter text-lg">DESIGN SAGA</span>
          </div>
          <div className="overline hidden md:flex items-center gap-2 live-dot">SYSTEM ONLINE</div>
        </div>

        <div className="relative max-w-md fade-up" style={{ animationDelay: "120ms" }}>
          <div className="overline mb-6 flex items-center gap-3">
            <span className="font-bold">01 / STUDIO LOGIN</span>
            <span className="h-px flex-1 bg-[#E5E5E5]" />
          </div>

          <h1 className="font-display font-bold tracking-tighter text-5xl lg:text-6xl leading-[0.92] mb-6">
            Run your<br/>
            design studio<br/>
            like a <span className="accent-blue relative inline-block">masterpiece
              <span className="absolute -bottom-2 left-0 right-0 h-1 bg-[#8B7F6A]" />
            </span>.
          </h1>

          <p className="text-[#5C5C5C] text-base leading-relaxed mb-8 max-w-sm">
            CRM, projects, drawings, invoices and AI — one calm, editorial command centre for architecture &amp; interior firms.
          </p>

          {/* Google button */}
          <button
            data-testid="login-google-btn"
            type="button"
            onClick={handleGoogle}
            className="btn-primary w-full justify-center text-base py-3.5 group"
            style={{ fontSize: 14 }}
          >
            <GoogleLogo size={18} weight="bold" />
            Sign in with Google
            <ArrowRight size={14} className="ml-1 transition-transform group-hover:translate-x-1" />
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="h-px flex-1 bg-[#E5E5E5]" />
            <div className="overline text-[10px]">OR STUDIO ID</div>
            <div className="h-px flex-1 bg-[#E5E5E5]" />
          </div>

          {/* Password form */}
          <form onSubmit={handlePasswordLogin} className="space-y-3" data-testid="password-login-form">
            <div className="flex items-center gap-2 border border-[#E5E5E5] px-3 py-2.5 focus-within:border-[#8B7F6A] transition bg-white">
              <User size={14} className="text-[#5C5C5C]" />
              <input
                required
                data-testid="login-identifier"
                className="flex-1 outline-none text-sm bg-transparent"
                placeholder="Email or Employee ID (e.g. DS0001)"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="flex items-center gap-2 border border-[#E5E5E5] px-3 py-2.5 focus-within:border-[#8B7F6A] transition bg-white">
              <LockKey size={14} className="text-[#5C5C5C]" />
              <input
                required
                type="password"
                data-testid="login-password"
                className="flex-1 outline-none text-sm bg-transparent"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {err && (
              <div
                className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 flex items-center gap-2"
                data-testid="login-error"
              >
                <Warning size={13} /> {err}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              data-testid="login-password-btn"
              className="w-full py-2.5 bg-[#0A0A0A] text-white text-sm font-semibold hover:bg-[#8B7F6A] transition disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in with password"}
            </button>
          </form>

          {/* Trust badges */}
          <div className="mt-6 flex flex-wrap items-center gap-4 text-xs text-[#5C5C5C]">
            <div className="flex items-center gap-1.5">
              <ShieldCheck size={12} weight="duotone" className="text-[#1D633E]" />
              <span className="font-mono tracking-wider uppercase">SOC-2 READY</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Sparkle size={12} weight="duotone" className="text-[#8B7F6A]" />
              <span className="font-mono tracking-wider uppercase">AI-NATIVE</span>
            </div>
          </div>
        </div>

        <div className="relative flex items-center justify-between text-xs text-[#5C5C5C] font-mono tracking-wider fade-up" style={{ animationDelay: "240ms" }}>
          <span>© {new Date().getFullYear()} DESIGN SAGA</span>
          <span>v2.2 — BETA</span>
        </div>
      </div>

      {/* ============== RIGHT: hero image ============== */}
      <div className="hidden lg:block relative overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1771450092348-3185c8fb889a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODd8MHwxfHNlYXJjaHwyfHxtb2Rlcm4lMjBtaW5pbWFsaXN0JTIwYXJjaGl0ZWN0dXJlJTIwaW50ZXJpb3J8ZW58MHx8fHwxNzc2NDM1MDg3fDA&ixlib=rb-4.1.0&q=85"
          alt="Studio"
          className="absolute inset-0 w-full h-full object-cover scale-105"
          style={{ animation: "fade-in 1200ms ease-out" }}
        />
        <div className="absolute inset-0 bg-gradient-to-br from-[#8B7F6A]/30 via-transparent to-black/60" />

        <div className="absolute top-10 left-10 right-10 flex items-center justify-between">
          <div className="overline text-white/90">REEL · 001</div>
          <div className="overline text-white/90 flex items-center gap-2">
            <span className="w-2 h-2 bg-[#FF2A00] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
            REC
          </div>
        </div>

        <div className="absolute bottom-10 left-10 right-10 text-white fade-up" style={{ animationDelay: "300ms" }}>
          <div className="overline text-white/70 mb-3 flex items-center gap-3">
            THE SAGA <span className="h-px w-12 bg-white/40" />
          </div>
          <p className="font-display tracking-tighter text-3xl xl:text-4xl leading-tight max-w-md">
            "Good design is obvious.<br/>Great design is transparent."
          </p>
          <p className="mt-4 text-sm text-white/80 font-mono tracking-widest">— J. NIELSEN</p>
        </div>

        <div className="absolute inset-6 border border-white/15 pointer-events-none" />
      </div>
    </div>
  );
}
