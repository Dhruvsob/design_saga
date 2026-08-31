import { useEffect, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { ChatCircleText, PaperPlaneRight, Trash } from "@phosphor-icons/react";

const relativeTime = (iso) => {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
};

export default function CommentsPanel({ entityType, entityId }) {
  const { user } = useAuth();
  const [comments, setComments] = useState([]);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const { data } = await api.get("/comments", { params: { entity_type: entityType, entity_id: entityId } });
      setComments(data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [entityType, entityId]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try {
      await api.post("/comments", { entity_type: entityType, entity_id: entityId, body: body.trim() });
      setBody("");
      await load();
    } finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this comment?")) return;
    await api.delete(`/comments/${id}`);
    load();
  };

  return (
    <div className="border border-[#E5E5E5]" data-testid="comments-panel">
      <div className="p-4 border-b border-[#E5E5E5] bg-[#FAFAFA] flex items-center gap-2">
        <ChatCircleText size={14} />
        <span className="overline">NOTES &amp; COMMENTS</span>
        <span className="font-mono text-xs text-[#9A9A9A] ml-auto">{comments.length}</span>
      </div>

      <div className="max-h-96 overflow-y-auto divide-y divide-[#F0F0F0]">
        {loading && <div className="p-4 text-xs font-mono uppercase tracking-wider text-[#9A9A9A]">Loading…</div>}
        {!loading && comments.length === 0 && (
          <div className="p-6 text-center text-sm text-[#9A9A9A]">No comments yet. Start the discussion.</div>
        )}
        {comments.map((c) => (
          <div key={c.id} className="p-4 group" data-testid={`comment-${c.id}`}>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-6 h-6 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-[10px]">
                {(c.author_name || "?").slice(0, 1).toUpperCase()}
              </div>
              <span className="text-sm font-semibold">{c.author_name}</span>
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#9A9A9A]">
                {c.author_role} · {relativeTime(c.created_at)}
              </span>
              {(c.author_id === user?.user_id || user?.role === "Admin") && (
                <button onClick={() => remove(c.id)} title="Delete"
                  className="ml-auto text-[#B22B22] opacity-0 group-hover:opacity-100 transition"
                  data-testid={`comment-delete-${c.id}`}>
                  <Trash size={12} />
                </button>
              )}
            </div>
            <p className="text-sm text-[#0A0A0A] whitespace-pre-wrap pl-8">{c.body}</p>
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="p-3 border-t border-[#E5E5E5] flex items-center gap-2">
        <input
          className="input-flat flex-1"
          placeholder="Write a note or comment…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          data-testid="comment-input"
        />
        <button className="btn-primary" disabled={busy || !body.trim()} data-testid="comment-submit">
          <PaperPlaneRight size={14} />
        </button>
      </form>
    </div>
  );
}
