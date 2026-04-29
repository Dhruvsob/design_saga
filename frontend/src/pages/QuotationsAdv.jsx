import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { Plus, ArrowRight, Trash, FilePdf, Sparkle } from "@phosphor-icons/react";

const TYPE_LABELS = {
  turnkey: "Turnkey",
  consultancy: "Design Consultancy",
  execution: "Execution Only",
  hybrid: "Hybrid",
};
const STATUS_COLORS = {
  draft: "chip-draft", sent: "chip-sent", under_review: "chip-medium",
  approved: "chip-paid", rejected: "chip-overdue", converted: "chip-paid",
};

export default function QuotationsAdv() {
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [form, setForm] = useState({ type: "turnkey", project_title: "", client_id: "", project_id: "", project_location: "", area_sqft: 0 });
  const navigate = useNavigate();

  const load = async () => {
    const [r, c, p] = await Promise.all([
      api.get("/quotations-adv"),
      api.get("/clients"),
      api.get("/projects"),
    ]);
    setRows(r.data);
    setClients(c.data);
    setProjects(p.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    const { data } = await api.post("/quotations-adv", { ...form, area_sqft: Number(form.area_sqft || 0) });
    navigate(`/quotations/${data.id}`);
  };

  const seed = async () => {
    setSeeding(true);
    try {
      const { data } = await api.post("/quotations-adv/seed");
      await load();
      navigate(`/quotations/${data.id}`);
    } finally {
      setSeeding(false);
    }
  };

  const del = async (id) => {
    if (!window.confirm("Delete quotation?")) return;
    await api.delete(`/quotations-adv/${id}`);
    load();
  };

  return (
    <div className="space-y-6" data-testid="quotations-adv-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="overline mb-1">FINANCE / QUOTATIONS</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">Enterprise quotation engine.</h1>
          <p className="text-[#5C5C5C] mt-2 max-w-xl">BOQ, room-wise costing, materials, payment plans, timeline, terms, versions and approval — all in one professional document.</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={seed} disabled={seeding} className="btn-ghost" data-testid="seed-quotation-btn">
            <Sparkle size={14} /> {seeding ? "Seeding…" : "Seed sample"}
          </button>
          <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-quotation-btn">
            <Plus size={14} /> {showForm ? "Cancel" : "New quotation"}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="new-quotation-form">
          <select className="input-flat" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="q-type">
            {Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <input required className="input-flat md:col-span-2" placeholder="Project title" value={form.project_title} onChange={(e) => setForm({ ...form, project_title: e.target.value })} data-testid="q-title" />
          <select className="input-flat" value={form.client_id} onChange={(e) => {
            const c = clients.find(x => x.id === e.target.value);
            setForm({ ...form, client_id: e.target.value, client_name: c?.name });
          }}>
            <option value="">Select client</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
            <option value="">Link project (optional)</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <input className="input-flat" type="number" placeholder="Area (sq.ft)" value={form.area_sqft} onChange={(e) => setForm({ ...form, area_sqft: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="Project location" value={form.project_location} onChange={(e) => setForm({ ...form, project_location: e.target.value })} />
          <button className="btn-primary md:col-span-3" data-testid="q-submit">Create quotation</button>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <table className="w-full">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Number</Th><Th>Project</Th><Th>Client</Th><Th>Type</Th><Th>Version</Th><Th className="text-right">Total</Th><Th>Status</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[#F0F0F0] hover:bg-[#FAFAFA] cursor-pointer" data-testid={`q-row-${r.id}`}>
                <Td className="font-mono font-semibold" onClick={() => navigate(`/quotations/${r.id}`)}>{r.number}</Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}>
                  <div className="font-semibold">{r.project_title}</div>
                  <div className="text-xs text-[#5C5C5C]">{r.area_sqft || 0} sq.ft</div>
                </Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}>{r.client_name || "—"}</Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}>
                  <span className="status-chip chip-medium">{TYPE_LABELS[r.type] || r.type}</span>
                </Td>
                <Td className="font-mono" onClick={() => navigate(`/quotations/${r.id}`)}>{r.version_label}</Td>
                <Td className="font-mono font-semibold text-right" onClick={() => navigate(`/quotations/${r.id}`)}>₹{(r.grand_total || 0).toLocaleString("en-IN")}</Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}><span className={`status-chip ${STATUS_COLORS[r.status] || "chip-draft"}`}>{r.status}</span></Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <button onClick={() => navigate(`/quotations/${r.id}`)} className="text-[#002FA7]" title="Open"><ArrowRight size={16} /></button>
                    <button onClick={() => del(r.id)} className="text-[#FF2A00]" title="Delete"><Trash size={16} /></button>
                  </div>
                </Td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan="8" className="p-8 text-center text-[#5C5C5C]">No quotations yet. Create one or seed a sample.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "", onClick }) => <td className={`px-4 py-3 text-sm ${className}`} onClick={onClick}>{children}</td>;
