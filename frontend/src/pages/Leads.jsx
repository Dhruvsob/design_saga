import { useEffect, useState } from "react";
import api from "../lib/api";
import { Plus, ArrowRight, Trash } from "@phosphor-icons/react";

const STAGES = ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"];
const SOURCES = ["Website", "Instagram", "Referral", "Marketplace", "Walk-in"];
const TYPES = ["Residential", "Commercial"];

export default function Leads() {
  const [leads, setLeads] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", source: "Website", project_type: "Residential", budget: 0, location: "", stage: "New" });
  const [dragId, setDragId] = useState(null);

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
    <div className="space-y-6" data-testid="crm-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline mb-1">CRM / PIPELINE</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">Every lead. Tracked.</h1>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-lead-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New lead"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="lead-form">
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
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 border-t border-l border-[#E5E5E5]">
        {STAGES.map((stage) => {
          const items = leads.filter((l) => l.stage === stage);
          return (
            <div
              key={stage}
              className="border-r border-b border-[#E5E5E5] min-h-[400px] flex flex-col"
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => drop(stage)}
              data-testid={`col-${stage}`}
            >
              <div className="p-3 border-b border-[#E5E5E5] bg-[#FAFAFA] flex items-center justify-between">
                <div className="overline">{stage}</div>
                <div className="font-mono text-xs font-semibold">{items.length}</div>
              </div>
              <div className="p-3 flex-1 space-y-3">
                {items.map((l) => (
                  <div
                    key={l.id}
                    draggable
                    onDragStart={() => setDragId(l.id)}
                    className="border border-[#E5E5E5] p-3 bg-white hover:border-[#0A0A0A] cursor-grab active:cursor-grabbing transition"
                    data-testid={`lead-${l.id}`}
                  >
                    <div className="font-semibold text-sm">{l.name}</div>
                    <div className="text-xs text-[#5C5C5C] mt-1">{l.project_type} · {l.location || "—"}</div>
                    <div className="font-mono text-xs mt-2">₹{(l.budget || 0).toLocaleString("en-IN")}</div>
                    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-[#F0F0F0]">
                      <span className="overline">{l.source}</span>
                      <div className="flex-1" />
                      {l.stage !== "Won" && l.stage !== "Lost" && (
                        <button onClick={() => convert(l.id)} className="text-[#002FA7] hover:underline text-xs flex items-center gap-1" title="Convert to project">
                          <ArrowRight size={12} /> Convert
                        </button>
                      )}
                      <button onClick={() => del(l.id)} className="text-[#FF2A00] hover:underline" title="Delete">
                        <Trash size={12} />
                      </button>
                    </div>
                  </div>
                ))}
                {items.length === 0 && <div className="text-xs text-[#5C5C5C]">—</div>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-[#5C5C5C] font-mono tracking-wider">DRAG CARDS BETWEEN COLUMNS TO UPDATE STAGES.</p>
    </div>
  );
}
