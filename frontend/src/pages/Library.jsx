import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import {
  Plus, X, Star, MagnifyingGlass, FilePdf, UploadSimple, Copy, Archive, ArrowCounterClockwise,
  Trash, PencilSimple, Tag, ArrowSquareOut, CurrencyInr,
} from "@phosphor-icons/react";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import AuthImage from "../components/AuthImage";
import PdfPreviewModal from "../components/PdfPreview";
import RowActions from "../components/RowActions";
import SearchSelect from "../components/SearchSelect";
import { askForm, confirmAction } from "../lib/confirm";
import { formatDate, formatINR } from "../lib/format";
import { safeExternalUrl } from "../lib/url";

const SOURCE = { manual: "Entered", quote: "Vendor quote", po: "Purchase order" };
const errText = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x?.msg || String(x)).join(" · ") : fallback;
};

function Panel({ title, onClose, children, wide = false, testid }) {
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
      <aside onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title} data-testid={testid}
        className={`relative h-full w-full ${wide ? "max-w-3xl" : "max-w-xl"} bg-white shadow-2xl overflow-y-auto`}>
        <div className="sticky top-0 z-[1] bg-white flex items-start justify-between gap-3 p-5 border-b border-[var(--line)]">
          <div className="font-display font-bold text-xl [overflow-wrap:anywhere]">{title}</div>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5">{children}</div>
      </aside>
    </div>, document.body);
}

const EMPTY = { name: "", brand: "", model: "", sku: "", category: "", finish: "", dimensions: "", unit: "nos",
  warranty: "", product_url: "", default_vendor_id: "", preferred: false, tags: "", notes: "", specs: [{ label: "", value: "" }] };

function ProductForm({ initial, vendors, facets, onClose, onSaved }) {
  const [form, setForm] = useState(() => (initial ? {
    ...EMPTY, ...Object.fromEntries(Object.entries(initial).filter(([k]) => k in EMPTY)),
    tags: (initial.tags || []).join(", "),
    specs: (initial.specs || []).length ? initial.specs : [{ label: "", value: "" }],
    default_vendor_id: initial.default_vendor_id || "",
  } : EMPTY));
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setSpec = (i, k, v) => setForm((f) => ({ ...f, specs: f.specs.map((s, n) => (n === i ? { ...s, [k]: v } : s)) }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error("Give the product a name"); return; }
    const body = {
      ...form,
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      specs: form.specs.filter((s) => s.label.trim()),
      product_url: form.product_url.trim() || null,
      default_vendor_id: form.default_vendor_id || null,
    };
    setBusy(true);
    try {
      const { data } = initial ? await api.patch(`/products/${initial.id}`, body) : await api.post("/products", body);
      toast.success(initial ? "Product updated" : "Product added to the library");
      onSaved(data);
    } catch (ex) { toast.error(errText(ex, "Could not save the product")); setBusy(false); }
  };

  const field = (k, label, props = {}) => (
    <label className="block text-xs text-[var(--ink-2)]">{label}
      <input className="input-flat w-full mt-1" value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} {...props} />
    </label>
  );
  return (
    <Panel title={initial ? `Edit ${initial.name}` : "Add product"} onClose={onClose} testid="product-form">
      <form onSubmit={submit} className="space-y-4">
        {field("name", "Name *", { required: true, placeholder: "BLDC ceiling fan", "data-testid": "product-name" })}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {field("brand", "Brand", { list: "lib-brands", placeholder: "Atomberg" })}
          {field("model", "Model", { placeholder: "Renesa+ 1200" })}
          {field("category", "Category", { list: "lib-categories", placeholder: "Fans" })}
          {field("sku", "SKU / code")}
          {field("finish", "Finish / colour", { placeholder: "Matt black" })}
          {field("dimensions", "Dimensions", { placeholder: "1200 mm sweep" })}
          {field("unit", "Unit", { placeholder: "nos, sq ft, rft" })}
          {field("warranty", "Warranty", { placeholder: "5 years" })}
        </div>
        <datalist id="lib-brands">{(facets.brands || []).map((b) => <option key={b} value={b} />)}</datalist>
        <datalist id="lib-categories">{(facets.categories || []).map((c) => <option key={c} value={c} />)}</datalist>
        <label className="block text-xs text-[var(--ink-2)]">Default vendor
          <SearchSelect className="input-flat w-full mt-1" aria-label="Default vendor" value={form.default_vendor_id}
            onChange={(e) => set("default_vendor_id", e.target.value)} data-testid="product-vendor">
            <option value="">None</option>
            {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </SearchSelect>
        </label>
        {field("product_url", "Product web page (optional)", { type: "url", placeholder: "https://" })}
        {field("tags", "Tags (comma separated)", { placeholder: "BLDC, remote, living room" })}
        <fieldset>
          <legend className="overline mb-2">Specifications</legend>
          {form.specs.map((s, i) => (
            <div key={i} className="grid grid-cols-[1fr_1.4fr_auto] gap-2 mb-2">
              <input className="input-flat" placeholder="Sweep" aria-label="Spec name" value={s.label} onChange={(e) => setSpec(i, "label", e.target.value)} />
              <input className="input-flat" placeholder="1200 mm" aria-label="Spec value" value={s.value} onChange={(e) => setSpec(i, "value", e.target.value)} />
              <button type="button" className="btn-ghost" aria-label="Remove spec" onClick={() => set("specs", form.specs.filter((_, n) => n !== i))}><X size={13} /></button>
            </div>
          ))}
          <button type="button" className="btn-ghost text-xs" onClick={() => set("specs", [...form.specs, { label: "", value: "" }])}><Plus size={12} /> Add spec</button>
        </fieldset>
        <label className="block text-xs text-[var(--ink-2)]">Notes
          <textarea className="input-flat w-full mt-1" rows={3} maxLength={2000} value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!form.preferred} onChange={(e) => set("preferred", e.target.checked)} /> Preferred product (shown first)
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy} data-testid="product-save">{busy ? "Saving…" : initial ? "Save" : "Add product"}</button>
        </div>
      </form>
    </Panel>
  );
}

function ProductDetail({ id, vendors, facets, onClose, onChanged }) {
  const [p, setP] = useState(null);
  const [editing, setEditing] = useState(false);
  const [sheet, setSheet] = useState(null);
  const [active, setActive] = useState(0);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(() => api.get(`/products/${id}`).then(({ data }) => setP(data))
    .catch((e) => { toast.error(errText(e, "Could not open the product")); onClose(); }), [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  const changed = () => { load(); onChanged(); };

  const upload = async (kind, file) => {
    if (!file) return;
    const body = new FormData();
    body.append("kind", kind);
    body.append("upload", file);
    setUploading(true);
    try { await api.post(`/products/${id}/files`, body); toast.success(kind === "image" ? "Image added" : "Datasheet added"); changed(); }
    catch (e) { toast.error(errText(e, "Upload failed")); }
    finally { setUploading(false); }
  };
  const removeFile = async (f) => {
    if (!await confirmAction(`Remove ${f.name}?`)) return;
    try { await api.delete(`/products/${id}/files/${f.id}`); setActive(0); changed(); } catch (e) { toast.error(errText(e, "Could not remove")); }
  };
  const addPrice = async () => {
    const v = await askForm({
      title: "Add a price",
      body: "Prices are kept as history: this adds a new price, earlier ones stay.",
      fields: [
        { name: "price", label: "Price (₹, before GST)", type: "number", required: true },
        { name: "gst_pct", label: "GST %", type: "number", defaultValue: "18" },
        { name: "vendor_id", label: "Vendor", options: [{ value: "", label: p.default_vendor_name ? `${p.default_vendor_name} (default)` : "None" },
          ...vendors.map((x) => ({ value: x.id, label: x.name }))] },
        { name: "unit", label: "Unit", defaultValue: p.unit || "nos" },
        { name: "valid_from", label: "Valid from", type: "date" },
        { name: "source", label: "Source", options: Object.entries(SOURCE).map(([value, label]) => ({ value, label })) },
        { name: "note", label: "Note (optional)", placeholder: "Quote no. 214, Diwali offer" },
      ],
      confirmLabel: "Add price",
    });
    if (!v) return;
    const price = Number(v.price);
    if (!Number.isFinite(price) || price < 0) { toast.error("Enter a valid price"); return; }
    try {
      await api.post(`/products/${id}/prices`, { price, gst_pct: v.gst_pct === "" ? null : Number(v.gst_pct),
        vendor_id: v.vendor_id || null, unit: v.unit || null, valid_from: v.valid_from || null, source: v.source || "manual", note: v.note || null });
      toast.success("Price added");
      changed();
    } catch (e) { toast.error(errText(e, "Could not add the price")); }
  };
  const setStatus = async (status) => {
    if (status === "discontinued" && !await confirmAction(`Mark ${p.name} as discontinued? It stays in old quotations but is hidden from new picks.`)) return;
    try { await api.patch(`/products/${id}`, { status }); toast.success(status === "active" ? "Product reactivated" : "Marked discontinued"); changed(); }
    catch (e) { toast.error(errText(e, "Could not update")); }
  };
  const duplicate = async () => {
    try { const { data } = await api.post(`/products/${id}/duplicate`); toast.success("Copy created"); onChanged(); onClose(data.id); }
    catch (e) { toast.error(errText(e, "Could not duplicate")); }
  };
  const remove = async () => {
    if (!await confirmAction(`Delete ${p.name} and its price history? This cannot be undone.`)) return;
    try { await api.delete(`/products/${id}`); toast.success("Product deleted"); onChanged(); onClose(); }
    catch (e) { toast.error(errText(e, "Could not delete")); }
  };
  const togglePreferred = async () => {
    try { await api.patch(`/products/${id}`, { preferred: !p.preferred }); changed(); } catch (e) { toast.error(errText(e, "Could not update")); }
  };

  if (!p) return <Panel title="Loading…" onClose={() => onClose()} wide><div className="overline">LOADING…</div></Panel>;
  const latest = p.latest_price;
  const link = safeExternalUrl(p.product_url);
  const img = p.images[active] || p.images[0];
  return (
    <Panel title={p.name} onClose={() => onClose()} wide testid="product-detail">
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`status-chip ${p.status === "active" ? "chip-paid" : "chip-cancelled"}`}>{p.status === "active" ? "Active" : "Discontinued"}</span>
          {p.used_in_quotations > 0 && <span className="text-xs text-[var(--ink-2)]">Used in {p.used_in_quotations} quotation{p.used_in_quotations === 1 ? "" : "s"}</span>}
          <span className="ml-auto flex items-center gap-1">
            {p.can_manage && (
              <button type="button" className="btn-ghost text-xs" onClick={togglePreferred} aria-pressed={!!p.preferred} data-testid="product-preferred">
                <Star size={14} weight={p.preferred ? "fill" : "regular"} className={p.preferred ? "text-[var(--accent-strong)]" : ""} /> {p.preferred ? "Preferred" : "Mark preferred"}
              </button>
            )}
            {p.can_manage && <button type="button" className="btn-ghost text-xs" onClick={() => setEditing(true)} data-testid="product-edit"><PencilSimple size={13} /> Edit</button>}
            {p.can_manage && (
              <RowActions label={`product ${p.name}`} actions={[
                { label: "Duplicate", icon: Copy, onSelect: duplicate },
                p.status === "active"
                  ? { label: "Mark discontinued", icon: Archive, onSelect: () => setStatus("discontinued") }
                  : { label: "Reactivate", icon: ArrowCounterClockwise, onSelect: () => setStatus("active") },
                { label: "Delete", icon: Trash, danger: true, divider: true, hidden: !p.can_delete || p.used_in_quotations > 0, onSelect: remove },
              ]} />
            )}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1.1fr_1fr] gap-5">
          <div>
            <AuthImage src={img?.url} alt={p.name} className="w-full aspect-[4/3] object-contain bg-[var(--surface-2)] border border-[var(--line)]"
              fallbackClassName="w-full aspect-[4/3] border border-[var(--line)]" />
            {p.images.length > 1 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {p.images.map((f, n) => (
                  <button key={f.id} type="button" onClick={() => setActive(n)} aria-label={`Show image ${n + 1}`}
                    className={`w-16 h-12 border ${n === active ? "border-[var(--ink)]" : "border-[var(--line)]"}`}>
                    <AuthImage src={f.url} alt="" className="w-full h-full object-cover" />
                  </button>
                ))}
              </div>
            )}
            {p.can_manage && (
              <div className="flex flex-wrap gap-2 mt-3 text-xs">
                <label className="btn-ghost text-xs cursor-pointer">
                  <UploadSimple size={13} /> {uploading ? "Uploading…" : "Add image"}
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" data-testid="product-image-input"
                    onChange={(e) => { upload("image", e.target.files?.[0]); e.target.value = ""; }} />
                </label>
                {img && <button type="button" className="btn-ghost text-xs" onClick={() => removeFile(img)}><Trash size={13} /> Remove this image</button>}
              </div>
            )}
          </div>
          <div className="space-y-3 text-sm">
            <div className="text-[var(--ink-2)]">{[p.brand, p.model].filter(Boolean).join(" · ") || "—"}{p.sku ? ` · ${p.sku}` : ""}</div>
            <div className="border border-[var(--line)] p-3">
              <div className="overline">LATEST PRICE</div>
              {latest ? (
                <>
                  <div className="font-display font-bold text-2xl font-mono">{formatINR(latest.price)} <span className="text-sm font-normal text-[var(--ink-2)]">/ {latest.unit}</span></div>
                  <div className="text-xs text-[var(--ink-2)]">{latest.gst_pct != null ? `+ ${latest.gst_pct}% GST · ` : ""}{latest.vendor_name || "No vendor"} · from {formatDate(latest.valid_from)}</div>
                </>
              ) : <div className="text-[var(--ink-3)]">No price yet</div>}
              {p.can_manage && <button type="button" className="btn-ghost text-xs mt-2" onClick={addPrice} data-testid="product-add-price"><CurrencyInr size={13} /> Add price</button>}
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              {[["Category", p.category], ["Finish", p.finish], ["Dimensions", p.dimensions], ["Unit", p.unit],
                ["Warranty", p.warranty], ["Default vendor", p.default_vendor_name]].filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="contents"><dt className="text-[var(--ink-3)]">{k}</dt><dd className="[overflow-wrap:anywhere]">{v}</dd></div>
              ))}
            </dl>
            {link && <a href={link} target="_blank" rel="noreferrer" className="text-xs text-[var(--accent-strong)] hover:underline inline-flex items-center gap-1">Product page <ArrowSquareOut size={12} /></a>}
            {p.tags?.length > 0 && <div className="flex flex-wrap gap-1">{p.tags.map((t) => <span key={t} className="text-[11px] border border-[var(--line)] px-1.5 py-0.5"><Tag size={10} className="inline" /> {t}</span>)}</div>}
          </div>
        </div>

        {p.specs?.length > 0 && (
          <section>
            <div className="overline mb-1">SPECIFICATIONS</div>
            <table className="w-full text-sm"><tbody>
              {p.specs.map((s, i) => (
                <tr key={i} className="border-t border-[var(--line-soft)]"><td className="py-1.5 pr-4 text-[var(--ink-2)] w-1/3">{s.label}</td><td className="py-1.5 [overflow-wrap:anywhere]">{s.value}</td></tr>
              ))}
            </tbody></table>
          </section>
        )}
        {p.notes && <p className="text-sm text-[var(--ink-2)] whitespace-pre-line [overflow-wrap:anywhere]">{p.notes}</p>}

        <section>
          <div className="flex items-center gap-2 mb-1">
            <div className="overline mr-auto">DATASHEETS</div>
            {p.can_manage && (
              <label className="btn-ghost text-xs cursor-pointer">
                <UploadSimple size={13} /> Add PDF
                <input type="file" accept="application/pdf" className="sr-only" data-testid="product-datasheet-input"
                  onChange={(e) => { upload("datasheet", e.target.files?.[0]); e.target.value = ""; }} />
              </label>
            )}
          </div>
          {p.datasheets.length === 0 ? <p className="text-sm text-[var(--ink-3)]">No datasheets.</p> : (
            <ul className="divide-y divide-[var(--line-soft)] border-y border-[var(--line-soft)]">
              {p.datasheets.map((f) => (
                <li key={f.id} className="py-2 flex items-center gap-2 text-sm">
                  <FilePdf size={16} className="text-[var(--danger)] shrink-0" />
                  <button type="button" className="hover:underline text-left [overflow-wrap:anywhere]" onClick={() => setSheet(f)}>{f.name}</button>
                  {p.can_manage && <button type="button" className="ml-auto btn-ghost text-xs" aria-label={`Remove ${f.name}`} onClick={() => removeFile(f)}><Trash size={13} /></button>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="overline mb-1">PRICE HISTORY</div>
          {p.prices.length === 0 ? <p className="text-sm text-[var(--ink-3)]">No prices recorded.</p> : (
            <div className="overflow-x-auto border border-[var(--line)]">
              <table className="w-full text-sm min-w-[560px]" data-testid="product-prices">
                <thead className="bg-[var(--surface-2)]"><tr className="overline text-left">
                  <th className="p-2">From</th><th className="p-2">Vendor</th><th className="p-2 text-right">Price</th><th className="p-2">GST</th><th className="p-2">Source</th><th className="p-2">Added by</th>
                </tr></thead>
                <tbody>
                  {p.prices.map((r, i) => (
                    <tr key={r.id} className={`border-t border-[var(--line-soft)] ${i === 0 ? "font-semibold" : ""}`}>
                      <td className="p-2 whitespace-nowrap">{formatDate(r.valid_from)}</td>
                      <td className="p-2">{r.vendor_name || "—"}</td>
                      <td className="p-2 text-right font-mono whitespace-nowrap">{formatINR(r.price)} / {r.unit}</td>
                      <td className="p-2">{r.gst_pct != null ? `${r.gst_pct}%` : "—"}</td>
                      <td className="p-2 text-xs">{SOURCE[r.source] || r.source}{r.note ? <div className="text-[var(--ink-3)] font-normal">{r.note}</div> : null}</td>
                      <td className="p-2 text-xs font-normal">{r.created_by_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
      {editing && <ProductForm initial={p} vendors={vendors} facets={facets} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); changed(); }} />}
      {sheet && <PdfPreviewModal path={sheet.url.slice(4)} title={sheet.name} filename={sheet.name} onClose={() => setSheet(null)} />}
    </Panel>
  );
}

/** Studio product & material library: the products a studio specifies again and again. */
export default function Library() {
  const [data, setData] = useState(null);
  const [vendors, setVendors] = useState([]);
  const [filters, setFilters] = useState({ q: "", category: "", brand: "", preferred: false, status: "active" });
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(() => {
    const params = { page, page_size: 48, status: filters.status, q: query || undefined,
      category: filters.category || undefined, brand: filters.brand || undefined, preferred: filters.preferred ? true : undefined };
    return api.get("/products", { params }).then(({ data: d }) => setData(d))
      .catch((e) => { setData({ items: [], total: 0, facets: {} }); toast.error(errText(e, "Could not load the library")); });
  }, [filters, query, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setTimeout(() => { setQuery(filters.q.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [filters.q]);
  useEffect(() => { api.get("/vendors").then(({ data: v }) => setVendors(Array.isArray(v) ? v : v.vendors || [])).catch(() => setVendors([])); }, []);

  const facets = data?.facets || {};
  const pages = data ? Math.max(1, Math.ceil(data.total / (data.page_size || 48))) : 1;
  const setF = (k, v) => { setFilters((f) => ({ ...f, [k]: v })); if (k !== "q") setPage(1); };
  const activeFilters = useMemo(() => [filters.category, filters.brand, filters.preferred, filters.status !== "active", query].filter(Boolean).length, [filters, query]);

  return (
    <div className="space-y-6" data-testid="library-page">
      <PageHero title="Product library" count={data ? data.total : undefined}
        kicker="The products and materials your studio specifies again and again, with photos, datasheets and price history. Add them to quotations in one click.">
        {data?.can_manage && <button type="button" className="btn-primary" onClick={() => setCreating(true)} data-testid="product-new"><Plus size={14} /> Add product</button>}
      </PageHero>

      <div className="flex flex-wrap items-center gap-2">
        <label className="relative flex-1 min-w-[200px] max-w-md">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
          <input className="input-flat w-full pl-8" placeholder="Search name, brand, model, SKU, tag" aria-label="Search the library"
            value={filters.q} onChange={(e) => setF("q", e.target.value)} data-testid="library-search" />
        </label>
        <select className="input-flat text-sm" aria-label="Category" value={filters.category} onChange={(e) => setF("category", e.target.value)}>
          <option value="">All categories</option>
          {(facets.categories || []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="input-flat text-sm" aria-label="Brand" value={filters.brand} onChange={(e) => setF("brand", e.target.value)}>
          <option value="">All brands</option>
          {(facets.brands || []).map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <select className="input-flat text-sm" aria-label="Status" value={filters.status} onChange={(e) => setF("status", e.target.value)}>
          <option value="active">Active</option>
          <option value="discontinued">Discontinued</option>
          <option value="all">All</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={filters.preferred} onChange={(e) => setF("preferred", e.target.checked)} /> Preferred only</label>
        {activeFilters > 0 && (
          <button type="button" className="btn-ghost text-xs" onClick={() => { setFilters({ q: "", category: "", brand: "", preferred: false, status: "active" }); setPage(1); }}>Clear</button>
        )}
      </div>

      {!data && <div className="overline p-4">LOADING…</div>}
      {data && data.items.length === 0 && (
        <div className="border border-[var(--line)] p-10 text-center text-sm text-[var(--ink-3)]">
          {activeFilters ? "No products match these filters." : "The library is empty. Add the products you use most (a fan, a fitting, a laminate) and reuse them in every quotation."}
        </div>
      )}
      {data && data.items.length > 0 && (
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4" data-testid="library-grid">
          {data.items.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => setOpenId(p.id)} data-testid={`product-card-${p.id}`}
                className={`w-full text-left border border-[var(--line)] bg-white hover:border-[var(--ink)] transition ${p.status !== "active" ? "opacity-70" : ""}`}>
                <div className="relative">
                  <AuthImage src={p.cover_url} alt={p.name} className="w-full aspect-[4/3] object-contain bg-[var(--surface-2)]" fallbackClassName="w-full aspect-[4/3]" />
                  {p.preferred && <span className="absolute top-2 left-2 bg-white/90 px-1.5 py-0.5 text-[10px] font-semibold inline-flex items-center gap-1"><Star size={11} weight="fill" className="text-[var(--accent-strong)]" /> Preferred</span>}
                  {p.status !== "active" && <span className="absolute top-2 right-2 status-chip chip-cancelled">Discontinued</span>}
                </div>
                <div className="p-3 space-y-1">
                  <div className="font-semibold leading-snug [overflow-wrap:anywhere]">{p.name}</div>
                  <div className="text-xs text-[var(--ink-2)] truncate">{[p.brand, p.model].filter(Boolean).join(" · ") || "—"}</div>
                  <div className="flex items-baseline justify-between gap-2 pt-1">
                    <span className="font-mono text-sm font-semibold">{p.latest_price ? `${formatINR(p.latest_price.price)} / ${p.latest_price.unit}` : <span className="text-[var(--ink-3)] font-sans font-normal text-xs">No price</span>}</span>
                    {p.category && <span className="text-[10px] uppercase tracking-wide text-[var(--ink-3)] truncate">{p.category}</span>}
                  </div>
                  {(p.latest_price?.vendor_name || p.default_vendor_name) && <div className="text-[11px] text-[var(--ink-3)] truncate">{p.latest_price?.vendor_name || p.default_vendor_name}</div>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {data && pages > 1 && (
        <div className="flex items-center justify-center gap-2 text-sm">
          <button type="button" className="btn-ghost text-xs" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button type="button" className="btn-ghost text-xs" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}

      {creating && <ProductForm vendors={vendors} facets={facets} onClose={() => setCreating(false)}
        onSaved={(p) => { setCreating(false); load(); setOpenId(p.id); }} />}
      {openId && <ProductDetail key={openId} id={openId} vendors={vendors} facets={facets} onChanged={load}
        onClose={(next) => setOpenId(typeof next === "string" ? next : null)} />}
    </div>
  );
}
