import { useEffect, useState } from "react";
import api from "../lib/api";
import { Plus } from "@phosphor-icons/react";

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", company: "", address: "" });

  const load = async () => {
    const { data } = await api.get("/clients");
    setClients(data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/clients", form);
    setForm({ name: "", email: "", phone: "", company: "", address: "" });
    setShowForm(false);
    load();
  };

  return (
    <div className="space-y-6" data-testid="clients-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline mb-1">DIRECTORY / CLIENTS</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">People we make things for.</h1>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary" data-testid="new-client-btn">
          <Plus size={14} /> {showForm ? "Cancel" : "New client"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card-flat grid grid-cols-1 md:grid-cols-2 gap-3">
          <input required className="input-flat" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="input-flat" placeholder="Company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
          <input className="input-flat" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input-flat" placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <input className="input-flat md:col-span-2" placeholder="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <button className="btn-primary md:col-span-2">Save client</button>
        </form>
      )}

      <div className="border border-[#E5E5E5]">
        <table className="w-full">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Name</Th><Th>Company</Th><Th>Email</Th><Th>Phone</Th><Th>Added</Th>
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.id} className="border-b border-[#F0F0F0] hover:bg-[#FAFAFA]" data-testid={`client-${c.id}`}>
                <Td className="font-semibold">{c.name}</Td>
                <Td>{c.company || "—"}</Td>
                <Td className="font-mono text-xs">{c.email || "—"}</Td>
                <Td className="font-mono text-xs">{c.phone || "—"}</Td>
                <Td className="font-mono text-xs">{(c.created_at || "").slice(0, 10)}</Td>
              </tr>
            ))}
            {clients.length === 0 && (
              <tr><td colSpan="5" className="p-6 text-center text-[#5C5C5C]">No clients yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const Th = ({ children }) => <th className="px-4 py-3 overline">{children}</th>;
const Td = ({ children, className = "" }) => <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>;
