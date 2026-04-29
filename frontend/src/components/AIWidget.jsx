import { useEffect, useRef, useState } from "react";
import { ChatCircleDots, X, PaperPlaneTilt, Sparkle } from "@phosphor-icons/react";
import api from "../lib/api";

export default function AIWidget() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hello. I'm Saga AI — I know every project, lead and task in your studio. What can I help with?" },
  ]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const boxRef = useRef(null);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [messages, loading]);

  const send = async () => {
    if (!msg.trim() || loading) return;
    const text = msg.trim();
    setMsg("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const { data } = await api.post("/ai/chat", { message: text, session_id: sessionId });
      setSessionId(data.session_id);
      setMessages((m) => [...m, { role: "assistant", content: data.response }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: "I hit a snag. Please try again in a moment." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        data-testid="ai-widget-toggle"
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 z-40 bg-[#002FA7] text-white p-4 hover:bg-[#001F70] transition shadow-lg"
        style={{ boxShadow: "0 10px 40px rgba(0,47,167,0.35)" }}
        aria-label="Open Saga AI"
      >
        {open ? <X size={22} weight="bold" /> : <ChatCircleDots size={22} weight="fill" />}
      </button>

      {open && (
        <div
          className="fixed bottom-24 right-6 z-40 w-[400px] max-w-[calc(100vw-3rem)] h-[540px] bg-white border border-[#E5E5E5] flex flex-col"
          style={{ boxShadow: "0 20px 60px rgba(0,0,0,0.12)" }}
          data-testid="ai-widget-panel"
        >
          <div className="p-4 border-b border-[#E5E5E5] flex items-center justify-between bg-[#002FA7] text-white">
            <div className="flex items-center gap-2">
              <Sparkle size={18} weight="fill" />
              <div>
                <div className="font-display font-bold text-sm tracking-tight">SAGA AI</div>
                <div className="text-[10px] font-mono tracking-widest opacity-80">CLAUDE 4.5 · LIVE</div>
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close" className="hover:opacity-80">
              <X size={18} />
            </button>
          </div>

          <div ref={boxRef} className="flex-1 overflow-y-auto p-4 space-y-3" data-testid="ai-messages">
            {messages.map((m, i) => (
              <div key={i} className={`max-w-[85%] ${m.role === "user" ? "ml-auto" : ""}`}>
                <div className="overline mb-1">
                  {m.role === "user" ? "YOU" : "SAGA AI"}
                </div>
                <div
                  className={`text-sm leading-relaxed whitespace-pre-wrap border p-3 ${
                    m.role === "user"
                      ? "bg-[#002FA7] text-white border-[#002FA7]"
                      : "bg-white text-[#0A0A0A] border-[#E5E5E5]"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="max-w-[85%]">
                <div className="overline mb-1">SAGA AI</div>
                <div className="text-sm border border-[#E5E5E5] p-3 text-[#5C5C5C]">Thinking…</div>
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); send(); }}
            className="border-t border-[#E5E5E5] p-3 flex items-center gap-2"
          >
            <input
              data-testid="ai-input"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder="Ask about any project, lead or task…"
              className="input-flat flex-1"
            />
            <button type="submit" className="btn-primary" data-testid="ai-send-btn" disabled={loading}>
              <PaperPlaneTilt size={16} weight="fill" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
