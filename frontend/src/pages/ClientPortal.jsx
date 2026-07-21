import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api, { API } from "../lib/api";

export default function ClientPortal() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/portal/${token}`);
        setData(data);
      } catch (e) {
        setErr("Invalid or expired link.");
      }
    })();
  }, [token]);

  const send = async (e) => {
    e.preventDefault();
    if (!msg.trim() || !name.trim()) return;
    await api.post(`/portal/${token}/message`, { from_name: name, message: msg });
    setSent(true);
    setMsg("");
  };

  if (err) return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="text-center">
        <div className="overline">LINK</div>
        <h1 className="font-display font-bold tracking-tight text-4xl">Not available</h1>
        <p className="text-[#5C5C5C] mt-2">{err}</p>
      </div>
    </div>
  );

  if (!data) return <div className="p-10 overline">LOADING…</div>;

  const { project, tasks_summary, files, invoices } = data;
  const stageIdx = project.all_stages.indexOf(project.stage);

  return (
    <div className="min-h-screen bg-white" data-testid="client-portal">
      {/* Header */}
      <div className="border-b border-[#E5E5E5] relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{ backgroundImage: 'url(https://images.pexels.com/photos/4458203/pexels-photo-4458203.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940)', backgroundSize: "cover", backgroundPosition: "center" }}
        />
        <div className="relative max-w-5xl mx-auto px-8 py-16">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-[#002FA7] flex items-center justify-center">
                <span className="text-white font-display font-bold text-xs">DS</span>
              </div>
              <span className="font-display font-bold tracking-tight">DESIGN SAGA</span>
            </div>
            <div className="overline">CLIENT PORTAL</div>
          </div>

          <div className="overline mb-3">{project.project_type} · {project.client_name || "Client"}</div>
          <h1 className="font-display font-bold tracking-tight text-5xl lg:text-6xl leading-[0.95] max-w-3xl">
            {project.name}
          </h1>
          {project.description && <p className="mt-4 text-[#5C5C5C] max-w-2xl text-lg">{project.description}</p>}
        </div>
      </div>

      {/* Progress */}
      <section className="max-w-5xl mx-auto px-8 py-12">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="overline mb-1">PROGRESS</div>
            <div className="font-display font-bold tracking-tight text-2xl">Stage: {project.stage}</div>
          </div>
          <div className="font-display font-bold tracking-tight text-5xl accent-blue">{project.progress}%</div>
        </div>
        <div className="h-1 bg-[#F0F0F0]">
          <div className="h-1 bg-[#002FA7]" style={{ width: `${project.progress}%` }} />
        </div>
        <div className="mt-6 grid grid-cols-3 md:grid-cols-9 gap-1">
          {project.all_stages.map((s, i) => (
            <div
              key={s}
              className={`p-2 text-[10px] font-mono uppercase tracking-wider border ${
                i < stageIdx ? "bg-[#0A0A0A] text-white border-[#0A0A0A]"
                : i === stageIdx ? "bg-[#002FA7] text-white border-[#002FA7]"
                : "bg-white text-[#5C5C5C] border-[#E5E5E5]"
              }`}
            >
              <div className="opacity-60">STEP {i + 1}</div>
              <div className="font-semibold">{s}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Grid */}
      <section className="max-w-5xl mx-auto px-8 pb-12 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card-flat">
          <div className="overline mb-2">TASKS</div>
          <div className="font-display font-bold text-4xl">{tasks_summary.done}/{tasks_summary.total}</div>
          <div className="text-sm text-[#5C5C5C] mt-2">{tasks_summary.in_progress} in progress</div>
        </div>
        <div className="card-flat">
          <div className="overline mb-2">FILES SHARED</div>
          <div className="font-display font-bold text-4xl">{files.length}</div>
          <div className="text-sm text-[#5C5C5C] mt-2">Review below</div>
        </div>
        <div className="card-flat">
          <div className="overline mb-2">INVOICES</div>
          <div className="font-display font-bold text-4xl">{invoices.length}</div>
          <div className="text-sm text-[#5C5C5C] mt-2">Track payment status</div>
        </div>
      </section>

      {/* Files */}
      <section className="max-w-5xl mx-auto px-8 pb-12">
        <div className="overline mb-3">DELIVERABLES / FILES</div>
        <div className="space-y-2">
          {files.length === 0 && <p className="text-[#5C5C5C] text-sm">No files shared yet.</p>}
          {files.map((f) => (
            <a key={f.id} href={f.url} target="_blank" rel="noreferrer" className="block border border-[#E5E5E5] p-4 hover:border-[#0A0A0A] transition">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">{f.name}</div>
                  <div className="text-xs text-[#5C5C5C] mt-1">{f.stage || "—"} · {(f.created_at || "").slice(0, 10)}</div>
                </div>
                <div className="overline">OPEN →</div>
              </div>
            </a>
          ))}
        </div>
      </section>

      {/* Invoices */}
      <section className="max-w-5xl mx-auto px-8 pb-12">
        <div className="overline mb-3">FINANCIALS</div>
        <div className="space-y-2">
          {invoices.length === 0 && <p className="text-[#5C5C5C] text-sm">No invoices yet.</p>}
          {invoices.map((i) => (
            <div key={i.id} className="border border-[#E5E5E5] p-4 flex items-center justify-between">
              <div>
                <div className="font-mono font-semibold">{i.number}</div>
                <div className="text-xs text-[#5C5C5C]">{i.doc_type} · Due {i.due_date || "—"}</div>
              </div>
              <div className="flex items-center gap-4">
                <div className="font-mono font-semibold">₹{(i.total || 0).toLocaleString("en-IN")}</div>
                <span className={`status-chip chip-${i.status}`}>{i.status}</span>
                <a href={`${API}/invoices/${i.id}/pdf?token=${token}`} target="_blank" rel="noreferrer" className="text-xs text-[#002FA7] underline">PDF</a>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Message */}
      <section className="max-w-5xl mx-auto px-8 pb-20">
        <div className="border-t border-[#0A0A0A] pt-8">
          <div className="overline mb-3">A QUICK WORD</div>
          <h2 className="font-display font-bold tracking-tight text-3xl mb-4">Leave a note for the team</h2>
          {sent ? (
            <p className="text-sm text-[#1D633E]">Thanks — we've received your message and will respond shortly.</p>
          ) : (
            <form onSubmit={send} className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <input required className="input-flat" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
              <input required className="input-flat md:col-span-2" placeholder="Message" value={msg} onChange={(e) => setMsg(e.target.value)} />
              <button className="btn-primary justify-center">Send</button>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
