import { useAuth } from "../context/AuthContext";
import { ArrowRight, GoogleLogo, Sparkle, ShieldCheck } from "@phosphor-icons/react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
  const { loading, user } = useAuth();

  const handleGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
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
        {/* Subtle grid background */}
        <div className="absolute inset-0 dotted-bg opacity-30 pointer-events-none" />

        {/* Header */}
        <div className="relative flex items-center justify-between fade-up">
          <div className="flex items-center gap-3">
            <div className="relative w-9 h-9 bg-[#002FA7] flex items-center justify-center">
              <span className="text-white font-display font-bold text-sm">DS</span>
              <div className="absolute -top-1 -right-1 w-2 h-2 bg-[#1D633E] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
            </div>
            <span className="font-display font-bold tracking-tighter text-lg">DESIGN SAGA</span>
          </div>
          <div className="overline hidden md:flex items-center gap-2 live-dot">SYSTEM ONLINE</div>
        </div>

        {/* Center */}
        <div className="relative max-w-md fade-up" style={{ animationDelay: "120ms" }}>
          <div className="overline mb-6 flex items-center gap-3">
            <span className="font-bold">01 / STUDIO LOGIN</span>
            <span className="h-px flex-1 bg-[#E5E5E5]" />
          </div>

          <h1 className="font-display font-bold tracking-tighter text-5xl lg:text-7xl leading-[0.92] mb-6">
            Run your<br/>
            design studio<br/>
            like a <span className="accent-blue relative inline-block">masterpiece
              <span className="absolute -bottom-2 left-0 right-0 h-1 bg-[#002FA7]" />
            </span>.
          </h1>

          <p className="text-[#5C5C5C] text-lg leading-relaxed mb-10 max-w-sm">
            CRM, projects, drawings, invoices and AI — one calm, editorial command centre for architecture & interior firms.
          </p>

          {/* Login button */}
          <button
            data-testid="login-google-btn"
            onClick={handleGoogle}
            className="btn-primary w-full justify-center text-base py-3.5 group"
            style={{ fontSize: 14 }}
          >
            <GoogleLogo size={18} weight="bold" />
            Sign in with Google
            <ArrowRight size={14} className="ml-1 transition-transform group-hover:translate-x-1" />
          </button>

          {/* Trust badges */}
          <div className="mt-6 flex flex-wrap items-center gap-4 text-xs text-[#5C5C5C]">
            <div className="flex items-center gap-1.5">
              <ShieldCheck size={12} weight="duotone" className="text-[#1D633E]" />
              <span className="font-mono tracking-wider uppercase">SOC-2 READY</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Sparkle size={12} weight="duotone" className="text-[#002FA7]" />
              <span className="font-mono tracking-wider uppercase">AI-NATIVE</span>
            </div>
            <span className="text-[#9A9A9A] font-mono tracking-wider uppercase">·  NO CREDIT CARD</span>
          </div>
        </div>

        {/* Footer */}
        <div className="relative flex items-center justify-between text-xs text-[#5C5C5C] font-mono tracking-wider fade-up" style={{ animationDelay: "240ms" }}>
          <span>© {new Date().getFullYear()} DESIGN SAGA</span>
          <span>v0.2 — BETA</span>
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
        <div className="absolute inset-0 bg-gradient-to-br from-[#002FA7]/30 via-transparent to-black/60" />

        {/* Side overline */}
        <div className="absolute top-10 left-10 right-10 flex items-center justify-between">
          <div className="overline text-white/90">REEL · 001</div>
          <div className="overline text-white/90 flex items-center gap-2">
            <span className="w-2 h-2 bg-[#FF2A00] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
            REC
          </div>
        </div>

        {/* Quote */}
        <div className="absolute bottom-10 left-10 right-10 text-white fade-up" style={{ animationDelay: "300ms" }}>
          <div className="overline text-white/70 mb-3 flex items-center gap-3">
            THE SAGA <span className="h-px w-12 bg-white/40" />
          </div>
          <p className="font-display tracking-tighter text-3xl xl:text-4xl leading-tight max-w-md">
            "Good design is obvious.<br/>Great design is transparent."
          </p>
          <p className="mt-4 text-sm text-white/80 font-mono tracking-widest">— J. NIELSEN</p>
        </div>

        {/* Frame */}
        <div className="absolute inset-6 border border-white/15 pointer-events-none" />
      </div>
    </div>
  );
}
