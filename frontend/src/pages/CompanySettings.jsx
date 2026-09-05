import { useEffect, useRef, useState } from "react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import MasterDataManager from "../components/MasterDataManager";
import {
  Palette, Buildings, Upload, Check, Warning, PaintBrush, ImageSquare, X,
  ListChecks,
} from "@phosphor-icons/react";

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
  const [err, setErr] = useState("");
  const fileRef = useRef(null);

  useEffect(() => { setOrg(currentOrg); }, [currentOrg]);

  const setBranding = (patch) =>
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
        await api.post("/org/current/logo", { logo_data_url: dataUrl });
        await refreshOrg();
        setBranding({ logo_url: dataUrl });
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

  return (
    <div className="space-y-8" data-testid="company-settings-page">
      <PageHero
        eyebrow="ADMIN / COMPANY"
        title="Your identity, everywhere."
        kicker={org?.business_mode
          ? `Business mode: ${(org.business_mode || "hybrid").toUpperCase()} · Logo, colours and company info flow into the sidebar, login screen, PDFs and every export.`
          : "Logo, colours and company info flow into the sidebar, login screen, PDFs and every export."}
      >
        {saved && (
          <span className="text-xs text-[#1D633E] font-mono flex items-center gap-1" data-testid="saved-indicator">
            <Check size={13} /> SAVED
          </span>
        )}
        <button disabled={saving} onClick={save} className="btn-primary" data-testid="save-branding-btn">
          {saving ? "Saving…" : "Save changes"}
        </button>
      </PageHero>

      {err && (
        <div className="border border-[#B22B22] bg-[#FCEEEC] p-4 text-sm text-[#B22B22] flex items-center gap-2">
          <Warning size={14} /> {err}
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[#E5E5E5]">
        {[
          { key: "branding", label: "Brand & Colours", Icon: Palette },
          { key: "profile",  label: "Company Profile", Icon: Buildings },
          { key: "masterdata", label: "Master Data", Icon: ListChecks },
        ].map(({ key, label, Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-3 text-sm font-semibold border-b-2 transition ${
              tab === key ? "border-[#8B7F6A] text-[#8B7F6A]" : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"
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
                {branding.logo_url ? (
                  <img src={branding.logo_url} alt="Logo" className="w-20 h-20 object-contain ring-1 ring-[#E5E5E5] bg-white p-2" />
                ) : (
                  <div className="w-20 h-20 flex items-center justify-center text-white font-display font-bold text-lg ring-1 ring-[#E5E5E5]"
                       style={{ backgroundColor: branding.primary_color || "#8B7F6A" }}>
                    {(org.name || "DS").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div>
                  <button onClick={() => fileRef.current?.click()} className="btn-primary" data-testid="upload-logo-btn">
                    <Upload size={12} /> Upload logo
                  </button>
                  <div className="text-xs text-[#5C5C5C] mt-2">
                    PNG, JPG or SVG · Max 2MB · Square works best.
                  </div>
                  {branding.logo_url && (
                    <button onClick={() => setBranding({ logo_url: null })}
                            className="btn-ghost text-xs mt-1" data-testid="remove-logo-btn">
                      <X size={10} /> Remove logo
                    </button>
                  )}
                </div>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onLogoPick} />
              </div>
            </div>

            <div className="card-flat">
              <div className="overline mb-4"><PaintBrush size={11} className="inline mr-1"/> COLOURS</div>
              <div className="grid grid-cols-2 gap-4">
                <ColorField label="Primary" value={branding.primary_color || "#8B7F6A"}
                            onChange={(v) => setBranding({ primary_color: v })} testid="color-primary" />
                <ColorField label="Accent" value={branding.accent_color || "#0A0A0A"}
                            onChange={(v) => setBranding({ accent_color: v })} testid="color-accent" />
              </div>
              <div className="mt-4">
                <label className="block text-xs text-[#5C5C5C] mb-1">Tagline (shown in sidebar)</label>
                <input className="input-flat w-full" placeholder="Studio OS · v0.2"
                       value={branding.tagline || ""} onChange={(e) => setBranding({ tagline: e.target.value })}
                       data-testid="tagline-input" />
              </div>
              <div className="mt-4">
                <label className="block text-xs text-[#5C5C5C] mb-1">PDF Footer note (appears on invoices, quotes, slips)</label>
                <input className="input-flat w-full" placeholder="e.g. Thank you for your business — Design Saga"
                       value={branding.pdf_footer || ""} onChange={(e) => setBranding({ pdf_footer: e.target.value })}
                       data-testid="pdf-footer-input" />
              </div>
            </div>
          </div>

          {/* Right column: Live preview */}
          <div className="space-y-4">
            <div className="card-flat sticky top-24">
              <div className="overline mb-3">LIVE PREVIEW</div>
              {/* Sidebar preview */}
              <div className="border border-[#E5E5E5] p-4 flex items-center gap-3 mb-4">
                {branding.logo_url ? (
                  <img src={branding.logo_url} alt="" className="w-9 h-9 object-contain ring-1 ring-[#E5E5E5]" />
                ) : (
                  <div className="w-9 h-9 flex items-center justify-center text-white font-display font-bold text-sm"
                       style={{ backgroundColor: branding.primary_color || "#8B7F6A" }}>
                    {(org.name || "DS").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div>
                  <div className="font-display font-bold tracking-tight text-sm">
                    {(org.display_name || org.name || "").toUpperCase()}
                  </div>
                  <div className="text-[10px] text-[#5C5C5C] font-mono uppercase">
                    {branding.tagline || "STUDIO OS"}
                  </div>
                </div>
              </div>
              {/* Button preview */}
              <div className="mb-4">
                <div className="overline mb-2 text-[9px]">BUTTON</div>
                <button className="text-white text-xs font-semibold px-4 py-2 w-full"
                        style={{ backgroundColor: branding.primary_color || "#8B7F6A" }}>
                  Continue
                </button>
              </div>
              {/* Invoice header preview */}
              <div>
                <div className="overline mb-2 text-[9px]">INVOICE HEADER</div>
                <div className="border border-[#E5E5E5] p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-display font-bold" style={{ color: branding.primary_color || "#8B7F6A" }}>
                        {org.display_name || org.name}
                      </div>
                      <div className="text-[10px] text-[#5C5C5C] font-mono">
                        GSTIN: {org.gstin || "—"}
                      </div>
                    </div>
                    {branding.logo_url && (
                      <img src={branding.logo_url} alt="" className="w-10 h-10 object-contain" />
                    )}
                  </div>
                  <div className="mt-2 h-[3px]" style={{ background: branding.primary_color || "#8B7F6A" }} />
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
            <p className="text-xs text-[#5C5C5C] mb-3">
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
        </div>
      )}

      {tab === "masterdata" && (
        <div className="space-y-4">
          <p className="text-sm text-[#5C5C5C] max-w-2xl">
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
      <label className="block text-xs text-[#5C5C5C] mb-1">{label}</label>
      <input className="input-flat w-full" value={value} readOnly={readOnly}
             onChange={onChange ? (e) => onChange(e.target.value) : undefined}
             data-testid={testid} />
      {hint && <div className="text-[10px] text-[#9A9A9A] mt-1">{hint}</div>}
    </div>
  );
}

function ColorField({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="block text-xs text-[#5C5C5C] mb-1">{label}</label>
      <div className="flex items-center gap-2 border border-[#E5E5E5] p-1 bg-white">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)}
               className="w-10 h-10 border-none cursor-pointer" data-testid={`${testid}-picker`} />
        <input type="text" value={value} onChange={(e) => onChange(e.target.value)}
               className="flex-1 font-mono text-sm outline-none px-2" data-testid={testid} />
      </div>
    </div>
  );
}
