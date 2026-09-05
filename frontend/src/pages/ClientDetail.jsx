import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import useMasterData from "../hooks/useMasterData";
import CommentsPanel from "../components/CommentsPanel";
import ActivityTimeline from "../components/ActivityTimeline";
import {
  ArrowLeft, PencilSimple, Archive, ArrowCounterClockwise, CaretRight, X, Warning,
} from "@phosphor-icons/react";

const TABS = ["Projects", "Invoices", "Ledger", "Activity"];
const inr = (n) => `\u20b9${(n || 0).toLocaleString("en-IN")}`;

export default function ClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const { values } = useMasterData();
  const clientTypes = values("client_type", ["Individual", "Corporate"]);

  const [c, setC] = useState(null);
  const [tab, setTab] = useState("Projects");
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState({});
  const [ledger, setLedger] = useState(null);
  const [ledgerErr, setLedgerErr] = useState("");
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/clients/${id}`);
      setC(data);
    } catch {
      setNotFound(true);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tab !== "Ledger" || ledger || !hasPerm("finance.read")) return;
    api.get(`/accounting/ledger/client/${id}`)
      .then((r) => setLedger(r.data))
      .catch(() => setLedgerErr("Ledger unavailable."));
  }, [tab, id, ledger, hasPerm]);

  const openEdit = () => {
    setForm({ name: c.name || "", email: c.email || "", phone: c.phone || "",
              company: c.company || "", address: c.address || "",
              client_type: c.client_type || "", notes: c.notes || "" });
    setEditOpen(true);
  };

  const saveEdit = async (e) => {
    e.preventDefault(); setErr("");
    try {
      await api.patch(`/clients/${id}`, form);
      setEditOpen(false);
      load();
    } catch (ex) {
      const d = ex?.response?.data?.detail;
      setErr(typeof d === "string" ? d : "Save failed");
    }
  };

  const toggleArchive = async () => {
    if (c.archived) {
      await api.post(`/clients/${id}/restore`);
    } else {
      if (!window.confirm(`Archive “${c.name}”?`)) return;
      await api.post(`/clients/${id}/archive`);
    }
    load();
  };

  if (loading) return <div className="overline">LOADING…</div>;
  if (notFound) return (
    <div className="text-center py-24">
      <div className="overline mb-2">404</div>
      <h1 className="font-display font-bold text-3xl mb-4">Client not found.</h1>
      <Link to="/clients" className="btn-primary inline-flex">Back to clients</Link>
    </div>
  );

  const s = c.summary || {};

  return (
    <div className="space-y-8" data-testid="client-detail">
      <Link to="/clients" className="inline-flex items-center gap-1 text-sm text-[#5C5C5C] hover:text-[#0A0A0A]">
        <ArrowLeft size={14} /> Back to clients
      </Link>

      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="overline mb-2">
            CLIENT {c.client_type ? `· ${c.client_type}` : ""} {c.archived && <span className="ml-2 text-[9px] font-mono uppercase px-1.5 py-0.5 bg-[#F5F5F5] text-[#9A9A9A]">ARCHIVED</span>}
          </div>
          <h1 className="font-display font-bold tracking-tight text-4xl">{c.name}</h1>
          <div className="mt-2 text-sm text-[#5C5C5C] space-x-3">
            {c.company && <span>{c.company}</span>}
            {c.email && <span className="font-mono text-xs">{c.email}</span>}
            {c.phone && <span className="font-mono text-xs">{c.phone}</span>}
          </div>
          {c.address && <div className="mt-1 text-sm text-[#5C5C5C]">{c.address}</div>}
          {c.notes && <p className="mt-2 text-sm text-[#5C5C5C] max-w-2xl border-l-2 border-[#E5E5E5] pl-3">{c.notes}</p>}
        </div>
        <div className="flex items-center gap-2">
          {hasPerm("clients.update") && (
            <>
              <button onClick={openEdit} className="btn-ghost" data-testid="client-edit-btn">
                <PencilSimple size={14} /> Edit
              </button>
              <button onClick={toggleArchive} className="btn-ghost" data-testid="client-archive-btn">
                {c.archived ? <><ArrowCounterClockwise size={14} /> Restore</> : <><Archive size={14} /> Archive</>}
              </button>
            </>
          )}
        </div>
      </div>

      {/* summary strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 border-t border-l border-[#E5E5E5]">
        <Stat label="Projects" value={s.projects ?? 0} />
        <Stat label="Invoiced" value={inr(s.total_invoiced)} />
        <Stat label="Collected" value={inr(s.total_paid)} accent="#1D633E" />
        <Stat label="Outstanding" value={inr(s.outstanding)} accent={s.outstanding > 0 ? "#B22B22" : undefined} />
      </div>

      {/* tabs */}
      <div className="flex gap-1 border-b border-[#E5E5E5]">
        {TABS.filter((t) => t !== "Ledger" || hasPerm("finance.read")).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition ${
              tab === t ? "border-[#8B7F6A] text-[#8B7F6A]" : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"
            }`}
            data-testid={`client-tab-${t}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Projects" && (
        <div className="space-y-2">
          {(c.projects || []).length === 0 && <Empty text="No projects for this client yet." />}
          {(c.projects || []).map((p) => (
            <button key={p.id} onClick={() => navigate(`/projects/${p.id}`)}
              className="w-full text-left border border-[#E5E5E5] p-4 hover:border-[#0A0A0A] transition flex items-center justify-between"
              data-testid={`client-project-${p.id}`}>
              <div>
                <div className="font-semibold">{p.name}</div>
                <div className="text-xs text-[#5C5C5C] mt-0.5">{p.project_type} · {p.stage}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm font-semibold">{inr(p.budget)}</span>
                <CaretRight size={12} />
              </div>
            </button>
          ))}
        </div>
      )}

      {tab === "Invoices" && (
        <div className="space-y-2">
          {(c.invoices || []).length === 0 && <Empty text="No invoices for this client yet." />}
          {(c.invoices || []).map((i) => (
            <div key={i.id} className="border border-[#E5E5E5] p-4 flex items-center justify-between">
              <div>
                <div className="font-mono font-semibold text-sm">{i.number}</div>
                <div className="text-xs text-[#5C5C5C] mt-0.5">{i.doc_type} · {i.project_name || "—"} · Due {i.due_date || "—"}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono font-semibold">{inr(i.total)}</span>
                <span className={`status-chip chip-${i.status}`}>{i.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "Ledger" && hasPerm("finance.read") && (
        <div className="space-y-4">
          {ledgerErr && <Empty text={ledgerErr} />}
          {!ledger && !ledgerErr && <div className="overline">LOADING LEDGER…</div>}
          {ledger && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 border-t border-l border-[#E5E5E5]">
                <Stat label="Opening" value={inr(ledger.opening_balance)} />
                <Stat label="Inflow" value={inr(ledger.inflow)} accent="#1D633E" />
                <Stat label="Outflow" value={inr(ledger.outflow)} accent="#B22B22" />
                <Stat label="Closing" value={inr(ledger.closing_balance)} />
              </div>
              <div className="border border-[#E5E5E5] overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
                    <tr className="text-left">
                      <th className="px-4 py-2.5 overline">Date</th>
                      <th className="px-4 py-2.5 overline">Narration</th>
                      <th className="px-4 py-2.5 overline text-right">In</th>
                      <th className="px-4 py-2.5 overline text-right">Out</th>
                      <th className="px-4 py-2.5 overline text-right">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(ledger.entries || []).map((e, i) => (
                      <tr key={i} className="border-b border-[#F0F0F0]">
                        <td className="px-4 py-2 font-mono text-xs">{(e.date || "").slice(0, 10)}</td>
                        <td className="px-4 py-2 text-sm">{e.narration || e.memo || "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs text-right text-[#1D633E]">{e.inflow ? inr(e.inflow) : "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs text-right text-[#B22B22]">{e.outflow ? inr(e.outflow) : "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs text-right font-semibold">{inr(e.balance ?? e.running_balance)}</td>
                      </tr>
                    ))}
                    {(ledger.entries || []).length === 0 && (
                      <tr><td colSpan="5" className="p-6 text-center text-sm text-[#5C5C5C]">No ledger entries yet.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {tab === "Activity" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <CommentsPanel entityType="client" entityId={id} />
          <ActivityTimeline entityType="client" entityId={id} />
        </div>
      )}

      {/* edit modal */}
      {editOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-6"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setEditOpen(false); }}>
          <form onSubmit={saveEdit} className="bg-white border border-[#0A0A0A] w-full max-w-lg p-6 space-y-3" data-testid="client-edit-modal">
            <div className="flex items-center justify-between">
              <div className="overline">EDIT CLIENT</div>
              <button type="button" onClick={() => setEditOpen(false)} className="btn-ghost p-1"><X size={14} /></button>
            </div>
            <input required className="input-flat w-full" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="edit-client-name" />
            <div className="grid grid-cols-2 gap-3">
              <input className="input-flat" placeholder="Company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
              <select className="input-flat" value={form.client_type} onChange={(e) => setForm({ ...form, client_type: e.target.value })}>
                <option value="">Client type…</option>
                {clientTypes.map((t) => <option key={t}>{t}</option>)}
              </select>
              <input className="input-flat" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              <input className="input-flat" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
            <input className="input-flat w-full" placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            <textarea className="input-flat w-full" rows="2" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            {err && <div className="border border-[#B22B22] bg-[#FCEEEC] text-[#B22B22] text-xs px-3 py-2 flex items-center gap-2"><Warning size={12} /> {err}</div>}
            <button className="btn-primary w-full" data-testid="edit-client-save">Save changes</button>
          </form>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div className="border-r border-b border-[#E5E5E5] p-5">
      <div className="overline mb-2">{label}</div>
      <div className="font-display font-bold tracking-tight text-2xl tabular-nums" style={accent ? { color: accent } : undefined}>{value}</div>
    </div>
  );
}

function Empty({ text }) {
  return <p className="text-[#5C5C5C] text-sm border border-dashed border-[#E5E5E5] p-6 text-center">{text}</p>;
}
