import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../lib/api";
import { ArrowLeft, Copy, Plus } from "@phosphor-icons/react";

const STAGES = ["Requirement", "Concept", "Design Dev", "Tech Drawings", "Review", "Signoff", "Procurement", "Execution", "Handover"];
const TABS = ["Overview", "Tasks", "Files", "Invoices"];

export default function ProjectDetail() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [tab, setTab] = useState("Overview");
  const [loading, setLoading] = useState(true);
  const [fileForm, setFileForm] = useState({ name: "", url: "", stage: "" });
  const [showFileForm, setShowFileForm] = useState(false);

  const load = async () => {
    setLoading(true);
    const { data } = await api.get(`/projects/${id}`);
    setP(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, [id]);

  const setStage = async (stage) => {
    await api.patch(`/projects/${id}/stage`, { stage });
    load();
  };

  const copyShare = () => {
    const url = `${window.location.origin}/portal/${p.share_token}`;
    navigator.clipboard.writeText(url);
    alert("Shareable link copied to clipboard!\n\n" + url);
  };

  const addFile = async (e) => {
    e.preventDefault();
    await api.post("/files", { ...fileForm, project_id: id });
    setFileForm({ name: "", url: "", stage: "" });
    setShowFileForm(false);
    load();
  };

  if (loading || !p) return <div className="overline">LOADING…</div>;

  const currentIdx = STAGES.indexOf(p.stage || "Requirement");

  return (
    <div className="space-y-8" data-testid="project-detail">
      <Link to="/projects" className="inline-flex items-center gap-1 text-sm text-[#5C5C5C] hover:text-[#0A0A0A]">
        <ArrowLeft size={14} /> Back to projects
      </Link>

      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="overline mb-2">{p.project_type} · {p.client_name || "—"}</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">{p.name}</h1>
          {p.description && <p className="mt-2 text-[#5C5C5C] max-w-2xl">{p.description}</p>}
        </div>
        <button onClick={copyShare} className="btn-ghost" data-testid="share-portal-btn">
          <Copy size={14} /> Copy client portal link
        </button>
      </div>

      {/* Stage tracker */}
      <div className="border border-[#E5E5E5] p-6 bg-white" data-testid="stage-tracker">
        <div className="overline mb-4">LIFECYCLE STAGE</div>
        <div className="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-9 gap-1">
          {STAGES.map((s, i) => {
            const done = i < currentIdx;
            const current = i === currentIdx;
            return (
              <button
                key={s}
                onClick={() => setStage(s)}
                className={`p-2 text-[10px] font-mono uppercase tracking-wider border text-left transition ${
                  current ? "bg-[#002FA7] text-white border-[#002FA7]"
                  : done ? "bg-[#0A0A0A] text-white border-[#0A0A0A]"
                  : "bg-white text-[#5C5C5C] border-[#E5E5E5] hover:border-[#0A0A0A]"
                }`}
                data-testid={`stage-${s}`}
              >
                <div className="opacity-60">STEP {i + 1}</div>
                <div className="font-semibold">{s}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-[#E5E5E5]">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition ${
              tab === t ? "border-[#002FA7] text-[#002FA7]" : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"
            }`}
            data-testid={`tab-${t}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-0 border-t border-l border-[#E5E5E5]">
          <MiniStat label="Budget" value={`₹${(p.budget || 0).toLocaleString("en-IN")}`} />
          <MiniStat label="Tasks" value={`${(p.tasks || []).length}`} />
          <MiniStat label="Files" value={`${(p.files || []).length}`} />
        </div>
      )}

      {tab === "Tasks" && (
        <div className="space-y-2">
          {(p.tasks || []).length === 0 && <p className="text-[#5C5C5C] text-sm">No tasks yet. Add them from the Tasks page.</p>}
          {(p.tasks || []).map((t) => (
            <div key={t.id} className="border border-[#E5E5E5] p-3 flex items-center justify-between">
              <div>
                <div className="font-semibold text-sm">{t.title}</div>
                <div className="text-xs text-[#5C5C5C]">Due {t.due_date || "—"} · {t.assignee_name}</div>
              </div>
              <span className={`status-chip chip-${t.priority}`}>{t.priority}</span>
            </div>
          ))}
        </div>
      )}

      {tab === "Files" && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => setShowFileForm(!showFileForm)} className="btn-primary" data-testid="add-file-btn">
              <Plus size={14} /> Add file link
            </button>
          </div>
          {showFileForm && (
            <form onSubmit={addFile} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3">
              <input className="input-flat" placeholder="File name" required value={fileForm.name} onChange={(e) => setFileForm({ ...fileForm, name: e.target.value })} />
              <input className="input-flat" placeholder="URL" required value={fileForm.url} onChange={(e) => setFileForm({ ...fileForm, url: e.target.value })} />
              <input className="input-flat" placeholder="Stage (e.g. Concept)" value={fileForm.stage} onChange={(e) => setFileForm({ ...fileForm, stage: e.target.value })} />
              <button className="btn-primary md:col-span-3">Save</button>
            </form>
          )}
          {(p.files || []).length === 0 && <p className="text-[#5C5C5C] text-sm">No files yet.</p>}
          {(p.files || []).map((f) => (
            <a key={f.id} href={f.url} target="_blank" rel="noreferrer" className="block border border-[#E5E5E5] p-3 hover:border-[#0A0A0A] transition">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-sm">{f.name}</div>
                  <div className="text-xs text-[#5C5C5C]">{f.stage || "—"} · v{f.version || 1} · {f.uploader_name}</div>
                </div>
                <span className="overline">OPEN →</span>
              </div>
            </a>
          ))}
        </div>
      )}

      {tab === "Invoices" && (
        <div className="space-y-2">
          {(p.invoices || []).length === 0 && <p className="text-[#5C5C5C] text-sm">No invoices yet.</p>}
          {(p.invoices || []).map((i) => (
            <div key={i.id} className="border border-[#E5E5E5] p-3 flex items-center justify-between">
              <div>
                <div className="font-mono font-semibold text-sm">{i.number}</div>
                <div className="text-xs text-[#5C5C5C]">{i.doc_type} · Due {i.due_date || "—"}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="font-mono font-semibold">₹{(i.total || 0).toLocaleString("en-IN")}</div>
                <span className={`status-chip chip-${i.status}`}>{i.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="border-r border-b border-[#E5E5E5] p-5">
      <div className="overline mb-2">{label}</div>
      <div className="font-display font-bold tracking-tight text-3xl">{value}</div>
    </div>
  );
}
