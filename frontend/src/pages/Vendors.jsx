import { useEffect, useMemo, useState } from "react";
import { formatINR } from "../lib/format";
import { Link, useNavigate } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import {
  Plus, MagnifyingGlass, Star, Buildings, Phone, Envelope, CurrencyInr,
  CaretRight, X, HardHat, PencilSimple, Archive,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import RowActions from "../components/RowActions";
import { usePaged } from "../components/Pager";
import { SkeletonRows, EmptyRow } from "../components/TableState";
import PageHero from "../components/PageHero";

const AGENCY_LABELS = {
  vendor: "Vendor", agency: "Agency", contractor: "Contractor",
  sub_contractor: "Sub-Contractor", supplier: "Supplier",
  consultant: "Consultant", freelancer: "Freelancer", other: "Other",
};

const INR = (n) =>
  formatINR(n, { decimals: 0 });

export default function Vendors() {
  const { hasPerm } = useAuth();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const { pageRows: rowsPage, pager: rowsPager } = usePaged(rows, { key: "vendors" });
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
    setLoaded(true);
    setMeta(m);
  };
  useEffect(() => { load().catch(() => {}).finally(() => setLoaded(true)); /* eslint-disable-next-line */ }, [filterType]);

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
  const canEdit = hasPerm("vendors.update");
  const canArchive = hasPerm("vendors.delete");
  const canSeeContacts = canEdit || hasPerm("finance.read");   // staff lookups don't see phone/email

  const archiveVendor = async (vendor, event) => {
    event.stopPropagation();
    if (!await confirmAction(`Archive ${vendor.name}? Existing bills, payments and accounting history will be preserved.`)) return;
    try {
      await api.delete(`/vendors/${vendor.id}`);
      toast.success("Vendor archived");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not archive vendor");
    }
  };

  return (
    <div className="space-y-6" data-testid="vendors-page">
      <PageHero title="Vendors" count={loaded ? rows.length : undefined}
        kicker="Contractors, agencies and suppliers, with their bills, payments, vendor incentives and ratings.">
        {canCreate && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="btn-primary"
            data-testid="new-vendor-btn"
          >
            {showForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> {"New vendor"}</>}
          </button>
        )}
      </PageHero>

      {/* KPI STRIP */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Kpi label="Vendors" value={rows.length} testid="kpi-vendor-count" />
        <Kpi label="With bills to pay" value={rows.filter((v) => Number(v.outstanding || 0) > 0).length} />
        <Kpi label="Outstanding" value={INR(totalOutstanding)} accent testid="kpi-vendor-outstanding" />
      </div>

      {/* FILTERS */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-1 max-w-md px-3 py-2 border border-[var(--line)] rounded-md focus-within:border-[var(--accent)] transition">
          <MagnifyingGlass size={15} className="text-[var(--ink-2)]" />
          <input
            data-testid="vendor-search"
            className="bg-transparent flex-1 outline-none text-sm placeholder-[var(--ink-3)]"
            placeholder={canSeeContacts ? "Search name, phone, GSTIN, contact…" : "Search vendor name"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <select aria-label="Vendor type"
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
            <select aria-label="Agency type" data-testid="vf-agency-type" className="input-flat" value={form.agency_type}
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
            <input className="input-flat" placeholder="TDS %" type="number" min="0" step="0.01"
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
      <div className="border border-[var(--line)] rounded-md overflow-hidden">
        <div className="overflow-x-auto"><table className="w-full">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
            <tr className="text-left">
              <Th>Vendor</Th><Th>Type</Th>{canSeeContacts && <Th>Contact</Th>}<Th>Category</Th>
              <Th>Rating</Th><Th className="text-right">Outstanding</Th><Th />
            </tr>
          </thead>
          <tbody>
            {!loaded && <SkeletonRows cols={canSeeContacts ? 7 : 6} />}
            {loaded && rows.length === 0 && (q || filterType ? (
              <EmptyRow cols={canSeeContacts ? 7 : 6} icon={HardHat} title="No vendors match" hint="Try a different search or agency type." />
            ) : (
              <EmptyRow cols={canSeeContacts ? 7 : 6} icon={HardHat} title="No vendors yet"
                hint="Add the contractors, agencies and suppliers you work with to track their bills, payments and ratings."
                actionLabel={canCreate ? "Add vendor" : undefined}
                onAction={() => { setShowForm(true); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
            ))}
            {rowsPage.map((v) => (
              <tr
                key={v.id}
                className="border-b border-[var(--line-soft)] hover:bg-[var(--surface-2)] cursor-pointer"
                onClick={() => navigate(`/vendors/${v.id}`)}
                data-testid={`vendor-row-${v.id}`}
              >
                <Td>
                  <div className="font-semibold group-hover:text-[var(--accent-strong)]">
                    <div className="flex items-center gap-2">
                      <Buildings size={14} className="text-[var(--ink-2)]" />
                      {v.name}
                    </div>
                  </div>
                  {v.company && <div className="text-xs text-[var(--ink-3)]">{v.company}</div>}
                </Td>
                <Td><TypePill type={v.agency_type} /></Td>
                {canSeeContacts && <Td>
                  <div className="text-xs space-y-0.5">
                    {v.phone && <div className="flex items-center gap-1.5"><Phone size={11} /> <span className="font-mono">{v.phone}</span></div>}
                    {v.email && <div className="flex items-center gap-1.5"><Envelope size={11} /> {v.email}</div>}
                    {!v.phone && !v.email && "—"}
                  </div>
                </Td>}
                <Td>{v.category || "—"}</Td>
                <Td>
                  {Number(v.rating) > 0 ? (
                    <div className="flex items-center gap-1">
                      <Star size={13} weight="fill" className="text-[#F5B800]" />
                      <span className="font-mono text-xs">{Number(v.rating).toFixed(1)}</span>
                    </div>
                  ) : <span className="text-xs text-[var(--ink-3)]">Not rated</span>}
                </Td>
                <Td className="text-right font-mono">
                  {Number(v.outstanding) > 0 ? (
                    <span className="text-[var(--danger)] font-semibold">{INR(v.outstanding)}</span>
                  ) : <span className="text-[var(--ink-2)]">—</span>}
                </Td>
                <Td className="text-right">
                  <div className="flex items-center justify-end gap-1" onClick={(event) => event.stopPropagation()}>
                    <RowActions label={v.name} testid={`vendor-actions-${v.id}`} actions={[
                      { label: "Edit", icon: PencilSimple, onSelect: () => navigate(`/vendors/${v.id}?edit=1`),
                        hidden: !canEdit, testid: `vendor-edit-${v.id}` },
                      { divider: true },
                      { label: "Archive", icon: Archive, danger: true, onSelect: () => archiveVendor(v, { stopPropagation() {} }),
                        hidden: !canArchive, testid: `vendor-archive-${v.id}` },
                    ]} />
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>{rowsPager}</div>
      </div>
    </div>
  );
}

function Kpi({ label, value, accent, testid }) {
  return (
    <div className={`card-flat ${accent ? "ring-1 ring-[#8B7F6A]/20" : ""}`} data-testid={testid}>
      <div className="overline">{label}</div>
      <div className={`font-display font-bold text-2xl mt-1 ${accent ? "text-[var(--accent-strong)]" : ""}`}>{value}</div>
    </div>
  );
}

function TypePill({ type }) {
  const map = {
    contractor: "bg-[var(--accent-soft)] text-[var(--warning)]",
    sub_contractor: "bg-[var(--accent-soft)] text-[var(--warning)]",
    supplier: "bg-[var(--info-soft)] text-[var(--accent-strong)]",
    agency: "bg-[var(--success-soft)] text-[var(--success)]",
    consultant: "bg-[#F5EEF7] text-[#5B2A83]",
    freelancer: "bg-[#F5EEF7] text-[#5B2A83]",
    vendor: "bg-[var(--line-soft)] text-[var(--ink)]",
    other: "bg-[var(--line-soft)] text-[var(--ink)]",
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
