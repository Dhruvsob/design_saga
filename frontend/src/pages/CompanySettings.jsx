import { useEffect, useRef, useState } from "react";
import api, { API } from "../lib/api";
import SignaturePad from "../components/SignaturePad";
import { confirmAction } from "../lib/confirm";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import MasterDataManager from "../components/MasterDataManager";
import {
  Palette, Buildings, Upload, Check, Warning, PaintBrush, ImageSquare, X,
  ListChecks,
} from "@phosphor-icons/react";

const BRAND_PDF_COLOUR = "#76705E";   // matches backend core.pdf_brand.BRAND_PRIMARY
const LEGACY_PDF_BLUE = "#002FA7";

function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}

export default function CompanySettings() {
  const { currentOrg, refreshOrg } = useAuth();
  const [tab, setTab] = useState("branding");
  const [org, setOrg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [logoBroken, setLogoBroken] = useState(false);   // show initials if the image cannot load
  const [err, setErr] = useState("");
  const fileRef = useRef(null);
  const sigFileRef = useRef(null);
  const [sigMode, setSigMode] = useState(null);        // null | "draw"
  const [sigBusy, setSigBusy] = useState(false);
  const [sigVersion, setSigVersion] = useState(Date.now());
  const [sigMsg, setSigMsg] = useState("");

  const saveSignature = async (dataUrl) => {
    setSigBusy(true); setSigMsg("");
    try {
      const { data } = await api.post("/org/current/signature", { signature_data_url: dataUrl });
      setOrg((o) => ({ ...o, has_signature: data.has_signature }));
      setSigVersion(Date.now()); setSigMode(null);
      setSigMsg("Signature saved. It now prints on invoices, payment reminders and salary slips.");
    } catch (e) {
      setSigMsg(e?.response?.data?.detail || "Could not save the signature");
    } finally { setSigBusy(false); }
  };
  const uploadSignature = (file) => {
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
      setSigMsg("Use a PNG, JPEG or WebP image — or draw the signature with Apple Pencil above.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => saveSignature(reader.result);
    reader.readAsDataURL(file);
  };
  const removeSignature = async () => {
    if (!await confirmAction("Remove the signature? PDFs will show only the signature line.")) return;
    try {
      const { data } = await api.delete("/org/current/signature");
      setOrg((o) => ({ ...o, has_signature: data.has_signature }));
      setSigMsg("Signature removed.");
    } catch (e) { setSigMsg(e?.response?.data?.detail || "Could not remove the signature"); }
  };

  useEffect(() => { setOrg(currentOrg); }, [currentOrg]);
  useEffect(() => { setLogoBroken(false); }, [org?.branding?.logo_url]);

  const setBranding = (patch) => {
    if ("logo_url" in patch) setLogoBroken(false);
    return setBrandingRaw(patch);
  };
  const setBrandingRaw = (patch) =>
    setOrg((o) => ({ ...o, branding: { ...(o?.branding || {}), ...patch } }));
  const setField = (k, v) => setOrg((o) => ({ ...o, [k]: v }));
  const setAddress = (patch) => setOrg((o) => ({ ...o, address: { ...(o?.address || {}), ...patch } }));
  const setBank = (patch) => setOrg((o) => ({ ...o, bank_details: { ...(o?.bank_details || {}), ...patch } }));

  const save = async () => {
    setSaving(true); setErr(""); setSaved(false);
    try {
      const payload = {
        display_name: org.display_name,
        phone: org.phone, website: org.website,
        gstin: org.gstin, pan: org.pan,
        branding: org.branding, address: org.address,
        bank_details: org.bank_details,
        accounting_basis: org.accounting_basis || "cash",
      };
      await api.patch("/org/current", payload);
      await refreshOrg();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setErr(fmtErr(e?.response?.data?.detail, "Save failed"));
    } finally { setSaving(false); }
  };

  const onLogoPick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setErr("Logo must be under 2MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      const dataUrl = reader.result;
      setSaving(true); setErr("");
      try {
        const { data } = await api.post("/org/current/logo", { logo_data_url: dataUrl });
        await refreshOrg();
        setBranding({ logo_url: data.logo_url });
      } catch (ex) {
        setErr(fmtErr(ex?.response?.data?.detail, "Upload failed"));
      } finally { setSaving(false); }
    };
    reader.readAsDataURL(file);
  };

  if (!org) {
    return <div className="skeleton h-96 w-full"></div>;
  }

  const branding = org.branding || {};
  // PDFs print in the brand taupe unless the studio picked its own colour; the old
  // blue default (#002FA7) was never chosen by anyone, so it counts as "not set".
  const pdfColour = (!branding.primary_color || branding.primary_color.toUpperCase() === LEGACY_PDF_BLUE)
    ? BRAND_PDF_COLOUR : branding.primary_color;

  return (
    <div className="space-y-8" data-testid="company-settings-page">
      <PageHero
        eyebrow="ADMIN / COMPANY"
        title="Company settings"
        kicker={org?.business_mode
          ? `Business mode: ${(org.business_mode || "hybrid").toUpperCase()} · Logo, colours and company info flow into the sidebar, login screen, PDFs and every export.`
          : "Logo, colours and company info flow into the sidebar, login screen, PDFs and every export."}
      >
        {saved && (
          <span className="text-xs text-[var(--success)] font-mono flex items-center gap-1" data-testid="saved-indicator">
            <Check size={13} /> SAVED
          </span>
        )}
        <button disabled={saving} onClick={save} className="btn-primary" data-testid="save-branding-btn">
          {saving ? "Saving…" : "Save changes"}
        </button>
      </PageHero>

      {err && (
        <div className="border border-[var(--danger)] bg-[var(--danger-soft)] p-4 text-sm text-[var(--danger)] flex items-center gap-2">
          <Warning size={14} /> {err}
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[var(--line)]">
        {[
          { key: "branding", label: "Brand & Colours", Icon: Palette },
          { key: "profile",  label: "Company Profile", Icon: Buildings },
          { key: "masterdata", label: "Master Data", Icon: ListChecks },
        ].map(({ key, label, Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-3 text-sm font-semibold border-b-2 transition ${
              tab === key ? "border-[var(--accent)] text-[var(--accent-strong)]" : "border-transparent text-[var(--ink-2)] hover:text-[var(--ink)]"
            }`}
            data-testid={`tab-${key}`}
          >
            <Icon size={13} className="inline mr-1.5" /> {label}
          </button>
        ))}
      </div>

      {tab === "branding" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Form */}
          <div className="lg:col-span-2 space-y-6">
            <div className="card-flat">
              <div className="overline mb-4"><ImageSquare size={11} className="inline mr-1"/> LOGO</div>
              <div className="flex items-center gap-4">
                {branding.logo_url && !logoBroken ? (
                  <img src={branding.logo_url} alt="Current logo" onError={() => setLogoBroken(true)} className="w-28 h-28 object-contain ring-1 ring-[var(--line)] bg-white p-2 rounded-lg" data-testid="logo-preview" />
                ) : (
                  <div className="w-20 h-20 flex items-center justify-center text-white font-display font-bold text-lg ring-1 ring-[var(--line)]"
                       style={{ backgroundColor: pdfColour }}>
                    {(org.name || "DS").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div>
                  <button onClick={() => fileRef.current?.click()} className="btn-primary" disabled={saving}
                          data-testid="upload-logo-btn">
                    <Upload size={12} /> {saving ? "Uploading…" : branding.logo_url ? "Replace logo" : "Upload logo"}
                  </button>
                  <div className="text-xs text-[var(--ink-2)] mt-2 max-w-xs">
                    PNG, JPG or WebP, up to 2 MB. A transparent PNG looks best. Empty borders are trimmed
                    automatically; the logo is used in the sidebar and on every PDF.
                  </div>
                  {branding.logo_url && (
                    <button onClick={() => setBranding({ logo_url: null })}
                            className="btn-ghost text-xs mt-1" data-testid="remove-logo-btn">
                      <X size={10} /> Remove logo
                    </button>
                  )}
                </div>
                <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                       onChange={(e) => { onLogoPick(e); e.target.value = ""; }} aria-label="Logo file" />
              </div>
            </div>

            <div className="card-flat">
              <div className="overline mb-4"><PaintBrush size={11} className="inline mr-1"/> COLOURS</div>
              <div className="grid grid-cols-2 gap-4">
                <ColorField label="PDF colour" value={pdfColour}
                            onChange={(v) => setBranding({ primary_color: v })} testid="color-primary" />
                <div className="self-end text-xs text-[var(--ink-2)] leading-relaxed">
                  Headings and rules on invoices, quotations, proposals and payslips. The app itself keeps the Design Saga palette.
                  {pdfColour.toUpperCase() !== BRAND_PDF_COLOUR && (
                    <button type="button" className="block mt-2 underline underline-offset-4 text-[var(--ink)]"
                            onClick={() => setBranding({ primary_color: BRAND_PDF_COLOUR })} data-testid="color-reset">
                      Use Design Saga colour
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-4">
                <label className="block text-xs text-[var(--ink-2)] mb-1">Tagline (shown in sidebar)</label>
                <input className="input-flat w-full" placeholder="Studio management"
                       value={branding.tagline || ""} onChange={(e) => setBranding({ tagline: e.target.value })}
                       data-testid="tagline-input" />
              </div>
              <div className="mt-4">
                <label className="block text-xs text-[var(--ink-2)] mb-1">PDF Footer note (appears on invoices, quotes, slips)</label>
                <input className="input-flat w-full" placeholder="e.g. Thank you for your business — Design Saga"
                       value={branding.pdf_footer || ""} onChange={(e) => setBranding({ pdf_footer: e.target.value })}
                       data-testid="pdf-footer-input" />
              </div>
            </div>
            <div className="card-flat" data-testid="signature-card">
              <div className="overline mb-1">SIGNATURE ON PDFs</div>
              <p className="text-xs text-[var(--ink-2)] mb-3">
                Printed above “Authorised Signatory” on invoices, payment reminders and salary slips.
                Draw it here with Apple Pencil on your iPad, or upload a PNG / JPEG / WebP. A white paper background is removed automatically.
              </p>
              {org.has_signature && sigMode !== "draw" && (
                <div className="flex items-center gap-4 flex-wrap mb-3">
                  <div className="border border-[var(--line)] rounded-lg bg-white px-4 py-2">
                    <img src={`${API}/org/current/signature?v=${sigVersion}`} alt="Saved signature" className="h-16 object-contain" data-testid="signature-preview" />
                  </div>
                  <button type="button" className="btn-ghost text-xs" onClick={removeSignature}>Remove</button>
                </div>
              )}
              {sigMode === "draw" ? (
                <>
                  <SignaturePad onSave={saveSignature} saving={sigBusy} />
                  <button type="button" className="btn-ghost text-xs mt-2" onClick={() => setSigMode(null)}>Cancel</button>
                </>
              ) : (
                <div className="flex gap-2 flex-wrap">
                  <button type="button" className="btn-primary text-xs" onClick={() => { setSigMode("draw"); setSigMsg(""); }} data-testid="signature-draw">
                    {org.has_signature ? "Draw a new signature" : "Draw signature"}
                  </button>
                  <button type="button" className="btn-ghost text-xs" onClick={() => sigFileRef.current?.click()} disabled={sigBusy}>
                    Upload image
                  </button>
                  <input ref={sigFileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                         onChange={(e) => { uploadSignature(e.target.files?.[0]); e.target.value = ""; }} data-testid="signature-file" />
                </div>
              )}
              {sigMsg && <p className="text-xs mt-2 text-[var(--ink-2)]" data-testid="signature-msg">{sigMsg}</p>}
            </div>
          </div>

          {/* Right column: Live preview */}
          <div className="space-y-4">
            <div className="card-flat sticky top-24">
              <div className="overline mb-3">LIVE PREVIEW</div>
              {/* Sidebar preview */}
              <div className="border border-[var(--line)] p-4 flex items-center gap-3 mb-4">
                {branding.logo_url && !logoBroken ? (
                  <img src={branding.logo_url} alt="" onError={() => setLogoBroken(true)} className="h-10 w-auto max-w-[64px] object-contain" />
                ) : (
                  <div className="w-9 h-9 flex items-center justify-center text-white font-display font-bold text-sm"
                       style={{ backgroundColor: pdfColour }}>
                    {(org.name || "DS").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div>
                  <div className="font-display font-bold tracking-tight text-sm">
                    {(org.display_name || org.name || "").toUpperCase()}
                  </div>
                  <div className="text-[10px] text-[var(--ink-2)] font-mono uppercase">
                    {branding.tagline || "STUDIO OS"}
                  </div>
                </div>
              </div>
              {/* Invoice header preview */}
              <div>
                <div className="overline mb-2 text-[9px]">INVOICE HEADER</div>
                <div className="border border-[var(--line)] p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-display font-bold" style={{ color: pdfColour }}>
                        {org.display_name || org.name}
                      </div>
                      <div className="text-[10px] text-[var(--ink-2)] font-mono">
                        GSTIN: {org.gstin || "—"}
                      </div>
                    </div>
                    {branding.logo_url && (
                      <img src={branding.logo_url} alt="" className="w-10 h-10 object-contain" />
                    )}
                  </div>
                  <div className="mt-2 h-[3px]" style={{ background: pdfColour }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "profile" && (
        <div className="max-w-3xl space-y-6">
          <div className="card-flat">
            <div className="overline mb-4">COMPANY INFO</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Display name" value={org.display_name || ""} onChange={(v) => setField("display_name", v)} testid="cs-display-name" />
              <Field label="Legal name" value={org.name || ""} readOnly hint="Contact Super Admin to rename" />
              <Field label="Phone" value={org.phone || ""} onChange={(v) => setField("phone", v)} testid="cs-phone" />
              <Field label="Website" value={org.website || ""} onChange={(v) => setField("website", v)} testid="cs-website" />
              <Field label="GSTIN" value={org.gstin || ""} onChange={(v) => setField("gstin", v)} testid="cs-gstin" />
              <Field label="PAN" value={org.pan || ""} onChange={(v) => setField("pan", v)} testid="cs-pan" />
            </div>
          </div>
          <div className="card-flat">
            <div className="overline mb-4">ADDRESS</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Line 1" value={org.address?.line1 || ""} onChange={(v) => setAddress({ line1: v })} testid="cs-addr1" />
              <Field label="Line 2" value={org.address?.line2 || ""} onChange={(v) => setAddress({ line2: v })} />
              <Field label="City" value={org.address?.city || ""} onChange={(v) => setAddress({ city: v })} testid="cs-city" />
              <Field label="State" value={org.address?.state || ""} onChange={(v) => setAddress({ state: v })} />
              <Field label="Pincode" value={org.address?.pincode || ""} onChange={(v) => setAddress({ pincode: v })} />
              <Field label="Country" value={org.address?.country || "India"} onChange={(v) => setAddress({ country: v })} />
            </div>
          </div>
          <div className="card-flat">
            <div className="overline mb-4">BILLING &amp; BANK DETAILS</div>
            <p className="text-xs text-[var(--ink-2)] mb-3">
              These details are printed in the &ldquo;Payment Details&rdquo; box on every invoice PDF.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Account name" value={org.bank_details?.account_name || ""} onChange={(v) => setBank({ account_name: v })} testid="cs-bank-account-name" />
              <Field label="Bank name" value={org.bank_details?.bank || ""} onChange={(v) => setBank({ bank: v })} testid="cs-bank-name" />
              <Field label="Account number" value={org.bank_details?.account || ""} onChange={(v) => setBank({ account: v })} testid="cs-bank-account" />
              <Field label="IFSC code" value={org.bank_details?.ifsc || ""} onChange={(v) => setBank({ ifsc: v })} testid="cs-bank-ifsc" />
              <Field label="UPI ID" value={org.bank_details?.upi || ""} onChange={(v) => setBank({ upi: v })} testid="cs-bank-upi" />
            </div>
          </div>
          <div className="card-flat">
            <div className="overline mb-4">WHEN IS INCOME BOOKED?</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3" role="radiogroup" aria-label="Accounting basis">
              {[["cash", "When money is received (recommended)",
                 "An invoice or reminder books nothing. Income is recorded only when you record a payment, for the amount actually received."],
                ["accrual", "When the invoice is sent",
                 "Sending an invoice books its full value as income owed; payments then settle it. Use only if your CA asks for it."]].map(([id, title, body]) => (
                <label key={id} className={`border rounded-lg p-3 cursor-pointer ${(org.accounting_basis || "cash") === id ? "border-[var(--accent-strong)] bg-[var(--surface-2)]" : "border-[var(--line)]"}`}>
                  <input type="radio" name="accounting_basis" className="mr-2" checked={(org.accounting_basis || "cash") === id}
                         onChange={() => setOrg((o) => ({ ...o, accounting_basis: id }))} data-testid={`cs-basis-${id}`} />
                  <span className="font-semibold text-sm">{title}</span>
                  <p className="text-xs text-[var(--ink-2)] mt-1">{body}</p>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "masterdata" && (
        <div className="space-y-4">
          <p className="text-sm text-[var(--ink-2)] max-w-2xl">
            Configure the dropdown values used across the ERP — project types, lead sources,
            task categories, designations and more. Values referenced by existing records are
            deactivated instead of deleted, so history is never broken.
          </p>
          <MasterDataManager />
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange, testid, readOnly, hint }) {
  return (
    <div>
      <label className="block text-xs text-[var(--ink-2)] mb-1">{label}</label>
      <input className="input-flat w-full" value={value} readOnly={readOnly}
             onChange={onChange ? (e) => onChange(e.target.value) : undefined}
             data-testid={testid} />
      {hint && <div className="text-[10px] text-[var(--ink-3)] mt-1">{hint}</div>}
    </div>
  );
}

function ColorField({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="block text-xs text-[var(--ink-2)] mb-1">{label}</label>
      <div className="flex items-center gap-2 border border-[var(--line)] p-1 bg-white">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} aria-label={`${label} picker`}
               className="w-10 h-10 border-none cursor-pointer" data-testid={`${testid}-picker`} />
        <input type="text" value={value} onChange={(e) => onChange(e.target.value)} aria-label={`${label} hex code`}
               className="flex-1 min-w-0 font-mono text-sm outline-none px-2" data-testid={testid} />
      </div>
    </div>
  );
}
