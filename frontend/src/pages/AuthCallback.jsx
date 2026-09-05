import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api, { setSessionToken } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash || "";
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const sessionId = params.get("session_id");

    if (!sessionId) {
      navigate("/", { replace: true });
      return;
    }

    (async () => {
      try {
        const { data } = await api.post(
          "/auth/session",
          { session_id: sessionId },
          { headers: { "X-Session-ID": sessionId } }
        );
        if (data.session_token) setSessionToken(data.session_token);
        setUser(data.user);
        // clear hash
        window.history.replaceState(null, "", "/dashboard");
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch (e) {
        console.error("Auth callback failed", e);
        navigate("/", { replace: true });
      }
    })();
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="overline mb-4">AUTHENTICATING</div>
        <div className="font-display text-2xl tracking-tight">Signing you in…</div>
      </div>
    </div>
  );
}
