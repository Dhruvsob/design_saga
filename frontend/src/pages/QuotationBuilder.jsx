import { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api, { API } from "../lib/api";
import {
  ArrowLeft, FloppyDisk, FilePdf, Sparkle, Plus, Trash, ArrowRight,
  CheckCircle, X, Clock,
} from "@phosphor-icons/react";

const TABS = ["Overview", "BOQ Builder", "Rooms", "Materials", "Costing", "Payment Plan", "Timeline", "Terms", "Versions", "Preview"];
const CONSULT_TABS = ["Overview", "Fee Schedule", "Costing", "Payment Plan", "Timeline", "Terms", "Versions", "Preview"];
const TYPE_LABELS = { turnkey: "Turnkey", consultancy: "Consultancy", execution: "Execution Only", hybrid: "Hybrid" };
const fmt = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function QuotationBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState(null);
  const [tpl, setTpl] = useState(null);
  const [tab, setTab] = useState("Overview");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [aiPanel, setAiPanel] = useState({ open: false, focus: "missing_items", loading: false, response: "" });

  const load = useCallback(async () => {
    const [qr, tr] = await Promise.all([
      api.get(`/quotations-adv/${id}`),
      api.get(`/quotations-adv/templates`),
    ]);
    setQ(qr.data);
    setTpl(tr.data);
    setDirty(false);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const update = (patch) => {
    setQ((prev) => ({ ...prev, ...patch }));
    setDirty(true);
  };

  const save = async () => {
    if (!q) return;
    setSaving(true);
    try {
      const payload = {
        type: q.type, project_title: q.project_title, client_id: q.client_id,
        client_name: q.client_name, project_location: q.project_location, area_sqft: Number(q.area_sqft || 0),
        client_requirement: q.client_requirement, design_intent: q.design_intent,
        highlights: q.highlights, design_scope: q.design_scope, execution_scope: q.execution_scope,
        exclusions: q.exclusions, deliverables: q.deliverables, boq: q.boq, materials: q.materials,
        cost: q.cost, payment_plan: q.payment_plan, timeline: q.timeline, terms: q.terms,
      };
      const { data } = await api.put(`/quotations-adv/${id}`, payload);
      setQ(data);
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (status) => {
    await api.post(`/quotations-adv/${id}/status`, { status });
    load();
  };

  const newVersion = async () => {
    const note = window.prompt("Revision note (what changed?)") || "";
    await api.post(`/quotations-adv/${id}/version`, { note });
    load();
  };

  const convert = async () => {
    if (!window.confirm("Convert this quotation into a project? Tasks will be auto-created.")) return;
    try {
      const { data } = await api.post(`/quotations-adv/${id}/convert-to-project`);
      alert(`Project created. ID: ${data.project_id}`);
      navigate(`/projects/${data.project_id}`);
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to convert");
    }
  };

  const askAI = async (focus) => {
    setAiPanel({ open: true, focus, loading: true, response: "" });
    try {
      const { data } = await api.post(`/quotations-adv/${id}/ai-suggest`, { focus });
      setAiPanel({ open: true, focus, loading: false, response: data.response });
    } catch {
      setAiPanel((p) => ({ ...p, loading: false, response: "AI unavailable. Please try again." }));
    }
  };

  if (!q || !tpl) return <div className="overline">LOADING…</div>;

  const isConsult = q.type === "consultancy";
  const visibleTabs = isConsult ? CONSULT_TABS : TABS;
  // If the current tab was hidden by a type switch, snap back to Overview
  const activeTab = visibleTabs.includes(tab) ? tab : "Overview";

  return (
    <div className="space-y-6 pb-32" data-testid="quotation-builder">
      <Link to="/quotations" className="inline-flex items-center gap-1 text-sm text-[#5C5C5C] hover:text-[#0A0A0A]">
        <ArrowLeft size={14} /> All quotations
      </Link>

      {/* Header */}
      <div className="border border-[#E5E5E5] p-6 flex flex-wrap gap-6 items-start justify-between bg-white">
        <div className="flex-1 min-w-[280px]">
          <div className="overline mb-2 flex items-center gap-3">
            {q.number} · {TYPE_LABELS[q.type]} · {q.version_label}
            <span className={`status-chip chip-${q.status === "approved" || q.status === "converted" ? "paid" : q.status === "rejected" ? "overdue" : q.status === "sent" || q.status === "under_review" ? "sent" : "draft"}`}>{q.status}</span>
          </div>
          <input
            value={q.project_title || ""}
            onChange={(e) => update({ project_title: e.target.value })}
            className="font-display font-bold tracking-tight text-3xl w-full bg-transparent outline-none border-b border-transparent focus:border-[#8B7F6A]"
            data-testid="builder-title"
          />
          <div className="mt-3 flex items-center gap-4 text-sm text-[#5C5C5C]">
            <div><span className="overline">CLIENT</span> <span className="ml-1 text-[#0A0A0A]">{q.client_name || "—"}</span></div>
            <div><span className="overline">LOCATION</span> <span className="ml-1 text-[#0A0A0A]">{q.project_location || "—"}</span></div>
            <div><span className="overline">AREA</span> <span className="ml-1 text-[#0A0A0A]">{q.area_sqft || 0} sq.ft</span></div>
          </div>
        </div>
        <div className="text-right">
          <div className="overline">GRAND TOTAL</div>
          <div className="font-display font-bold text-4xl tracking-tight accent-blue">{fmt(q.cost?.grand_total)}</div>
          <div className="overline mt-1">incl GST · {q.total_duration_weeks || 0} weeks</div>
        </div>
      </div>

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={save} disabled={saving || !dirty} className="btn-primary" data-testid="save-quotation-btn">
          <FloppyDisk size={14} /> {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
        <a href={`${API}/quotations-adv/${id}/pdf`} target="_blank" rel="noreferrer" className="btn-ghost" data-testid="pdf-btn">
          <FilePdf size={14} /> Download PDF
        </a>
        <button onClick={newVersion} className="btn-ghost">
          New version
        </button>
        <button onClick={() => setStatus("sent")} className="btn-ghost">Mark sent</button>
        <button onClick={() => setStatus("approved")} className="btn-ghost">Mark approved</button>
        <button onClick={convert} className="btn-ghost">
          <ArrowRight size={14} /> Convert to project
        </button>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => askAI("missing_items")} className="btn-ghost text-xs"><Sparkle size={12} /> AI: missing items</button>
          <button onClick={() => askAI("cost_optimisation")} className="btn-ghost text-xs"><Sparkle size={12} /> AI: optimise cost</button>
          <button onClick={() => askAI("premium_upgrades")} className="btn-ghost text-xs"><Sparkle size={12} /> AI: premium upgrades</button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-[#E5E5E5]">
        {visibleTabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition ${
              activeTab === t ? "border-[#8B7F6A] text-[#8B7F6A]" : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"
            }`}
            data-testid={`tab-${t.replace(/\s/g, "-")}`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "Overview" && <Overview q={q} update={update} tpl={tpl} isConsult={isConsult} />}
        {(activeTab === "BOQ Builder" || activeTab === "Fee Schedule") && <BoqBuilder q={q} update={update} tpl={tpl} isConsult={isConsult} />}
        {activeTab === "Rooms" && !isConsult && <Rooms q={q} />}
        {activeTab === "Materials" && !isConsult && <Materials q={q} update={update} tpl={tpl} />}
        {activeTab === "Costing" && <Costing q={q} update={update} />}
        {activeTab === "Payment Plan" && <PaymentPlan q={q} update={update} tpl={tpl} />}
        {activeTab === "Timeline" && <Timeline q={q} update={update} tpl={tpl} />}
        {activeTab === "Terms" && <Terms q={q} update={update} tpl={tpl} />}
        {activeTab === "Versions" && <Versions q={q} />}
        {activeTab === "Preview" && <Preview qid={id} />}
      </div>

      {/* AI panel drawer */}
      {aiPanel.open && (
        <div className="fixed inset-y-0 right-0 w-[480px] max-w-[100vw] bg-white border-l border-[#E5E5E5] z-50 flex flex-col" style={{ boxShadow: "-20px 0 60px rgba(0,0,0,0.10)" }}>
          <div className="p-4 border-b border-[#E5E5E5] flex items-center justify-between bg-[#8B7F6A] text-white">
            <div className="flex items-center gap-2">
              <Sparkle size={18} weight="fill" />
              <div>
                <div className="font-display font-bold text-sm tracking-tight">SAGA AI · QUOTATION AUDIT</div>
                <div className="text-[10px] font-mono tracking-widest opacity-80">{aiPanel.focus.toUpperCase()}</div>
              </div>
            </div>
            <button onClick={() => setAiPanel((p) => ({ ...p, open: false }))}><X size={18} /></button>
          </div>
          <div className="flex-1 overflow-y-auto p-5">
            {aiPanel.loading ? (
              <div className="overline">ANALYSING…</div>
            ) : (
              <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">{aiPanel.response}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ========= Overview ========= */
function Overview({ q, update, tpl, isConsult }) {
  const setHL = (k, v) => update({ highlights: { ...(q.highlights || {}), [k]: v } });
  const setDel = (k, v) => update({ deliverables: { ...(q.deliverables || {}), [k]: Number(v) || 0 } });

  const swapType = (newType) => {
    if (!window.confirm(`Switch type to ${TYPE_LABELS[newType]}? Default payment plan, timeline, terms and deliverables will reset.`)) return;
    const patch = {
      type: newType,
      payment_plan: tpl.payment_plans[newType].map((p) => ({ ...p })),
      timeline: tpl.timelines[newType].map((p) => ({ ...p })),
      deliverables: { ...tpl.deliverables[newType] },
    };
    if (newType === "consultancy" && tpl.consultancy_terms) {
      patch.terms = tpl.consultancy_terms.map((t) => ({ ...t }));
    } else if (q.type === "consultancy" && tpl.default_terms) {
      patch.terms = tpl.default_terms.map((t) => ({ ...t }));
    }
    update(patch);
  };

  const editList = (key) => {
    const current = (q[key] || []).join("\n");
    const next = window.prompt("One bullet per line:", current);
    if (next === null) return;
    update({ [key]: next.split("\n").map((s) => s.trim()).filter(Boolean) });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="tab-overview">
      <div className="lg:col-span-2 space-y-6">
        <Card title="EXECUTIVE SUMMARY">
          <Field label="Client requirement">
            <textarea rows={3} className="input-flat" value={q.client_requirement || ""} onChange={(e) => update({ client_requirement: e.target.value })} />
          </Field>
          <Field label="Design intent">
            <textarea rows={3} className="input-flat" value={q.design_intent || ""} onChange={(e) => update({ design_intent: e.target.value })} />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Budget range">
              <input className="input-flat" value={q.highlights?.budget_range || ""} onChange={(e) => setHL("budget_range", e.target.value)} />
            </Field>
            <Field label="Timeline">
              <input className="input-flat" value={q.highlights?.timeline || ""} onChange={(e) => setHL("timeline", e.target.value)} />
            </Field>
            <Field label="Quality level">
              <select className="input-flat" value={q.highlights?.quality_level || "Premium"} onChange={(e) => setHL("quality_level", e.target.value)}>
                <option>Premium</option><option>Mid</option><option>Budget</option>
              </select>
            </Field>
          </div>
        </Card>

        <Card title="SCOPE OF WORK">
          {(isConsult
            ? [["design_scope", "Design scope"], ["exclusions", "Exclusions"]]
            : [["design_scope", "Design scope"], ["execution_scope", "Execution scope"], ["exclusions", "Exclusions"]]
          ).map(([k, l]) => (
            <div key={k} className="border-t border-[#F0F0F0] pt-4">
              <div className="flex items-center justify-between mb-2">
                <div className="overline">{l}</div>
                <button onClick={() => editList(k)} className="text-xs underline">edit</button>
              </div>
              <ul className="text-sm list-disc ml-5 space-y-1 text-[#0A0A0A]">
                {(q[k] || []).map((it, i) => <li key={i}>{it}</li>)}
                {(q[k] || []).length === 0 && <li className="list-none text-[#5C5C5C]">—</li>}
              </ul>
            </div>
          ))}
        </Card>

        <Card title="DELIVERABLES">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ["type_2d", "2D drawings"],
              ["type_3d", "3D renders"],
              ["drawings", "Tech drawings"],
              ["site_visits", "Site visits"],
              ["revision_limit", "Revision limit"],
            ].map(([k, l]) => (
              <Field key={k} label={l}>
                <input type="number" className="input-flat" value={q.deliverables?.[k] ?? 0} onChange={(e) => setDel(k, e.target.value)} />
              </Field>
            ))}
          </div>
        </Card>
      </div>

      <div className="space-y-6">
        <Card title="QUOTATION TYPE">
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(TYPE_LABELS).map(([v, l]) => (
              <button
                key={v}
                onClick={() => swapType(v)}
                className={`p-3 border text-left transition ${q.type === v ? "bg-[#8B7F6A] border-[#8B7F6A] text-white" : "bg-white border-[#E5E5E5] hover:border-[#0A0A0A]"}`}
              >
                <div className="overline" style={{ color: q.type === v ? "rgba(255,255,255,0.7)" : undefined }}>{v.toUpperCase()}</div>
                <div className="font-semibold text-sm mt-1">{l}</div>
              </button>
            ))}
          </div>
        </Card>

        <Card title="META">
          <Field label="Client name">
            <input className="input-flat" value={q.client_name || ""} onChange={(e) => update({ client_name: e.target.value })} />
          </Field>
          <Field label="Location">
            <input className="input-flat" value={q.project_location || ""} onChange={(e) => update({ project_location: e.target.value })} />
          </Field>
          <Field label="Area (sq.ft)">
            <input type="number" className="input-flat" value={q.area_sqft || 0} onChange={(e) => update({ area_sqft: Number(e.target.value) || 0 })} />
          </Field>
        </Card>
      </div>
    </div>
  );
}

/* ========= BOQ Builder / Fee Schedule ========= */
function BoqBuilder({ q, update, tpl, isConsult }) {
  const [showCatForm, setShowCatForm] = useState(false);
  const [newCat, setNewCat] = useState("");
  const lib = isConsult ? (tpl.consultancy_fee_templates || {}) : tpl.boq_templates;

  const addTemplateCat = (name) => {
    const items = (lib[name] || []).map((it) => ({
      code: `${name.slice(0, 3).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      description: it.description, unit: it.unit, quantity: it.quantity,
      rate: it.rate, margin_pct: isConsult ? 0 : it.margin_pct, amount: 0,
      room: isConsult ? "Unassigned" : tpl.rooms[0], brand_tier: "Standard", vendor: "",
    }));
    update({ boq: [...(q.boq || []), { category: name, items, category_total: 0 }] });
  };

  const addEmptyCat = () => {
    if (!newCat.trim()) return;
    update({ boq: [...(q.boq || []), { category: newCat.trim(), items: [], category_total: 0 }] });
    setNewCat(""); setShowCatForm(false);
  };

  const updateItem = (ci, ii, key, val) => {
    const boq = JSON.parse(JSON.stringify(q.boq));
    boq[ci].items[ii] = { ...boq[ci].items[ii], [key]: val };
    update({ boq });
  };

  const addItem = (ci) => {
    const boq = JSON.parse(JSON.stringify(q.boq));
    boq[ci].items.push({
      code: `LIN-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      description: "", unit: isConsult ? "lot" : "nos", quantity: 1, rate: 0,
      margin_pct: isConsult ? 0 : 15,
      amount: 0, room: isConsult ? "Unassigned" : tpl.rooms[0], brand_tier: "Standard", vendor: "",
    });
    update({ boq });
  };

  const removeItem = (ci, ii) => {
    const boq = JSON.parse(JSON.stringify(q.boq));
    boq[ci].items.splice(ii, 1);
    update({ boq });
  };

  const removeCat = (ci) => {
    if (!window.confirm("Remove this category?")) return;
    const boq = JSON.parse(JSON.stringify(q.boq));
    boq.splice(ci, 1);
    update({ boq });
  };

  return (
    <div className="space-y-6" data-testid="tab-boq">
      <Card title={isConsult ? "ADD FEE BLOCKS" : "ADD FROM LIBRARY"}>
        <div className="flex flex-wrap gap-2">
          {Object.keys(lib).map((name) => (
            <button key={name} onClick={() => addTemplateCat(name)} className="btn-ghost text-xs" data-testid={`add-tpl-${name}`}>
              <Plus size={12} /> {name}
            </button>
          ))}
          <button onClick={() => setShowCatForm(!showCatForm)} className="btn-ghost text-xs">
            <Plus size={12} /> Custom category
          </button>
        </div>
        {showCatForm && (
          <div className="mt-3 flex gap-2">
            <input className="input-flat" placeholder="Category name" value={newCat} onChange={(e) => setNewCat(e.target.value)} />
            <button onClick={addEmptyCat} className="btn-primary">Add</button>
          </div>
        )}
      </Card>

      {(q.boq || []).map((cat, ci) => (
        <Card key={ci} title={cat.category} actions={
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold">{fmt(cat.category_total)}</span>
            <button onClick={() => removeCat(ci)} className="text-[#FF2A00]"><Trash size={14} /></button>
          </div>
        }>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-[#E5E5E5]">
                  <th className="py-2 overline" style={{ minWidth: 70 }}>Code</th>
                  <th className="py-2 overline" style={{ minWidth: 220 }}>{isConsult ? "Professional service" : "Description"}</th>
                  <th className="py-2 overline">Unit</th>
                  <th className="py-2 overline text-right">Qty</th>
                  <th className="py-2 overline text-right">Rate</th>
                  {!isConsult && <th className="py-2 overline text-right">Mgn%</th>}
                  <th className="py-2 overline text-right">Amount</th>
                  {!isConsult && <th className="py-2 overline">Room</th>}
                  {!isConsult && <th className="py-2 overline">Brand</th>}
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {cat.items.map((it, ii) => {
                  const amt = (Number(it.quantity) || 0) * (Number(it.rate) || 0) * (1 + (Number(it.margin_pct) || 0) / 100);
                  return (
                    <tr key={ii} className="border-b border-[#F0F0F0]">
                      <td><input className="input-flat" style={{ padding: "6px 8px" }} value={it.code || ""} onChange={(e) => updateItem(ci, ii, "code", e.target.value)} /></td>
                      <td><input className="input-flat" style={{ padding: "6px 8px" }} value={it.description || ""} onChange={(e) => updateItem(ci, ii, "description", e.target.value)} /></td>
                      <td><input className="input-flat" style={{ padding: "6px 8px", width: 70 }} value={it.unit || ""} onChange={(e) => updateItem(ci, ii, "unit", e.target.value)} /></td>
                      <td><input type="number" className="input-flat text-right" style={{ padding: "6px 8px", width: 80 }} value={it.quantity} onChange={(e) => updateItem(ci, ii, "quantity", Number(e.target.value) || 0)} /></td>
                      <td><input type="number" className="input-flat text-right" style={{ padding: "6px 8px", width: 100 }} value={it.rate} onChange={(e) => updateItem(ci, ii, "rate", Number(e.target.value) || 0)} /></td>
                      {!isConsult && <td><input type="number" className="input-flat text-right" style={{ padding: "6px 8px", width: 70 }} value={it.margin_pct} onChange={(e) => updateItem(ci, ii, "margin_pct", Number(e.target.value) || 0)} /></td>}
                      <td className="font-mono text-right">{fmt(amt)}</td>
                      {!isConsult && (
                      <td>
                        <select className="input-flat" style={{ padding: "6px 8px" }} value={it.room || ""} onChange={(e) => updateItem(ci, ii, "room", e.target.value)}>
                          {tpl.rooms.map((r) => <option key={r}>{r}</option>)}
                        </select>
                      </td>
                      )}
                      {!isConsult && (
                      <td>
                        <select className="input-flat" style={{ padding: "6px 8px" }} value={it.brand_tier || "Standard"} onChange={(e) => updateItem(ci, ii, "brand_tier", e.target.value)}>
                          {tpl.brand_tiers.map((b) => <option key={b}>{b}</option>)}
                        </select>
                      </td>
                      )}
                      <td><button onClick={() => removeItem(ci, ii)} className="text-[#FF2A00]"><Trash size={14} /></button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <button onClick={() => addItem(ci)} className="btn-ghost text-xs mt-3">
            <Plus size={12} /> Add line item
          </button>
        </Card>
      ))}
      {(!q.boq || q.boq.length === 0) && (
        <Card title={isConsult ? "EMPTY FEE SCHEDULE" : "EMPTY BOQ"}>
          <p className="text-sm text-[#5C5C5C]">
            {isConsult
              ? "Add a fee block from the library above — design fees, consultations, site services and more."
              : "Add a category from the library above to get started."}
          </p>
        </Card>
      )}
    </div>
  );
}

/* ========= Rooms ========= */
function Rooms({ q }) {
  const rooms = q.room_totals || [];
  const total = rooms.reduce((s, r) => s + (r.total || 0), 0);
  // build items per room
  const itemsByRoom = useMemo(() => {
    const m = {};
    (q.boq || []).forEach((cat) => {
      cat.items.forEach((it) => {
        const r = it.room || "Unassigned";
        if (!m[r]) m[r] = [];
        m[r].push({ ...it, category: cat.category });
      });
    });
    return m;
  }, [q.boq]);

  return (
    <div className="space-y-4" data-testid="tab-rooms">
      <Card title="ROOM-WISE COST MAPPING">
        {rooms.length === 0 ? <p className="text-sm text-[#5C5C5C]">No items yet. Add BOQ lines first.</p> : (
          <div className="space-y-2">
            {rooms.map((r) => {
              const pct = total ? (r.total / total) * 100 : 0;
              return (
                <div key={r.room} className="border border-[#E5E5E5] p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-display font-semibold">{r.room}</div>
                    <div className="font-mono font-semibold">{fmt(r.total)} <span className="text-xs text-[#5C5C5C] ml-2">({pct.toFixed(0)}%)</span></div>
                  </div>
                  <div className="h-1 bg-[#F0F0F0] mb-3">
                    <div className="h-1 bg-[#8B7F6A]" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="text-xs text-[#5C5C5C] space-y-1">
                    {(itemsByRoom[r.room] || []).slice(0, 8).map((it, i) => (
                      <div key={i} className="flex justify-between">
                        <span>{it.category} · {it.description}</span>
                        <span className="font-mono">{fmt(it.amount)}</span>
                      </div>
                    ))}
                    {(itemsByRoom[r.room] || []).length > 8 && <div className="italic">+ {itemsByRoom[r.room].length - 8} more…</div>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ========= Materials ========= */
function Materials({ q, update, tpl }) {
  const setRow = (i, key, val) => {
    const ms = JSON.parse(JSON.stringify(q.materials || []));
    ms[i] = { ...ms[i], [key]: val };
    update({ materials: ms });
  };
  const addRow = () => {
    update({ materials: [...(q.materials || []), { category: "", brand_premium: "", brand_standard: "", brand_budget: "", selected_tier: "Standard", notes: "" }] });
  };
  const removeRow = (i) => {
    const ms = JSON.parse(JSON.stringify(q.materials || []));
    ms.splice(i, 1); update({ materials: ms });
  };

  return (
    <Card title="MATERIAL SPECIFICATION SYSTEM" actions={<button onClick={addRow} className="btn-ghost text-xs"><Plus size={12} /> Add row</button>} testid="tab-materials">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[#E5E5E5]">
              <th className="py-2 overline">Category</th>
              <th className="py-2 overline">Premium</th>
              <th className="py-2 overline">Standard</th>
              <th className="py-2 overline">Budget</th>
              <th className="py-2 overline">Selected</th>
              <th className="py-2 overline">Notes</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(q.materials || []).map((m, i) => (
              <tr key={i} className="border-b border-[#F0F0F0]">
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={m.category || ""} onChange={(e) => setRow(i, "category", e.target.value)} /></td>
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={m.brand_premium || ""} onChange={(e) => setRow(i, "brand_premium", e.target.value)} /></td>
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={m.brand_standard || ""} onChange={(e) => setRow(i, "brand_standard", e.target.value)} /></td>
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={m.brand_budget || ""} onChange={(e) => setRow(i, "brand_budget", e.target.value)} /></td>
                <td>
                  <select className="input-flat" style={{ padding: "6px 8px" }} value={m.selected_tier || "Standard"} onChange={(e) => setRow(i, "selected_tier", e.target.value)}>
                    {tpl.brand_tiers.map((b) => <option key={b}>{b}</option>)}
                  </select>
                </td>
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={m.notes || ""} onChange={(e) => setRow(i, "notes", e.target.value)} /></td>
                <td><button onClick={() => removeRow(i)} className="text-[#FF2A00]"><Trash size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ========= Costing ========= */
function Costing({ q, update }) {
  const c = q.cost || {};
  const setC = (k, v) => update({ cost: { ...c, [k]: Number(v) || 0 } });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="tab-costing">
      <Card title="ADJUST COMMERCIALS">
        <Field label="Discount %"><input type="number" className="input-flat" value={c.discount_pct || 0} onChange={(e) => setC("discount_pct", e.target.value)} /></Field>
        <Field label="Contingency %"><input type="number" className="input-flat" value={c.contingency_pct || 0} onChange={(e) => setC("contingency_pct", e.target.value)} /></Field>
        <Field label="GST %"><input type="number" className="input-flat" value={c.tax_pct || 18} onChange={(e) => setC("tax_pct", e.target.value)} /></Field>
        <p className="text-xs text-[#5C5C5C] mt-2">Save to recompute totals on the server.</p>
      </Card>

      <Card title="SUMMARY">
        <Row label="Subtotal (BOQ)" val={c.subtotal} />
        <Row label={`Discount (${c.discount_pct || 0}%)`} val={-(c.discount_amt || 0)} />
        <Row label={`Contingency (${c.contingency_pct || 0}%)`} val={c.contingency_amt} />
        <Row label={`GST (${c.tax_pct || 18}%)`} val={c.tax_amt} />
        <div className="border-t border-[#0A0A0A] mt-3 pt-3">
          <div className="flex items-center justify-between">
            <div className="font-display font-bold tracking-tight text-xl">GRAND TOTAL</div>
            <div className="font-display font-bold tracking-tight text-2xl accent-blue">{fmt(c.grand_total)}</div>
          </div>
        </div>

        <div className="mt-6 border-t border-[#F0F0F0] pt-4">
          <div className="overline mb-2">CATEGORY BREAKDOWN</div>
          {(q.category_totals || []).map((c) => (
            <div key={c.category} className="flex justify-between text-sm py-1">
              <span>{c.category}</span><span className="font-mono">{fmt(c.total)}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ========= Payment Plan ========= */
function PaymentPlan({ q, update, tpl }) {
  const setRow = (i, key, val) => {
    const arr = JSON.parse(JSON.stringify(q.payment_plan || []));
    arr[i] = { ...arr[i], [key]: key === "label" || key === "type" || key === "notes" ? val : Number(val) || 0 };
    update({ payment_plan: arr });
  };
  const addRow = () => update({ payment_plan: [...(q.payment_plan || []), { label: "Milestone", type: "milestone", percentage: 10, due_after_days: 30, amount: 0, notes: "" }] });
  const removeRow = (i) => {
    const arr = JSON.parse(JSON.stringify(q.payment_plan || [])); arr.splice(i, 1); update({ payment_plan: arr });
  };
  const loadPreset = () => {
    if (!window.confirm("Load default plan for this type? Current plan will be replaced.")) return;
    update({ payment_plan: tpl.payment_plans[q.type].map((p) => ({ ...p })) });
  };

  const totalPct = (q.payment_plan || []).reduce((s, p) => s + (Number(p.percentage) || 0), 0);

  return (
    <Card title="PAYMENT STRUCTURE BUILDER" actions={
      <div className="flex items-center gap-2">
        <button onClick={loadPreset} className="btn-ghost text-xs">Load preset</button>
        <button onClick={addRow} className="btn-ghost text-xs"><Plus size={12} /> Add</button>
      </div>
    } testid="tab-payment">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[#E5E5E5]">
              <th className="py-2 overline" style={{ minWidth: 200 }}>Milestone</th>
              <th className="py-2 overline">Type</th>
              <th className="py-2 overline text-right">%</th>
              <th className="py-2 overline text-right">Days</th>
              <th className="py-2 overline text-right">Amount</th>
              <th className="py-2 overline">Notes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(q.payment_plan || []).map((p, i) => (
              <tr key={i} className="border-b border-[#F0F0F0]">
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={p.label || ""} onChange={(e) => setRow(i, "label", e.target.value)} /></td>
                <td>
                  <select className="input-flat" style={{ padding: "6px 8px" }} value={p.type || "milestone"} onChange={(e) => setRow(i, "type", e.target.value)}>
                    <option value="milestone">milestone</option>
                    <option value="time">time</option>
                    <option value="custom">custom</option>
                  </select>
                </td>
                <td><input type="number" className="input-flat text-right" style={{ padding: "6px 8px", width: 80 }} value={p.percentage} onChange={(e) => setRow(i, "percentage", e.target.value)} /></td>
                <td><input type="number" className="input-flat text-right" style={{ padding: "6px 8px", width: 80 }} value={p.due_after_days || 0} onChange={(e) => setRow(i, "due_after_days", e.target.value)} /></td>
                <td className="font-mono text-right">{fmt(p.amount)}</td>
                <td><input className="input-flat" style={{ padding: "6px 8px" }} value={p.notes || ""} onChange={(e) => setRow(i, "notes", e.target.value)} /></td>
                <td><button onClick={() => removeRow(i)} className="text-[#FF2A00]"><Trash size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={`mt-4 text-sm font-mono ${Math.abs(totalPct - 100) < 0.5 ? "text-[#1D633E]" : "text-[#FF2A00]"}`}>
        Total: {totalPct}% {Math.abs(totalPct - 100) < 0.5 ? "✓" : "(should be 100%)"}
      </div>
    </Card>
  );
}

/* ========= Timeline ========= */
function Timeline({ q, update, tpl }) {
  const setRow = (i, key, val) => {
    const arr = JSON.parse(JSON.stringify(q.timeline || []));
    arr[i] = { ...arr[i], [key]: key === "phase" ? val : Number(val) || 0 };
    update({ timeline: arr });
  };
  const addRow = () => update({ timeline: [...(q.timeline || []), { phase: "Phase", duration_weeks: 2, start_offset_weeks: 0 }] });
  const removeRow = (i) => {
    const arr = JSON.parse(JSON.stringify(q.timeline || [])); arr.splice(i, 1); update({ timeline: arr });
  };
  const loadPreset = () => {
    if (!window.confirm("Load default timeline for this type?")) return;
    update({ timeline: tpl.timelines[q.type].map((p) => ({ ...p })) });
  };

  const total = (q.timeline || []).reduce((m, p) => Math.max(m, (p.start_offset_weeks || 0) + (p.duration_weeks || 0)), 0);

  return (
    <Card title="PROJECT TIMELINE" actions={
      <div className="flex items-center gap-2">
        <span className="overline">{total} WEEKS TOTAL</span>
        <button onClick={loadPreset} className="btn-ghost text-xs">Load preset</button>
        <button onClick={addRow} className="btn-ghost text-xs"><Plus size={12} /> Add</button>
      </div>
    } testid="tab-timeline">
      <div className="space-y-3">
        {(q.timeline || []).map((p, i) => (
          <div key={i} className="grid grid-cols-12 gap-3 items-center">
            <input className="input-flat col-span-5" value={p.phase || ""} onChange={(e) => setRow(i, "phase", e.target.value)} placeholder="Phase name" />
            <div className="col-span-2"><input type="number" className="input-flat" value={p.start_offset_weeks || 0} onChange={(e) => setRow(i, "start_offset_weeks", e.target.value)} placeholder="Start (wk)" /></div>
            <div className="col-span-2"><input type="number" className="input-flat" value={p.duration_weeks || 0} onChange={(e) => setRow(i, "duration_weeks", e.target.value)} placeholder="Duration" /></div>
            <div className="col-span-2 h-6 bg-[#F0F0F0] relative">
              <div className="absolute top-0 h-6 bg-[#8B7F6A]" style={{ left: `${(p.start_offset_weeks / Math.max(total, 1)) * 100}%`, width: `${(p.duration_weeks / Math.max(total, 1)) * 100}%` }} />
            </div>
            <button onClick={() => removeRow(i)} className="text-[#FF2A00]"><Trash size={14} /></button>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ========= Terms ========= */
function Terms({ q, update, tpl }) {
  const setRow = (i, key, val) => {
    const arr = JSON.parse(JSON.stringify(q.terms || []));
    arr[i] = { ...arr[i], [key]: val };
    update({ terms: arr });
  };
  const addRow = () => update({ terms: [...(q.terms || []), { section: "New section", content: "" }] });
  const removeRow = (i) => {
    const arr = JSON.parse(JSON.stringify(q.terms || [])); arr.splice(i, 1); update({ terms: arr });
  };
  const loadPreset = () => {
    if (!window.confirm("Reset to default terms?")) return;
    update({ terms: tpl.default_terms.map((t) => ({ ...t })) });
  };

  return (
    <Card title="TERMS & CONDITIONS" actions={
      <div className="flex items-center gap-2">
        <button onClick={loadPreset} className="btn-ghost text-xs">Reset to default</button>
        <button onClick={addRow} className="btn-ghost text-xs"><Plus size={12} /> Add</button>
      </div>
    } testid="tab-terms">
      <div className="space-y-4">
        {(q.terms || []).map((t, i) => (
          <div key={i} className="border border-[#E5E5E5] p-4">
            <div className="flex items-center justify-between mb-2">
              <input className="font-display font-bold text-lg bg-transparent outline-none border-b border-transparent focus:border-[#8B7F6A]" value={t.section || ""} onChange={(e) => setRow(i, "section", e.target.value)} />
              <button onClick={() => removeRow(i)} className="text-[#FF2A00]"><Trash size={14} /></button>
            </div>
            <textarea rows={3} className="input-flat" value={t.content || ""} onChange={(e) => setRow(i, "content", e.target.value)} />
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ========= Versions ========= */
function Versions({ q }) {
  return (
    <Card title="VERSION HISTORY" testid="tab-versions">
      <div className="overline mb-2">CURRENT</div>
      <div className="border border-[#0A0A0A] p-4 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display font-bold text-lg">{q.version_label}</div>
            <div className="text-xs text-[#5C5C5C]">Live working version</div>
          </div>
          <div className="font-mono font-semibold">{fmt(q.cost?.grand_total)}</div>
        </div>
      </div>
      <div className="overline mb-2">PREVIOUS SNAPSHOTS</div>
      {(q.versions_log || []).length === 0 ? (
        <p className="text-sm text-[#5C5C5C]">No prior versions yet. Use "New version" to snapshot the current quotation.</p>
      ) : (
        <div className="space-y-2">
          {[...(q.versions_log || [])].reverse().map((v, i) => {
            const diff = (q.cost?.grand_total || 0) - (v.grand_total || 0);
            return (
              <div key={i} className="border border-[#E5E5E5] p-4">
                <div className="flex items-center justify-between mb-1">
                  <div className="font-display font-bold">{v.version_label}</div>
                  <div className="font-mono">{fmt(v.grand_total)}</div>
                </div>
                <div className="text-xs text-[#5C5C5C] flex items-center gap-2">
                  <Clock size={12} />
                  {(v.snapshot_at || "").slice(0, 16).replace("T", " ")} · by {v.by || "—"}
                </div>
                {v.note && <p className="text-sm mt-2">{v.note}</p>}
                <div className={`text-xs mt-1 font-mono ${diff > 0 ? "text-[#1D633E]" : diff < 0 ? "text-[#FF2A00]" : "text-[#5C5C5C]"}`}>
                  Δ vs current: {diff >= 0 ? "+" : ""}{fmt(diff)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

/* ========= Preview ========= */
function Preview({ qid }) {
  return (
    <div className="border border-[#E5E5E5]" style={{ height: "85vh" }} data-testid="tab-preview">
      <iframe title="Quotation Preview" src={`${API}/quotations-adv/${qid}/pdf`} className="w-full h-full" />
    </div>
  );
}

/* ========= Reusable subcomponents ========= */
function Card({ title, children, actions, testid }) {
  return (
    <div className="card-flat" data-testid={testid}>
      <div className="flex items-center justify-between mb-4">
        <div className="overline">{title}</div>
        {actions}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="overline mb-1">{label}</div>
      {children}
    </label>
  );
}

function Row({ label, val }) {
  return (
    <div className="flex items-center justify-between text-sm py-1">
      <span className="text-[#5C5C5C]">{label}</span>
      <span className="font-mono">{fmt(val)}</span>
    </div>
  );
}
