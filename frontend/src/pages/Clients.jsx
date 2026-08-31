import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import PageHero from "../components/PageHero";
import {
  Plus, MagnifyingGlass, PencilSimple, Archive, ArrowCounterClockwise, CaretRight, X,
} from "@phosphor-icons/react";

const EMPTY = { name: "", email: "", phone: "", company: "", address: "", client_type: "", notes: "" };

export default function Clients() {
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const { values } = useMasterData();
  const clientTypes = values("client_type", ["Individual", "Corporate"]);

  const [clients, setClients] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null); // client being edited
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/clients", { params: { include_archived: showArchived } });
      setClients(data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [showArchived]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    let rows = clients;
    if (!showArchived) rows = rows.filter((c) => !c.archived);
    if (typeFilter) rows = rows.filter((c) => c.client_type === typeFilter);
    const q = query.trim().toLowerCase();
    if (q) rows = rows.filter((c) =>
      [c.name, c.company, c.email, c.phone].some((v) => (v || "").toLowerCase().includes(q)));
    return rows;
  }, [clients, query, typeFilter, showArchived]);

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      if (editing) {
        await api.patch(`/clients/${editing.id}`, form);
      } else {
        await api.post("/clients", form);
      }
      setForm(EMPTY); setShowForm(false); setEditing(null);
      load();
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(typeof d === "string" ? d : "Save failed");
    }
  };

  const startEdit = (c, e) => {
    e.stopPropagation();
    setEditing(c);
    setForm({ name: c.name || "", email: c.email || "", phone: c.phone || "",
              company: c.company || "", address: c.address || "",
              client_type: c.client_type || "", notes: c.notes || "" });
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const archive = async (c, e) => {
    e.stopPropagation();
    if (!window.confirm(`Archive “${c.name}”? The client will be hidden but history is preserved.`)) return;
    await api.post(`/clients/${c.id}/archive`);
    load();
  };

  const restore = async (c, e) => {
    e.stopPropagation();
    await api.post(`/clients/${c.id}/restore`);
    load();
  };

  return (
    <div className="space-y-6" data-testid="clients-page">
      <PageHero
        eyebrow="DIRECTORY / CLIENTS"
        title="People we make things for."
        kicker="Click a client to open their profile — projects, invoices and ledger in one place."
        count={filtered.length}
      >
        <button
          onClick={() => { setShowForm(!showForm); setEditing(null); setForm(EMPTY); }}
          className="btn-primary" data-testid="new-client-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New client"}
        </button>
      </PageHero>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-2 gap-3 scale-in" data-testid="client-form">
          <div className="md:col-span-2 flex items-center justify-between">
            <div className="overline">{editing ? `EDITING — ${editing.name}` : "NEW CLIENT"}</div>
            {editing && (
              <button type="button" className="btn-ghost text-xs" onClick={() => { setEditing(null); setForm(EMPTY); setShowForm(false); }}>
                <X size={12} /> Cancel edit
              </button>
            )}
          </div>
          <input required className="input-flat" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="client-name" />
          <input className="input-flat" placeholder="Company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
          <input className="input-flat" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input-flat" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <select className="input-flat" value={form.client_type} onChange={(e) => setForm({ ...form, client_type: e.target.value })} data-testid="client-type-select">
            <option value="">Client type…</option>
            {clientTypes.map((t) => <option key={t}>{t}</option>)}
          </select>
          <input className="input-flat" placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <textarea className="input-flat md:col-span-2" rows="2" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          {err && <div className="md:col-span-2 border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2">{err}</div>}
          <button className="btn-primary md:col-span-2" data-testid="client-submit">{editing ? "Save changes" : "Save client"}</button>
        </form>
      )}

      {/* filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-2 border border-[#E5E5E5] focus-within:border-[#8B7F6A] transition flex-1 max-w-sm">
          <MagnifyingGlass size={14} className="text-[#5C5C5C]" />
          <input className="flex-1 outline-none text-sm bg-transparent" placeholder="Search name, company, email, phone…"
            value={query} onChange={(e) => setQuery(e.target.value)} data-testid="clients-search" />
        </div>
        <select className="input-flat w-auto" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} data-testid="clients-type-filter">
          <option value="">All types</option>
          {clientTypes.map((t) => <option key={t}>{t}</option>)}
        </select>
        <label className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[#5C5C5C] cursor-pointer">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} data-testid="clients-show-archived" />
          Show archived
        </label>
      </div>

      <div className="border border-[#E5E5E5]">
        <div className="overflow-x-auto"><table className="w-full">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Name</Th><Th>Type</Th><Th>Company</Th><Th>Email</Th><Th>Phone</Th><Th>Added</Th><Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan="7" className="p-6 text-center text-sm text-[#9A9A9A] font-mono uppercase tracking-wider">Loading…</td></tr>
            )}
            {!loading && filtered.map((c) => (
              <tr key={c.id}
                  onClick={() => navigate(`/clients/${c.id}`)}
                  className={`border-b border-[#F0F0F0] hover:bg-[#FAFAFA] cursor-pointer transition ${c.archived ? "opacity-50" : ""}`}
                  data-testid={`client-${c.id}`}>
                <Td className="font-semibold">
                  <span className="inline-flex items-center gap-2">
                    {c.name}
                    {c.archived && <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 bg-[#F5F5F5] text-[#9A9A9A]">Archived</span>}
                    <CaretRight size={10} className="text-[#9A9A9A]" />
                  </span>
                </Td>
                <Td>{c.client_type || "—"}</Td>
                <Td>{c.company || "—"}</Td>
                <Td className="font-mono text-xs">{c.email || "—"}</Td>
                <Td className="font-mono text-xs">{c.phone || "—"}</Td>
                <Td className="font-mono text-xs">{(c.created_at || "").slice(0, 10)}</Td>
                <Td>
                  <div className="flex items-center justify-end gap-1">
                    {hasPerm("clients.update") && (
                      <button onClick={(e) => startEdit(c, e)} className="btn-ghost p-1.5" title="Edit" data-testid={`client-edit-${c.id}`}>
                        <PencilSimple size={13} />
                      </button>
                    )}
                    {hasPerm("clients.update") && !c.archived && (
                      <button onClick={(e) => archive(c, e)} className="btn-ghost p-1.5" title="Archive" data-testid={`client-archive-${c.id}`}>
                        <Archive size={13} />
                      </button>
                    )}
                    {hasPerm("clients.update") && c.archived && (
                      <button onClick={(e) => restore(c, e)} className="btn-ghost p-1.5 text-[#1D633E]" title="Restore" data-testid={`client-restore-${c.id}`}>
                        <ArrowCounterClockwise size={13} />
                      </button>
                    )}
                  </div>
                </Td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan="7" className="p-8 text-center text-[#5C5C5C]">
                <div className="overline mb-1">{query || typeFilter ? "NO MATCHES" : "NO CLIENTS YET"}</div>
                <div className="text-sm">{query || typeFilter ? "Try a different search or filter." : "Add your first client or convert a lead from the CRM."}</div>
              </td></tr>
            )}
          </tbody>
        </table></div>
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
