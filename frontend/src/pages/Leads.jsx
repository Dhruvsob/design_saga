import { useEffect, useState } from "react";
import api from "../lib/api";
import { Plus, ArrowRight, Trash, DotsSixVertical } from "@phosphor-icons/react";
import PageHero from "../components/PageHero";

const STAGES = ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"];
const SOURCES = ["Website", "Instagram", "Referral", "Marketplace", "Walk-in"];
const TYPES = ["Residential", "Commercial"];

const STAGE_COLORS = {
  New: "#5C5C5C",
  Qualified: "#002FA7",
  Proposal: "#002FA7",
  Negotiation: "#FF8C00",
  Won: "#1D633E",
  Lost: "#FF2A00",
};

export default function Leads() {
  const [leads, setLeads] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", source: "Website", project_type: "Residential", budget: 0, location: "", stage: "New" });
  const [dragId, setDragId] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  const load = async () => {
    const { data } = await api.get("/leads");
    setLeads(data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/leads", { ...form, budget: Number(form.budget || 0) });
    setShowForm(false);
    setForm({ name: "", email: "", phone: "", source: "Website", project_type: "Residential", budget: 0, location: "", stage: "New" });
    load();
  };

  const drop = async (stage) => {
    if (!dragId) return;
    await api.patch(`/leads/${dragId}/stage`, { stage });
    setDragId(null);
    setDragOver(null);
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Delete this lead?")) return;
    await api.delete(`/leads/${id}`);
    load();
  };

  const convert = async (id) => {
    const { data } = await api.post(`/leads/${id}/convert`);
    alert(`Converted! Project created: ${data.project_id}`);
    load();
  };

  return (
    <div className="space-y-8" data-testid="crm-page">
      <PageHero
        eyebrow="CRM / PIPELINE"
        title="Every lead. Tracked."
        kicker="Drag cards between columns to update stages. Convert qualified leads into projects with one click."
        count={leads.length}
      >
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-lead-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New lead"}
        </button>
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-4 scale-in" data-testid="lead-form">
          <input className="input-flat" placeholder="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="lead-name" />
          <input className="input-flat" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input-flat" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <select className="input-flat" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
            {SOURCES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="input-flat" value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
            {TYPES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <input className="input-flat" type="number" placeholder="Budget (₹)" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          <button className="btn-primary" type="submit" data-testid="lead-submit">Save lead</button>
        </form>
      )}

      {/* Kanban */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 border-t border-l border-[#E5E5E5] stagger">
        {STAGES.map((stage, idx) => {
          const items = leads.filter((l) => l.stage === stage);
          const stageColor = STAGE_COLORS[stage];
          const isOver = dragOver === stage;
          return (
            <div
              key={stage}
              className={`fade-up border-r border-b border-[#E5E5E5] min-h-[500px] flex flex-col transition-all ${isOver ? "bg-[#F0F3FB]" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(stage); }}
              onDragLeave={() => setDragOver(null)}
              onDrop={() => drop(stage)}
              data-testid={`col-${stage}`}
            >
              <div className="p-3 border-b border-[#E5E5E5] bg-[#FAFAFA] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: stageColor }} />
                  <div className="overline">{stage}</div>
                </div>
                <div className="font-mono text-xs font-semibold bg-white px-1.5 border border-[#E5E5E5]">{items.length}</div>
              </div>
              <div className="p-3 flex-1 space-y-3">
                {items.map((l) => (
                  <div
                    key={l.id}
                    draggable
                    onDragStart={() => setDragId(l.id)}
                    className="border border-[#E5E5E5] p-3 bg-white hover:border-[#0A0A0A] hover:-translate-y-0.5 cursor-grab active:cursor-grabbing transition-all group"
                    data-testid={`lead-${l.id}`}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <div className="font-semibold text-sm leading-snug">{l.name}</div>
                      <DotsSixVertical size={14} className="text-[#CCCCCC] mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <div className="text-xs text-[#5C5C5C] mt-1 flex items-center gap-1.5">
                      <span>{l.project_type}</span>
                      <span className="w-0.5 h-0.5 bg-[#9A9A9A] rounded-full" />
                      <span>{l.location || "—"}</span>
                    </div>
                    <div className="font-mono text-sm mt-2 tabular-nums font-semibold">₹{(l.budget || 0).toLocaleString("en-IN")}</div>
                    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-[#F0F0F0]">
                      <span className="overline text-[10px]">{l.source}</span>
                      <div className="flex-1" />
                      {l.stage !== "Won" && l.stage !== "Lost" && (
                        <button onClick={() => convert(l.id)} className="text-[#002FA7] hover:underline text-xs flex items-center gap-1 font-semibold" title="Convert to project">
                          <ArrowRight size={12} weight="bold" /> Convert
                        </button>
                      )}
                      <button onClick={() => del(l.id)} className="text-[#FF2A00] hover:scale-110 transition" title="Delete">
                        <Trash size={12} />
                      </button>
                    </div>
                  </div>
                ))}
                {items.length === 0 && (
                  <div className="text-center py-8 text-xs text-[#9A9A9A]">
                    <div className="dotted-bg mx-auto mb-2" style={{ width: 32, height: 32 }} />
                    —
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-[#5C5C5C] font-mono tracking-wider flex items-center gap-2">
        <DotsSixVertical size={12} /> DRAG CARDS BETWEEN COLUMNS TO UPDATE STAGES.
      </p>
    </div>
  );
}
