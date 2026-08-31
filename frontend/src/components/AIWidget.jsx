import { useEffect, useRef, useState } from "react";
import { ChatCircleDots, X, PaperPlaneTilt, Sparkle, Lightning } from "@phosphor-icons/react";
import api from "../lib/api";

const SUGGESTIONS = [
  "Summarise this week's pipeline",
  "Which projects are at risk?",
  "Draft a follow-up for the Studio North lead",
  "What's pending on the Menon residence?",
];

export default function AIWidget() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hello. I'm Saga AI — I know every project, lead and task in your studio.\n\nAsk me anything, or tap a suggestion below to start." },
  ]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [messages, loading]);

  useEffect(() => {
    if (open && inputRef.current) {
      setTimeout(() => inputRef.current.focus(), 200);
    }
  }, [open]);

  const send = async (textOverride) => {
    const text = (textOverride ?? msg).trim();
    if (!text || loading) return;
    setMsg("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const { data } = await api.post("/ai/chat", { message: text, session_id: sessionId });
      setSessionId(data.session_id);
      setMessages((m) => [...m, { role: "assistant", content: data.response }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "I hit a snag. Please try again in a moment." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/20 backdrop-blur-[2px] z-30 fade-in no-print"
          onClick={() => setOpen(false)}
        />
      )}

      {/* FAB */}
      <button
        data-testid="ai-widget-toggle"
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 z-40 bg-[#8B7F6A] text-white p-4 hover:bg-[#76705E] transition-all no-print"
        style={{
          boxShadow: open ? "0 4px 16px rgba(0,47,167,0.25)" : "0 12px 40px rgba(0,47,167,0.40)",
          transform: open ? "scale(0.92)" : "scale(1)",
        }}
        aria-label="Open Saga AI"
      >
        <div className="relative">
          {open ? <X size={22} weight="bold" /> : <ChatCircleDots size={22} weight="fill" />}
          {!open && (
            <div
              className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-[#1D633E] rounded-full"
              style={{ animation: "pulse-dot 1.5s ease-in-out infinite", boxShadow: "0 0 0 2px #8B7F6A" }}
            />
          )}
        </div>
      </button>

      {/* Panel */}
      {open && (
        <div
          className="fixed bottom-24 right-6 z-40 w-[440px] max-w-[calc(100vw-3rem)] h-[600px] max-h-[calc(100vh-8rem)] bg-white border border-[#E5E5E5] flex flex-col scale-in no-print"
          style={{ boxShadow: "0 30px 80px rgba(0,0,0,0.18)" }}
          data-testid="ai-widget-panel"
        >
          {/* Header */}
          <div className="relative overflow-hidden bg-[#8B7F6A] text-white">
            <div className="absolute inset-0 opacity-20 diagonal-stripes" />
            <div className="relative p-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-white/15 backdrop-blur-sm flex items-center justify-center">
                  <Sparkle size={20} weight="fill" />
                </div>
                <div>
                  <div className="font-display font-bold text-base tracking-tight flex items-center gap-2">
                    SAGA AI
                    <span className="bg-white/20 text-[9px] px-1.5 py-0.5 font-mono tracking-widest">BETA</span>
                  </div>
                  <div className="text-[10px] font-mono tracking-widest opacity-80 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-[#5BE584] rounded-full" style={{ animation: "pulse-dot 1.5s ease-in-out infinite" }} />
                    CLAUDE 4.5 · LIVE
                  </div>
                </div>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Close" className="hover:opacity-80 p-2 -m-2">
                <X size={18} weight="bold" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={boxRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#FAFAFA]" data-testid="ai-messages">
            {messages.map((m, i) => (
              <div key={i} className={`max-w-[88%] ${m.role === "user" ? "ml-auto" : ""} fade-up`} style={{ animationDelay: `${i * 30}ms` }}>
                <div className={`text-[9px] font-mono tracking-widest uppercase font-semibold mb-1.5 flex items-center gap-1.5 ${m.role === "user" ? "justify-end text-[#8B7F6A]" : "text-[#5C5C5C]"}`}>
                  {m.role === "user" ? "YOU" : (
                    <>
                      <Sparkle size={9} weight="fill" />
                      SAGA AI
                    </>
                  )}
                </div>
                <div
                  className={`text-sm leading-relaxed whitespace-pre-wrap border p-3 ${
                    m.role === "user"
                      ? "bg-[#8B7F6A] text-white border-[#8B7F6A]"
                      : "bg-white text-[#0A0A0A] border-[#E5E5E5]"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="max-w-[88%] fade-up">
                <div className="text-[9px] font-mono tracking-widest uppercase font-semibold mb-1.5 flex items-center gap-1.5 text-[#5C5C5C]">
                  <Sparkle size={9} weight="fill" />
                  SAGA AI · THINKING
                </div>
                <div className="text-sm border border-[#E5E5E5] p-3 bg-white flex items-center gap-1">
                  <div className="w-1.5 h-1.5 bg-[#8B7F6A] rounded-full" style={{ animation: "pulse-dot 0.9s ease-in-out infinite" }} />
                  <div className="w-1.5 h-1.5 bg-[#8B7F6A] rounded-full" style={{ animation: "pulse-dot 0.9s ease-in-out infinite", animationDelay: "0.15s" }} />
                  <div className="w-1.5 h-1.5 bg-[#8B7F6A] rounded-full" style={{ animation: "pulse-dot 0.9s ease-in-out infinite", animationDelay: "0.3s" }} />
                </div>
              </div>
            )}

            {/* Suggestions on first open only */}
            {messages.length === 1 && !loading && (
              <div className="pt-2">
                <div className="overline mb-2">QUICK ASKS</div>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="text-xs px-3 py-1.5 border border-[#E5E5E5] hover:border-[#8B7F6A] hover:text-[#8B7F6A] bg-white transition flex items-center gap-1.5"
                    >
                      <Lightning size={10} /> {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => { e.preventDefault(); send(); }}
            className="border-t border-[#E5E5E5] p-3 flex items-center gap-2 bg-white"
          >
            <input
              ref={inputRef}
              data-testid="ai-input"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder="Ask about any project, lead or task…"
              className="input-flat flex-1"
            />
            <button type="submit" className="btn-primary" data-testid="ai-send-btn" disabled={loading || !msg.trim()}>
              <PaperPlaneTilt size={16} weight="fill" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
