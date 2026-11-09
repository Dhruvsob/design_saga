import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import PageHero from "../components/PageHero";
import { formatDate } from "../lib/format";
import {
  Plus, MagnifyingGlass, PencilSimple, Archive, ArrowCounterClockwise, CaretRight, X,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";
import { ArrowSquareOut } from "@phosphor-icons/react";
import { usePaged } from "../components/Pager";
import { UsersThree } from "@phosphor-icons/react";
import { SkeletonRows, EmptyRow } from "../components/TableState";

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
  const canCreate = hasPerm("clients.create");

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
  const { pageRows: filteredPage, pager: filteredPager } = usePaged(filtered, { key: "clients" });

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
    if (!await confirmAction(`Archive “${c.name}”? The client will be hidden but history is preserved.`)) return;
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
        title="Clients"
        kicker="Click a client to open their profile — projects, invoices and ledger in one place."
        count={filtered.length}
      >
        {canCreate && (
          <button
            onClick={() => { setShowForm(!showForm); setEditing(null); setForm(EMPTY); }}
            className="btn-primary" data-testid="new-client-btn">
            {showForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> {"New client"}</>}
          </button>
        )}
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
          <select aria-label="Client type" className="input-flat" value={form.client_type} onChange={(e) => setForm({ ...form, client_type: e.target.value })} data-testid="client-type-select">
            <option value="">Client type…</option>
            {clientTypes.map((t) => <option key={t}>{t}</option>)}
          </select>
          <input className="input-flat" placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <textarea className="input-flat md:col-span-2" rows="2" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          {err && <div className="md:col-span-2 border border-[var(--danger)] bg-[var(--danger-soft)] text-[var(--danger)] text-xs px-3 py-2">{err}</div>}
          <button className="btn-primary md:col-span-2" data-testid="client-submit">{editing ? "Save changes" : "Save client"}</button>
        </form>
      )}

      {/* filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-2 border border-[var(--line)] focus-within:border-[var(--accent)] transition flex-1 max-w-sm">
          <MagnifyingGlass size={14} className="text-[var(--ink-2)]" />
          <input className="flex-1 outline-none text-sm bg-transparent" placeholder="Search name, company, email, phone…"
            value={query} onChange={(e) => setQuery(e.target.value)} data-testid="clients-search" />
        </div>
        <select aria-label="Type filter" className="input-flat w-auto" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} data-testid="clients-type-filter">
          <option value="">All types</option>
          {clientTypes.map((t) => <option key={t}>{t}</option>)}
        </select>
        <label className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--ink-2)] cursor-pointer">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} data-testid="clients-show-archived" />
          Show archived
        </label>
      </div>

      <div className="border border-[var(--line)]">
        <div className="overflow-x-auto"><table className="w-full">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
            <tr className="text-left">
              <Th>Name</Th><Th>Type</Th><Th>Company</Th><Th>Email</Th><Th>Phone</Th><Th>Added</Th><Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {loading && <SkeletonRows cols={7} />}
            {!loading && filteredPage.map((c) => (
              <tr key={c.id}
                  onClick={() => navigate(`/clients/${c.id}`)}
                  className={`border-b border-[var(--line-soft)] hover:bg-[var(--surface-2)] cursor-pointer transition ${c.archived ? "opacity-50" : ""}`}
                  data-testid={`client-${c.id}`}>
                <Td className="font-semibold">
                  <span className="inline-flex items-center gap-2">
                    {c.name}
                    {c.archived && <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 bg-[var(--hover)] text-[var(--ink-3)]">Archived</span>}
                    <CaretRight size={10} className="text-[var(--ink-3)]" />
                  </span>
                </Td>
                <Td>{c.client_type || "—"}</Td>
                <Td>{c.company || "—"}</Td>
                <Td className="font-mono text-xs">{c.email || "—"}</Td>
                <Td className="font-mono text-xs">{c.phone || "—"}</Td>
                <Td className="font-mono text-xs">{formatDate(c.created_at)}</Td>
                <Td>
                  <div className="flex items-center justify-end">
                    <RowActions label={c.name} testid={`client-actions-${c.id}`} actions={[
                      { label: "Open", icon: ArrowSquareOut, onSelect: () => navigate(`/clients/${c.id}`) },
                      { label: "Edit", icon: PencilSimple, onSelect: () => startEdit(c, { stopPropagation() {} }),
                        hidden: !hasPerm("clients.update"), testid: `client-edit-${c.id}` },
                      { divider: true },
                      { label: "Archive", icon: Archive, onSelect: () => archive(c, { stopPropagation() {} }),
                        hidden: !hasPerm("clients.update") || c.archived, testid: `client-archive-${c.id}` },
                      { label: "Restore", icon: ArrowCounterClockwise, onSelect: () => restore(c, { stopPropagation() {} }),
                        hidden: !hasPerm("clients.update") || !c.archived, testid: `client-restore-${c.id}` },
                    ]} />
                  </div>
                </Td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (query || typeFilter ? (
              <EmptyRow cols={7} icon={UsersThree} title="No clients match" hint="Try a different search or filter." />
            ) : (
              <EmptyRow cols={7} icon={UsersThree} title="No clients yet"
                hint="Add your first client, or convert a won lead from the CRM."
                actionLabel={canCreate ? "Add client" : undefined}
                onAction={() => { setEditing(null); setForm(EMPTY); setShowForm(true); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
            ))}
          </tbody>
        </table>{filteredPager}</div>
      </div>
    </div>
  );
}

const Th = ({ children, className = "" }) => <th className={`px-4 py-3 overline ${className}`}>{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
