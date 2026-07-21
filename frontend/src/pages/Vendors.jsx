import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  Plus, MagnifyingGlass, Star, Buildings, Phone, Envelope, CurrencyInr,
  CaretRight, X, HardHat,
} from "@phosphor-icons/react";

const AGENCY_LABELS = {
  vendor: "Vendor", agency: "Agency", contractor: "Contractor",
  sub_contractor: "Sub-Contractor", supplier: "Supplier",
  consultant: "Consultant", freelancer: "Freelancer", other: "Other",
};

const INR = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(n || 0));

export default function Vendors() {
  const { hasPerm } = useAuth();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ agency_types: [] });
  const [q, setQ] = useState("");
  const [filterType, setFilterType] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(initial());

  function initial() {
    return {
      name: "", company: "", agency_type: "vendor", contact_person: "",
      phone: "", email: "", city: "", state: "", pincode: "", address: "",
      gstin: "", pan: "", tds_applicable: false, tds_rate: 0,
      bank_name: "", bank_account_number: "", bank_ifsc: "", bank_branch: "", upi_id: "",
      category: "", notes: "",
    };
  }

  const load = async () => {
    const params = {};
    if (q) params.q = q;
    if (filterType) params.agency_type = filterType;
    const [{ data: v }, { data: m }] = await Promise.all([
      api.get("/vendors", { params }),
      api.get("/vendors/meta"),
    ]);
    setRows(v);
    setMeta(m);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filterType]);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/vendors", form);
      setForm(initial());
      setShowForm(false);
      await load();
    } finally { setSaving(false); }
  };

  const totalOutstanding = useMemo(
    () => rows.reduce((s, v) => s + Number(v.outstanding || 0), 0),
    [rows]
  );

  const canCreate = hasPerm("vendors.create");

  return (
    <div className="space-y-6" data-testid="vendors-page">
      {/* HERO */}
      <div className="flex items-end justify-between gap-6 flex-wrap">
        <div>
          <div className="overline mb-1">DIRECTORY / VENDORS &amp; AGENCIES</div>
          <h1 className="font-display font-bold tracking-tight text-4xl">
            Every hand that builds. In one place.
          </h1>
          <p className="text-[#5C5C5C] mt-2 max-w-xl">
            Master data for contractors, agencies and suppliers — with live bills, running ledger and performance signals.
          </p>
        </div>
        {canCreate && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="btn-primary"
            data-testid="new-vendor-btn"
          >
            <Plus size={14} /> {showForm ? "Cancel" : "New vendor"}
          </button>
        )}
      </div>

      {/* KPI STRIP */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Kpi label="Vendors" value={rows.length} testid="kpi-vendor-count" />
        <Kpi label="Contractors" value={rows.filter((v) => v.agency_type === "contractor").length} />
        <Kpi label="Suppliers" value={rows.filter((v) => v.agency_type === "supplier").length} />
        <Kpi label="Outstanding" value={INR(totalOutstanding)} accent testid="kpi-vendor-outstanding" />
      </div>

      {/* FILTERS */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-1 max-w-md px-3 py-2 border border-[#E5E5E5] focus-within:border-[#002FA7] transition">
          <MagnifyingGlass size={15} className="text-[#5C5C5C]" />
          <input
            data-testid="vendor-search"
            className="bg-transparent flex-1 outline-none text-sm placeholder-[#9A9A9A]"
            placeholder="Search name, phone, GSTIN, contact…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <select
          data-testid="vendor-filter-type"
          className="input-flat max-w-[220px]"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">All types</option>
          {(meta.agency_types || []).map((t) => (
            <option key={t} value={t}>{AGENCY_LABELS[t] || t}</option>
          ))}
        </select>
      </div>

      {/* CREATE FORM */}
      {showForm && (
        <form onSubmit={submit} className="card-flat space-y-4" data-testid="vendor-form">
          <div className="overline">01 · Identity</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input required data-testid="vf-name" className="input-flat" placeholder="Vendor / Agency name *"
              value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="input-flat" placeholder="Legal / company name"
              value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
            <select data-testid="vf-agency-type" className="input-flat" value={form.agency_type}
              onChange={(e) => setForm({ ...form, agency_type: e.target.value })}>
              {(meta.agency_types || []).map((t) => (
                <option key={t} value={t}>{AGENCY_LABELS[t] || t}</option>
              ))}
            </select>
            <input className="input-flat" placeholder="Contact person"
              value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} />
            <input className="input-flat" placeholder="Phone" data-testid="vf-phone"
              value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <input className="input-flat" placeholder="Email" type="email"
              value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <input className="input-flat" placeholder="Category (e.g. Carpenter, Marble)"
              value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
            <input className="input-flat" placeholder="City"
              value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
            <input className="input-flat" placeholder="State"
              value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} />
            <input className="input-flat md:col-span-3" placeholder="Full address"
              value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>

          <div className="overline pt-2">02 · Compliance</div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <input className="input-flat" placeholder="GSTIN"
              value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value.toUpperCase() })} />
            <input className="input-flat" placeholder="PAN"
              value={form.pan} onChange={(e) => setForm({ ...form, pan: e.target.value.toUpperCase() })} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.tds_applicable}
                onChange={(e) => setForm({ ...form, tds_applicable: e.target.checked })} />
              TDS applicable
            </label>
            <input className="input-flat" placeholder="TDS %" type="number" step="0.01"
              disabled={!form.tds_applicable}
              value={form.tds_rate} onChange={(e) => setForm({ ...form, tds_rate: parseFloat(e.target.value) || 0 })} />
          </div>

          <div className="overline pt-2">03 · Banking</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input className="input-flat" placeholder="Bank name"
              value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
            <input className="input-flat" placeholder="Account number"
              value={form.bank_account_number} onChange={(e) => setForm({ ...form, bank_account_number: e.target.value })} />
            <input className="input-flat" placeholder="IFSC"
              value={form.bank_ifsc} onChange={(e) => setForm({ ...form, bank_ifsc: e.target.value.toUpperCase() })} />
            <input className="input-flat" placeholder="Branch"
              value={form.bank_branch} onChange={(e) => setForm({ ...form, bank_branch: e.target.value })} />
            <input className="input-flat" placeholder="UPI id"
              value={form.upi_id} onChange={(e) => setForm({ ...form, upi_id: e.target.value })} />
          </div>

          <textarea className="input-flat w-full min-h-[70px]" placeholder="Internal notes"
            value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />

          <div className="flex items-center gap-3">
            <button disabled={saving} className="btn-primary" data-testid="save-vendor-btn">
              {saving ? "Saving…" : "Save vendor"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="btn-ghost">
              <X size={14} /> Cancel
            </button>
          </div>
        </form>
      )}

      {/* LIST */}
      <div className="border border-[#E5E5E5]">
        <table className="w-full">
          <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5]">
            <tr className="text-left">
              <Th>Vendor</Th><Th>Type</Th><Th>Contact</Th><Th>Category</Th>
              <Th>Rating</Th><Th className="text-right">Outstanding</Th><Th />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="p-12 text-center text-[#5C5C5C]">
                  <HardHat size={26} className="mx-auto text-[#9A9A9A] mb-3" />
                  <div className="overline mb-1">EMPTY</div>
                  No vendors yet. Add your first one.
                </td>
              </tr>
            )}
            {rows.map((v) => (
              <tr key={v.id} className="border-b border-[#F0F0F0] hover:bg-[#FAFAFA]" data-testid={`vendor-row-${v.id}`}>
                <Td>
                  <Link to={`/vendors/${v.id}`} className="font-semibold hover:text-[#002FA7]">
                    <div className="flex items-center gap-2">
                      <Buildings size={14} className="text-[#5C5C5C]" />
                      {v.name}
                    </div>
                  </Link>
                  {v.company && <div className="text-xs text-[#9A9A9A]">{v.company}</div>}
                </Td>
                <Td><TypePill type={v.agency_type} /></Td>
                <Td>
                  <div className="text-xs space-y-0.5">
                    {v.phone && <div className="flex items-center gap-1.5"><Phone size={11} /> <span className="font-mono">{v.phone}</span></div>}
                    {v.email && <div className="flex items-center gap-1.5"><Envelope size={11} /> {v.email}</div>}
                    {!v.phone && !v.email && "—"}
                  </div>
                </Td>
                <Td>{v.category || "—"}</Td>
                <Td>
                  <div className="flex items-center gap-1">
                    <Star size={13} weight="fill" className="text-[#F5B800]" />
                    <span className="font-mono text-xs">{Number(v.rating || 0).toFixed(1)}</span>
                  </div>
                </Td>
                <Td className="text-right font-mono">
                  {Number(v.outstanding) > 0 ? (
                    <span className="text-[#B22B22] font-semibold">{INR(v.outstanding)}</span>
                  ) : <span className="text-[#5C5C5C]">—</span>}
                </Td>
                <Td className="text-right">
                  <Link to={`/vendors/${v.id}`} className="text-[#002FA7] text-xs font-semibold flex items-center gap-1 justify-end">
                    Open <CaretRight size={11} weight="bold" />
                  </Link>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Kpi({ label, value, accent, testid }) {
  return (
    <div className={`card-flat ${accent ? "ring-1 ring-[#002FA7]/20" : ""}`} data-testid={testid}>
      <div className="overline">{label}</div>
      <div className={`font-display font-bold text-2xl mt-1 ${accent ? "text-[#002FA7]" : ""}`}>{value}</div>
    </div>
  );
}

function TypePill({ type }) {
  const map = {
    contractor: "bg-[#F5F1EB] text-[#7A4E1A]",
    sub_contractor: "bg-[#F5F1EB] text-[#7A4E1A]",
    supplier: "bg-[#EEF2FF] text-[#002FA7]",
    agency: "bg-[#EFF7EF] text-[#1D633E]",
    consultant: "bg-[#F5EEF7] text-[#5B2A83]",
    freelancer: "bg-[#F5EEF7] text-[#5B2A83]",
    vendor: "bg-[#F2F2F2] text-[#0A0A0A]",
    other: "bg-[#F2F2F2] text-[#0A0A0A]",
  };
  return (
    <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 ${map[type] || map.vendor}`}>
      {AGENCY_LABELS[type] || type || "vendor"}
    </span>
  );
}

const Th = ({ children, className = "" }) => (
  <th className={`px-4 py-3 overline ${className}`}>{children}</th>
);
const Td = ({ children, className = "" }) => (
  <td className={`px-4 py-3 text-sm ${className}`}>{children}</td>
);
