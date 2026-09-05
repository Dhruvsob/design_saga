import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import useMasterData from "../hooks/useMasterData";
import { Plus, ArrowRight, Trash, DotsSixVertical, PencilSimple, X } from "@phosphor-icons/react";
import PageHero from "../components/PageHero";

const FALLBACK_STAGES = ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"];
const FALLBACK_SOURCES = ["Website", "Instagram", "Referral", "Marketplace", "Walk-in"];
const FALLBACK_TYPES = ["Residential", "Commercial"];

const STAGE_COLORS = {
  New: "#5C5C5C",
  Qualified: "#8B7F6A",
  Proposal: "#8B7F6A",
  Negotiation: "#FF8C00",
  Won: "#1D633E",
  Lost: "#FF2A00",
};

export default function Leads() {
  const navigate = useNavigate();
  const { values } = useMasterData();
  const STAGES = values("lead_stage", FALLBACK_STAGES);
  const SOURCES = values("lead_source", FALLBACK_SOURCES);
  const TYPES = values("project_type", FALLBACK_TYPES);
  const [leads, setLeads] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", source: "Website", project_type: "Residential", budget: 0, location: "", stage: "New" });
  const [editing, setEditing] = useState(null); // lead being edited
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

  const startEdit = (l) => {
    setEditing(l);
  };

  const saveEdit = async (e) => {
    e.preventDefault();
    const { id, ...rest } = editing;
    await api.patch(`/leads/${id}`, {
      name: rest.name, email: rest.email || undefined, phone: rest.phone || undefined,
      source: rest.source || undefined, project_type: rest.project_type || undefined,
      budget: Number(rest.budget || 0), location: rest.location || undefined,
      notes: rest.notes || undefined,
    });
    setEditing(null);
    load();
  };

  const convert = async (id) => {
    const { data } = await api.post(`/leads/${id}/convert`);
    toast.success("Lead converted — client & project created", {
      action: { label: "Open project", onClick: () => navigate(`/projects/${data.project_id}`) },
    });
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
              className={`fade-up border-r border-b border-[#E5E5E5] min-h-[500px] flex flex-col transition-all ${isOver ? "bg-[#F5F4F0]" : ""}`}
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
                    <div className="flex items-center flex-wrap gap-x-2 gap-y-2 mt-3 pt-3 border-t border-[#F0F0F0]">
                      <span className="overline text-[10px] truncate min-w-0 flex-1">{l.source}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        {l.stage !== "Won" && l.stage !== "Lost" && (
                          <button onClick={() => convert(l.id)} className="text-[#8B7F6A] hover:underline text-xs flex items-center gap-1 font-semibold shrink-0" title="Convert to project">
                            <ArrowRight size={12} weight="bold" /> Convert
                          </button>
                        )}
                        <button onClick={() => startEdit(l)} className="text-[#5C5C5C] hover:text-[#0A0A0A] hover:scale-110 transition shrink-0" title="Edit" data-testid={`lead-edit-${l.id}`}>
                          <PencilSimple size={12} />
                        </button>
                        <button onClick={() => del(l.id)} className="text-[#B4342B] hover:scale-110 transition shrink-0" title="Delete" data-testid={`lead-delete-${l.id}`}>
                          <Trash size={12} />
                        </button>
                      </div>
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

      {/* Edit lead modal */}
      {editing && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setEditing(null); }}>
          <form onSubmit={saveEdit} className="bg-white border border-[#0A0A0A] w-full max-w-lg p-6 space-y-3" data-testid="lead-edit-modal">
            <div className="flex items-center justify-between">
              <div className="overline">EDIT LEAD</div>
              <button type="button" onClick={() => setEditing(null)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <input required className="input-flat w-full" placeholder="Name" value={editing.name || ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} data-testid="edit-lead-name" />
            <div className="grid grid-cols-2 gap-3">
              <input className="input-flat" placeholder="Email" value={editing.email || ""} onChange={(e) => setEditing({ ...editing, email: e.target.value })} />
              <input className="input-flat" placeholder="Phone" value={editing.phone || ""} onChange={(e) => setEditing({ ...editing, phone: e.target.value })} />
              <select className="input-flat" value={editing.source || ""} onChange={(e) => setEditing({ ...editing, source: e.target.value })}>
                {SOURCES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <select className="input-flat" value={editing.project_type || ""} onChange={(e) => setEditing({ ...editing, project_type: e.target.value })}>
                {TYPES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <input className="input-flat" type="number" placeholder="Budget (₹)" value={editing.budget ?? 0} onChange={(e) => setEditing({ ...editing, budget: e.target.value })} data-testid="edit-lead-budget" />
              <input className="input-flat" placeholder="Location" value={editing.location || ""} onChange={(e) => setEditing({ ...editing, location: e.target.value })} />
            </div>
            <textarea className="input-flat w-full" rows="2" placeholder="Notes" value={editing.notes || ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} />
            <button className="btn-primary w-full" data-testid="edit-lead-save">Save changes</button>
          </form>
        </div>
      )}
    </div>
  );
}
