import { useAuth } from "../context/AuthContext";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
  const { loading, user } = useAuth();

  const handleGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading…</div>;

  if (user) {
    window.location.href = "/dashboard";
    return null;
  }

  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-white">
      {/* Left: form */}
      <div className="flex flex-col justify-between p-10 lg:p-16 border-r border-[#E5E5E5]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-[#002FA7] flex items-center justify-center">
            <span className="text-white font-display font-bold text-sm">DS</span>
          </div>
          <span className="font-display font-bold tracking-tight text-lg">DESIGN SAGA</span>
        </div>

        <div className="max-w-md">
          <div className="overline mb-6">01 / Studio Login</div>
          <h1 className="font-display font-bold tracking-tight text-5xl lg:text-6xl leading-[0.95] mb-6">
            Run your<br/>design studio<br/>like a <span className="accent-blue">masterpiece.</span>
          </h1>
          <p className="text-[#5C5C5C] text-base leading-relaxed mb-10 max-w-sm">
            CRM, projects, drawings, invoices and AI — one calm, editorial command centre for architecture & interior firms.
          </p>

          <button
            data-testid="login-google-btn"
            onClick={handleGoogle}
            className="btn-primary w-full justify-center"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M22.5 12.27c0-.8-.07-1.57-.2-2.3H12v4.36h5.9c-.25 1.37-1.03 2.53-2.2 3.31v2.74h3.56c2.08-1.92 3.24-4.75 3.24-8.11z" fill="#fff"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.74c-.98.66-2.24 1.05-3.72 1.05-2.86 0-5.29-1.93-6.15-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#fff" opacity=".85"/>
              <path d="M5.85 14.12c-.22-.66-.35-1.37-.35-2.12s.13-1.46.35-2.12V7.04H2.18A10.99 10.99 0 001 12c0 1.77.42 3.45 1.18 4.96l3.67-2.84z" fill="#fff" opacity=".7"/>
              <path d="M12 5.36c1.62 0 3.07.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.04l3.67 2.84C6.71 7.29 9.14 5.36 12 5.36z" fill="#fff" opacity=".55"/>
            </svg>
            Sign in with Google
          </button>

          <p className="mt-6 text-xs text-[#5C5C5C] font-mono tracking-wider">
            BY CONTINUING, YOU AGREE TO THE STUDIO TERMS.
          </p>
        </div>

        <div className="flex items-center justify-between text-xs text-[#5C5C5C] font-mono tracking-wider">
          <span>© {new Date().getFullYear()} DESIGN SAGA</span>
          <span>v0.1 — BETA</span>
        </div>
      </div>

      {/* Right: hero image */}
      <div className="hidden lg:block relative overflow-hidden">
        <img
          src="https://images.unsplash.com/photo-1771450092348-3185c8fb889a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODd8MHwxfHNlYXJjaHwyfHxtb2Rlcm4lMjBtaW5pbWFsaXN0JTIwYXJjaGl0ZWN0dXJlJTIwaW50ZXJpb3J8ZW58MHx8fHwxNzc2NDM1MDg3fDA&ixlib=rb-4.1.0&q=85"
          alt="Studio"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-black/30" />
        <div className="absolute bottom-10 left-10 right-10 text-white">
          <div className="overline text-white/80 mb-3">THE SAGA</div>
          <p className="font-display tracking-tight text-3xl leading-tight max-w-md">
            "Good design is obvious. Great design is transparent."
          </p>
          <p className="mt-3 text-sm text-white/80 font-mono">— J. NIELSEN</p>
        </div>
      </div>
    </div>
  );
}
