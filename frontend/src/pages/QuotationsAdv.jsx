import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Plus, ArrowRight, Trash } from "@phosphor-icons/react";
import SearchSelect from "../components/SearchSelect";

const TYPE_LABELS = {
  turnkey: "Turnkey",
  consultancy: "Design Consultancy",
  // Display labels retained for historical records only.
  execution: "Execution Only",
  hybrid: "Hybrid",
};
const NEW_TYPE_LABELS = {
  turnkey: TYPE_LABELS.turnkey,
  consultancy: TYPE_LABELS.consultancy,
};
const TYPE_HELP = {
  consultancy: "Letter-style design proposal: scope, design process, fixed fee with advance and instalments, optional site coordinator.",
  turnkey: "Design-and-build quotation: BOQ line items, rooms, materials, GST, payment milestones and timeline.",
};
const STATUS_COLORS = {
  draft: "chip-draft", sent: "chip-sent", under_review: "chip-medium",
  approved: "chip-paid", rejected: "chip-overdue", converted: "chip-paid",
};

export default function QuotationsAdv() {
  const { hasPerm } = useAuth();
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [allowedTypes, setAllowedTypes] = useState(["turnkey", "consultancy"]);
  const [form, setForm] = useState({ type: "", project_title: "", client_id: "", project_id: "", project_location: "", area_sqft: "" });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    const [r, c, p, t] = await Promise.all([
      api.get("/quotations-adv"),
      api.get("/clients"),
      api.get("/projects"),
      api.get("/quotations-adv/templates").catch(() => ({ data: {} })),
    ]);
    setRows(r.data);
    setClients(c.data);
    setProjects(p.data);
    const allowed = (t.data.allowed_types || ["turnkey", "consultancy"]).filter((x) => NEW_TYPE_LABELS[x]);
    setAllowedTypes(allowed);
    if (allowed.length === 1) setForm((f) => ({ ...f, type: allowed[0] }));
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.type) {
      toast.error("Choose Consultancy or Turnkey first");
      return;
    }
    setCreating(true);
    try {
      const { data } = await api.post("/quotations-adv", { ...form, area_sqft: Number(form.area_sqft || 0) });
      navigate(`/quotations/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create the quotation");
    } finally {
      setCreating(false);
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
          <h1 className="font-display font-bold tracking-tight text-3xl sm:text-4xl">Quotations</h1>
          <p className="text-[#5C5C5C] mt-2 max-w-xl">Design consultancy proposals and turnkey quotations, with versions, approval and a branded PDF.</p>
        </div>
        <div className="flex items-center gap-3">
          {hasPerm("quotations.create") && <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-quotation-btn">
            <Plus size={14} /> {showForm ? "Cancel" : "New quotation"}
          </button>}
        </div>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="new-quotation-form">
          {allowedTypes.length > 1 ? (
            <fieldset className="md:col-span-3">
              <legend className="text-xs font-semibold text-[#5C5C5C] mb-2">What are you quoting for?</legend>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup">
                {allowedTypes.map((v) => (
                  <label key={v} data-testid={`q-type-${v}`}
                         className={`block p-4 rounded-lg border cursor-pointer transition ${form.type === v
                           ? "border-[#76705E] bg-[#FAF9F6] ring-1 ring-[#76705E]" : "border-[#E8E6E1] bg-white hover:border-[#76705E]"}`}>
                    <span className="flex items-center gap-2">
                      <input type="radio" name="q-type" value={v} checked={form.type === v}
                             onChange={() => setForm({ ...form, type: v })} />
                      <span className="font-semibold">{NEW_TYPE_LABELS[v]}</span>
                    </span>
                    <span className="block text-xs text-[#6E6A63] mt-1">{TYPE_HELP[v]}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : (
            <p className="md:col-span-3 text-sm text-[#5C5C5C]" data-testid="q-type-fixed">
              <strong>{NEW_TYPE_LABELS[allowedTypes[0]]}</strong> · {TYPE_HELP[allowedTypes[0]]}
            </p>
          )}
          <input required className="input-flat md:col-span-2" aria-label="Project title"
                 placeholder={form.type === "consultancy" ? "Project, e.g. 4 BHK Apartment" : "Project title"}
                 value={form.project_title} onChange={(e) => setForm({ ...form, project_title: e.target.value })} data-testid="q-title" />
          <SearchSelect className="input-flat" value={form.client_id} onChange={(e) => {
            const c = clients.find(x => x.id === e.target.value);
            setForm({ ...form, client_id: e.target.value, client_name: c?.name });
          }}>
            <option value="">Select client</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </SearchSelect>
          <SearchSelect className="input-flat" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
            <option value="">Link project (optional)</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </SearchSelect>
          <input className="input-flat" type="number" placeholder="Enter area (sq ft)" value={form.area_sqft} onChange={(e) => setForm({ ...form, area_sqft: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="Project location" value={form.project_location} onChange={(e) => setForm({ ...form, project_location: e.target.value })} />
          <button className="btn-primary md:col-span-3" disabled={creating} data-testid="q-submit">
            {creating ? "Creating…" : "Create quotation"}
          </button>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <div className="overflow-x-auto"><table className="w-full">
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
                    <button onClick={() => navigate(`/quotations/${r.id}`)} className="text-[#76705E]" title="Open"><ArrowRight size={16} /></button>
                    {hasPerm("quotations.delete") && r.status !== "converted" && <button onClick={() => del(r.id)} className="text-[#FF2A00]" title="Delete"><Trash size={16} /></button>}
                  </div>
                </Td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan="8" className="p-8 text-center text-[#5C5C5C]">No quotations yet. Create the first quotation to get started.</td></tr>
            )}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "", onClick }) => <td className={`px-4 py-3 text-sm ${className}`} onClick={onClick}>{children}</td>;
