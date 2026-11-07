import { useEffect, useState } from "react";
import { statusLabel } from "../lib/format";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Plus, ArrowRight, Trash } from "@phosphor-icons/react";
import SearchSelect from "../components/SearchSelect";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";
import { FilePdf } from "@phosphor-icons/react";
import { API } from "../lib/api";
import { SkeletonRows, EmptyRow } from "../components/TableState";
import PageHero from "../components/PageHero";

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
  const [loaded, setLoaded] = useState(false);
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
    setLoaded(true);
    setClients(c.data);
    setProjects(p.data);
    const allowed = (t.data.allowed_types || ["turnkey", "consultancy"]).filter((x) => NEW_TYPE_LABELS[x]);
    setAllowedTypes(allowed);
    if (allowed.length === 1) setForm((f) => ({ ...f, type: allowed[0] }));
  };
  useEffect(() => { load().catch(() => {}).finally(() => setLoaded(true)); }, []);

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
    if (!await confirmAction("Delete quotation?")) return;
    await api.delete(`/quotations-adv/${id}`);
    load();
  };

  return (
    <div className="space-y-6" data-testid="quotations-adv-page">
      <PageHero title="Quotations" count={loaded ? rows.length : undefined}
        kicker="Design proposals and turnkey quotations, with versions, approval and a branded PDF.">
        <div className="flex items-center gap-3">
          {hasPerm("quotations.create") && <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-quotation-btn">
            <Plus size={14} /> {showForm ? "Cancel" : "New quotation"}
          </button>}
        </div>
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="new-quotation-form">
          {allowedTypes.length > 1 ? (
            <fieldset className="md:col-span-3">
              <legend className="text-xs font-semibold text-[var(--ink-2)] mb-2">What are you quoting for?</legend>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup">
                {allowedTypes.map((v) => (
                  <label key={v} data-testid={`q-type-${v}`}
                         className={`block p-4 rounded-lg border cursor-pointer transition ${form.type === v
                           ? "border-[var(--accent-strong)] bg-[var(--surface-2)] ring-1 ring-[var(--accent-strong)]" : "border-[var(--line)] bg-white hover:border-[var(--accent-strong)]"}`}>
                    <span className="flex items-center gap-2">
                      <input type="radio" name="q-type" value={v} checked={form.type === v}
                             onChange={() => setForm({ ...form, type: v })} />
                      <span className="font-semibold">{NEW_TYPE_LABELS[v]}</span>
                    </span>
                    <span className="block text-xs text-[var(--ink-3)] mt-1">{TYPE_HELP[v]}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : (
            <p className="md:col-span-3 text-sm text-[var(--ink-2)]" data-testid="q-type-fixed">
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
          <input className="input-flat" type="number" min="0" placeholder="Enter area (sq ft)" value={form.area_sqft} onChange={(e) => setForm({ ...form, area_sqft: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="Project location" value={form.project_location} onChange={(e) => setForm({ ...form, project_location: e.target.value })} />
          <button className="btn-primary md:col-span-3" disabled={creating} data-testid="q-submit">
            {creating ? "Creating…" : "Create quotation"}
          </button>
        </form>
      )}

      <div className="border border-[var(--line)]">
        <div className="overflow-x-auto"><table className="w-full">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
            <tr className="text-left">
              <Th>Number</Th><Th>Project</Th><Th>Client</Th><Th>Type</Th><Th>Version</Th><Th className="text-right">Total</Th><Th>Status</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[var(--line-soft)] hover:bg-[var(--surface-2)] cursor-pointer" data-testid={`q-row-${r.id}`}>
                <Td className="font-mono font-semibold" onClick={() => navigate(`/quotations/${r.id}`)}>{r.number}</Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}>
                  <div className="font-semibold">{r.project_title}</div>
                  <div className="text-xs text-[var(--ink-2)]">{r.area_sqft || 0} sq.ft</div>
                </Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}>{r.client_name || "—"}</Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}>
                  <span className="status-chip chip-medium">{TYPE_LABELS[r.type] || r.type}</span>
                </Td>
                <Td className="font-mono" onClick={() => navigate(`/quotations/${r.id}`)}>{r.version_label}</Td>
                <Td className="font-mono font-semibold text-right" onClick={() => navigate(`/quotations/${r.id}`)}>₹{(r.grand_total || 0).toLocaleString("en-IN")}</Td>
                <Td onClick={() => navigate(`/quotations/${r.id}`)}><span className={`status-chip ${STATUS_COLORS[r.status] || "chip-draft"}`}>{statusLabel(r.status)}</span></Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <RowActions label={`Quotation ${r.number}`} testid={`q-actions-${r.id}`} actions={[
                      { label: "Open", icon: ArrowRight, onSelect: () => navigate(`/quotations/${r.id}`) },
                      { label: "Download PDF", icon: FilePdf, onSelect: () => window.open(`${API}/quotations-adv/${r.id}/pdf`, "_blank", "noopener") },
                      { divider: true },
                      { label: "Delete", icon: Trash, danger: true, onSelect: () => del(r.id), testid: `q-delete-${r.id}`,
                        hidden: !(hasPerm("quotations.delete") && r.status !== "converted") },
                    ]} />
                  </div>
                </Td>
              </tr>
            ))}
            {!loaded && <SkeletonRows cols={8} />}
            {loaded && rows.length === 0 && (
              <EmptyRow cols={8} icon={FilePdf} title="No quotations yet"
                hint="Create a design proposal or a turnkey BOQ quotation and download it as a branded PDF."
                actionLabel={hasPerm("quotations.create") ? "New quotation" : undefined}
                onAction={() => { setShowForm(true); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
            )}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "", onClick }) => <td className={`px-4 py-3 text-sm ${className}`} onClick={onClick}>{children}</td>;
