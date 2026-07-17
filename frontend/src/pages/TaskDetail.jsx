import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../lib/api";
import PageHero from "../components/PageHero";
import {
  ArrowLeft, Trash, Bell, Clock, Plus, PaperclipHorizontal, LinkSimple,
  ClockCounterClockwise, Users, Buildings, Warning,
} from "@phosphor-icons/react";

const STATUS_COLORS = {
  "Pending": "#5C5C5C", "Selection Required": "#8A6DFF",
  "Reference Required": "#FF8C00", "Vendor Required": "#FF8C00",
  "Quotation Requested": "#F0A93A", "Quotation Received": "#3B82F6",
  "Ordered": "#0EA5E9", "Work Started": "#0891B2", "In Progress": "#002FA7",
  "On Hold": "#F59E0B", "Inspection Pending": "#EAB308",
  "Completed": "#1D633E", "Cancelled": "#B4001C",
};

const TABS = [
  { id: "overview",   label: "Overview",   Icon: Buildings },
  { id: "followups",  label: "Follow-ups", Icon: Bell },
  { id: "timeline",   label: "Timeline",   Icon: ClockCounterClockwise },
  { id: "refs",       label: "References", Icon: LinkSimple },
];

export default function TaskDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [task, setTask] = useState(null);
  const [meta, setMeta] = useState(null);
  const [tab, setTab] = useState("overview");

  const load = async () => {
    const [t, m] = await Promise.all([api.get(`/tasks/${id}`), api.get("/tasks/meta")]);
    setTask(t.data); setMeta(m.data);
  };
  useEffect(() => { load(); }, [id]);

  const save = async (patch) => {
    await api.put(`/tasks/${id}`, patch);
    load();
  };

  const del = async () => {
    if (!window.confirm("Delete this task permanently?")) return;
    await api.delete(`/tasks/${id}`);
    navigate("/tasks");
  };

  if (!task) return <div className="p-8 overline">LOADING…</div>;

  const isVendor = task.task_type === "vendor";
  const today = new Date().toISOString().slice(0, 10);
  const overdue = task.due_date && task.due_date < today && task.status !== "done";

  return (
    <div className="space-y-6" data-testid="task-detail-page">
      <button onClick={() => navigate("/tasks")} className="text-xs font-mono text-[#5C5C5C] flex items-center gap-1 hover:text-[#002FA7]" data-testid="back-btn">
        <ArrowLeft size={12} /> BACK TO TASKS
      </button>

      <PageHero
        eyebrow={`${isVendor ? "AGENCY / VENDOR" : "EMPLOYEE"} TASK · ${task.status_detail || task.status}`}
        title={task.title}
        kicker={[task.project_name, task.area, task.category].filter(Boolean).join(" · ")}
      >
        {overdue && (
          <span className="status-chip" style={{ background: "#FFF2F0", color: "#FF2A00" }}>
            <Warning size={12} weight="fill" /> OVERDUE
          </span>
        )}
        <button onClick={del} className="btn-ghost text-[#FF2A00]" data-testid="delete-task-btn">
          <Trash size={14} /> Delete
        </button>
      </PageHero>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[#E5E5E5]">
        {TABS.map(({ id: tid, label, Icon }) => (
          <button
            key={tid} onClick={() => setTab(tid)}
            data-testid={`tab-${tid}`}
            className={`px-4 py-2.5 text-sm border-b-2 -mb-px flex items-center gap-2 transition ${tab === tid
              ? "border-[#002FA7] text-[#002FA7] font-semibold"
              : "border-transparent text-[#5C5C5C] hover:text-[#0A0A0A]"}`}
          >
            <Icon size={14} /> {label}
            {tid === "followups" && task.follow_ups?.length > 0 && (
              <span className="text-[10px] font-mono px-1.5 bg-[#F0F3FB] text-[#002FA7]">{task.follow_ups.length}</span>
            )}
            {tid === "timeline" && task.timeline?.length > 0 && (
              <span className="text-[10px] font-mono px-1.5 bg-[#FAFAFA]">{task.timeline.length}</span>
            )}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview task={task} meta={meta} onSave={save} />}
      {tab === "followups" && <FollowUps task={task} reload={load} />}
      {tab === "timeline" && <Timeline task={task} />}
      {tab === "refs" && <References task={task} onSave={save} />}
    </div>
  );
}

// ================================================================
function Overview({ task, meta, onSave }) {
  const [t, setT] = useState(task);
  useEffect(() => setT(task), [task]);
  const set = (k, v) => setT((s) => ({ ...s, [k]: v }));
  const setVendor = (k, v) => setT((s) => ({ ...s, vendor_contact: { ...(s.vendor_contact || {}), [k]: v } }));

  const commit = (k, v) => { if ((task[k] || "") !== (v || "")) onSave({ [k]: v }); };
  const commitVendor = (k, v) => {
    const cur = task.vendor_contact?.[k] || "";
    if (cur !== (v || "")) onSave({ vendor_contact: { ...(task.vendor_contact || {}), [k]: v } });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="tab-overview">
      <div className="lg:col-span-2 space-y-4">
        <div className="card-flat space-y-3">
          <div className="overline">Description</div>
          <textarea value={t.description || ""}
            onChange={(e) => set("description", e.target.value)}
            onBlur={(e) => commit("description", e.target.value)}
            className="input-flat w-full min-h-[120px]" placeholder="Add task description…"
            data-testid="desc-input" />
        </div>

        <div className="card-flat space-y-3">
          <div className="overline">Item / Line details</div>
          <div className="grid grid-cols-2 gap-3">
            <LabeledInput label="Item description" value={t.item_description || ""}
              onChange={(v) => set("item_description", v)} onBlur={(v) => commit("item_description", v)} />
            <LabeledInput label="Quantity" type="number" value={t.quantity ?? ""}
              onChange={(v) => set("quantity", v)}
              onBlur={(v) => commit("quantity", v === "" ? null : Number(v))} />
            <LabeledInput label="Remarks" value={t.remarks || ""}
              onChange={(v) => set("remarks", v)} onBlur={(v) => commit("remarks", v)} />
            <LabeledInput label="Due date" type="date" value={t.due_date || ""}
              onChange={(v) => set("due_date", v)} onBlur={(v) => commit("due_date", v)} />
          </div>
        </div>

        {t.task_type === "vendor" && (
          <div className="card-flat space-y-3" data-testid="vendor-block">
            <div className="overline">Vendor / Agency Contact</div>
            <div className="grid grid-cols-2 gap-3">
              <LabeledInput label="Vendor name" value={t.vendor_contact?.vendor_name || ""}
                onChange={(v) => setVendor("vendor_name", v)} onBlur={(v) => commitVendor("vendor_name", v)} />
              <LabeledInput label="Company" value={t.vendor_contact?.company_name || ""}
                onChange={(v) => setVendor("company_name", v)} onBlur={(v) => commitVendor("company_name", v)} />
              <LabeledInput label="Contact person" value={t.vendor_contact?.contact_person || ""}
                onChange={(v) => setVendor("contact_person", v)} onBlur={(v) => commitVendor("contact_person", v)} />
              <LabeledInput label="Phone" value={t.vendor_contact?.phone || ""}
                onChange={(v) => setVendor("phone", v)} onBlur={(v) => commitVendor("phone", v)} />
              <LabeledInput label="Email" value={t.vendor_contact?.email || ""}
                onChange={(v) => setVendor("email", v)} onBlur={(v) => commitVendor("email", v)} />
              <LabeledInput label="WhatsApp" value={t.vendor_contact?.whatsapp || ""}
                onChange={(v) => setVendor("whatsapp", v)} onBlur={(v) => commitVendor("whatsapp", v)} />
            </div>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="card-flat space-y-3">
          <div className="overline">Status & Priority</div>
          <div className="space-y-2">
            <select value={t.status_detail || ""} className="input-flat w-full"
              onChange={(e) => { set("status_detail", e.target.value); onSave({ status_detail: e.target.value }); }}
              data-testid="status-select"
              style={{ color: STATUS_COLORS[t.status_detail] || "#000", fontWeight: 600 }}>
              <option value="">—</option>
              {(meta?.status_detail || []).map((s) => <option key={s}>{s}</option>)}
            </select>
            <select value={t.priority || "medium"} className="input-flat w-full"
              onChange={(e) => { set("priority", e.target.value); onSave({ priority: e.target.value }); }}
              data-testid="priority-select">
              {(meta?.priorities || []).map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
        </div>

        <div className="card-flat space-y-3">
          <div className="overline">Classification</div>
          <select value={t.area || ""} className="input-flat w-full"
            onChange={(e) => { set("area", e.target.value); onSave({ area: e.target.value }); }}>
            <option value="">Area…</option>
            {(meta?.areas || []).map((a) => <option key={a}>{a}</option>)}
          </select>
          <select value={t.category || ""} className="input-flat w-full"
            onChange={(e) => { set("category", e.target.value); onSave({ category: e.target.value }); }}>
            <option value="">Category…</option>
            {(meta?.categories || []).map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>

        {t.task_type !== "vendor" && (
          <div className="card-flat space-y-3">
            <div className="overline flex items-center gap-2"><Users size={12} /> Assignee</div>
            <LabeledInput label="Employee name" value={t.assignee_name || ""}
              onChange={(v) => set("assignee_name", v)} onBlur={(v) => commit("assignee_name", v)} />
          </div>
        )}

        <div className="card-flat space-y-2 text-xs text-[#5C5C5C] font-mono">
          <div>ID · {task.id}</div>
          <div>CREATED · {task.created_at?.slice(0, 16).replace("T", " ")}</div>
          <div>UPDATED · {task.updated_at?.slice(0, 16).replace("T", " ")}</div>
        </div>
      </div>
    </div>
  );
}

function LabeledInput({ label, value, onChange, onBlur, type = "text" }) {
  return (
    <label className="block text-xs">
      <div className="overline mb-1">{label}</div>
      <input type={type} value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        onBlur={(e) => onBlur?.(e.target.value)}
        className="input-flat w-full" />
    </label>
  );
}

// ================================================================
function FollowUps({ task, reload }) {
  const [draft, setDraft] = useState({
    follow_up_date: "", reminder_date: "", reminder_time: "",
    notes: "", next_follow_up_date: "", assigned_employee_name: "",
  });
  const add = async (e) => {
    e.preventDefault();
    if (!draft.notes && !draft.follow_up_date) return;
    await api.post(`/tasks/${task.id}/follow-ups`, draft);
    setDraft({ follow_up_date: "", reminder_date: "", reminder_time: "", notes: "", next_follow_up_date: "", assigned_employee_name: "" });
    reload();
  };

  const del = async (fid) => {
    if (!window.confirm("Delete follow-up?")) return;
    await api.delete(`/tasks/${task.id}/follow-ups/${fid}`);
    reload();
  };

  const markDone = async (fid) => {
    await api.patch(`/tasks/${task.id}/follow-ups/${fid}`, { status: "done" });
    reload();
  };

  return (
    <div className="space-y-4" data-testid="tab-followups">
      <form onSubmit={add} className="card-flat space-y-3" data-testid="followup-form">
        <div className="overline">Add follow-up</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <label className="text-xs">
            <div className="overline mb-1">Follow-up date</div>
            <input type="date" className="input-flat w-full" value={draft.follow_up_date}
              onChange={(e) => setDraft({ ...draft, follow_up_date: e.target.value })} data-testid="fu-date" />
          </label>
          <label className="text-xs">
            <div className="overline mb-1">Reminder date</div>
            <input type="date" className="input-flat w-full" value={draft.reminder_date}
              onChange={(e) => setDraft({ ...draft, reminder_date: e.target.value })} />
          </label>
          <label className="text-xs">
            <div className="overline mb-1">Reminder time</div>
            <input type="time" className="input-flat w-full" value={draft.reminder_time}
              onChange={(e) => setDraft({ ...draft, reminder_time: e.target.value })} />
          </label>
          <label className="text-xs">
            <div className="overline mb-1">Next follow-up</div>
            <input type="date" className="input-flat w-full" value={draft.next_follow_up_date}
              onChange={(e) => setDraft({ ...draft, next_follow_up_date: e.target.value })} />
          </label>
          <label className="text-xs md:col-span-2">
            <div className="overline mb-1">Assigned employee</div>
            <input className="input-flat w-full" value={draft.assigned_employee_name}
              onChange={(e) => setDraft({ ...draft, assigned_employee_name: e.target.value })} />
          </label>
          <label className="text-xs md:col-span-2">
            <div className="overline mb-1">Notes</div>
            <input className="input-flat w-full" value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })} data-testid="fu-notes" />
          </label>
        </div>
        <div className="flex justify-end">
          <button className="btn-primary" data-testid="fu-submit"><Plus size={14} /> Add follow-up</button>
        </div>
      </form>

      <div className="space-y-3">
        {(task.follow_ups || []).length === 0 && (
          <div className="text-center py-12 text-sm text-[#9A9A9A]">No follow-ups yet.</div>
        )}
        {(task.follow_ups || []).slice().reverse().map((fu) => (
          <div key={fu.id} className={`card-flat ${fu.status === "done" ? "opacity-60" : ""}`}
            data-testid={`fu-${fu.id}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-xs">
                <Bell size={12} className="text-[#8A6DFF]" />
                <span className="font-mono">
                  {fu.follow_up_date || fu.reminder_date || "—"}
                  {fu.reminder_time ? ` · ${fu.reminder_time}` : ""}
                </span>
                {fu.status === "done" && <span className="status-chip">DONE</span>}
              </div>
              <div className="flex items-center gap-2">
                {fu.status !== "done" && (
                  <button onClick={() => markDone(fu.id)} className="btn-ghost text-xs" data-testid={`fu-done-${fu.id}`}>
                    Mark done
                  </button>
                )}
                <button onClick={() => del(fu.id)} className="text-[#FF2A00]" data-testid={`fu-del-${fu.id}`}>
                  <Trash size={12} />
                </button>
              </div>
            </div>
            {fu.notes && <p className="text-sm">{fu.notes}</p>}
            <div className="flex items-center gap-4 mt-2 text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
              {fu.assigned_employee_name && <span>ASSIGNED · {fu.assigned_employee_name}</span>}
              {fu.next_follow_up_date && <span>NEXT · {fu.next_follow_up_date}</span>}
              {fu.created_by_name && <span>BY · {fu.created_by_name}</span>}
              {fu.created_at && <span>· {fu.created_at.slice(0, 10)}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ================================================================
function Timeline({ task }) {
  const items = (task.timeline || []).slice().reverse();
  return (
    <div className="space-y-3" data-testid="tab-timeline">
      {items.length === 0 && <div className="text-center py-12 text-sm text-[#9A9A9A]">No history yet.</div>}
      {items.map((ev) => (
        <div key={ev.id} className="flex gap-3 pb-3 border-b border-[#F0F0F0]" data-testid={`tl-${ev.id}`}>
          <div className="w-24 flex-shrink-0 text-[10px] font-mono uppercase tracking-wider text-[#5C5C5C]">
            {ev.at?.slice(0, 16).replace("T", " ")}
          </div>
          <div className="w-2 h-2 mt-1.5 rounded-full bg-[#002FA7] flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-xs font-mono uppercase tracking-wider text-[#002FA7]">{ev.event.replace(/_/g, " ")}</div>
            <div className="text-sm">{ev.details}</div>
            {ev.actor_name && <div className="text-[10px] text-[#9A9A9A] mt-0.5">by {ev.actor_name}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ================================================================
function References({ task, onSave }) {
  const [link, setLink] = useState("");
  const [att, setAtt] = useState({ label: "", url: "", type: "link" });

  const addLink = () => {
    if (!link) return;
    const links = [...(task.reference_links || []), link];
    onSave({ reference_links: links });
    setLink("");
  };
  const delLink = (idx) => {
    const links = (task.reference_links || []).filter((_, i) => i !== idx);
    onSave({ reference_links: links });
  };
  const addAtt = () => {
    if (!att.url) return;
    const items = [...(task.attachments || []), att];
    onSave({ attachments: items });
    setAtt({ label: "", url: "", type: "link" });
  };
  const delAtt = (idx) => {
    const items = (task.attachments || []).filter((_, i) => i !== idx);
    onSave({ attachments: items });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6" data-testid="tab-refs">
      <div className="card-flat space-y-3">
        <div className="overline">Reference links</div>
        <div className="flex gap-2">
          <input className="input-flat flex-1" value={link} onChange={(e) => setLink(e.target.value)}
            placeholder="https://pinterest.com/pin/…" data-testid="ref-input" />
          <button onClick={addLink} className="btn-primary" data-testid="ref-add"><Plus size={14} /></button>
        </div>
        {(task.reference_links || []).map((l, i) => (
          <div key={i} className="flex items-center justify-between text-xs border border-[#E5E5E5] p-2" data-testid={`ref-${i}`}>
            <a href={l} target="_blank" rel="noreferrer" className="truncate flex-1 text-[#002FA7] hover:underline">{l}</a>
            <button onClick={() => delLink(i)} className="text-[#FF2A00] ml-2"><Trash size={12} /></button>
          </div>
        ))}
        {(task.reference_links || []).length === 0 && <div className="text-xs text-[#9A9A9A] text-center py-6">No references yet.</div>}
      </div>

      <div className="card-flat space-y-3">
        <div className="overline">Attachments (URL)</div>
        <div className="grid grid-cols-2 gap-2">
          <input className="input-flat" placeholder="Label" value={att.label}
            onChange={(e) => setAtt({ ...att, label: e.target.value })} />
          <select className="input-flat" value={att.type} onChange={(e) => setAtt({ ...att, type: e.target.value })}>
            <option value="link">Link</option><option value="image">Image</option>
            <option value="pdf">PDF</option><option value="doc">Doc</option>
          </select>
          <input className="input-flat col-span-2" placeholder="URL" value={att.url}
            onChange={(e) => setAtt({ ...att, url: e.target.value })} data-testid="att-url" />
        </div>
        <button onClick={addAtt} className="btn-primary w-full" data-testid="att-add"><Plus size={14} /> Add attachment</button>
        {(task.attachments || []).map((a, i) => (
          <div key={i} className="flex items-center justify-between text-xs border border-[#E5E5E5] p-2" data-testid={`att-${i}`}>
            <div className="flex items-center gap-2 truncate flex-1">
              <PaperclipHorizontal size={12} />
              <a href={a.url} target="_blank" rel="noreferrer" className="truncate text-[#002FA7] hover:underline">
                {a.label || a.url}
              </a>
              <span className="text-[10px] font-mono text-[#9A9A9A]">{a.type}</span>
            </div>
            <button onClick={() => delAtt(i)} className="text-[#FF2A00]"><Trash size={12} /></button>
          </div>
        ))}
        {(task.attachments || []).length === 0 && <div className="text-xs text-[#9A9A9A] text-center py-6">No attachments yet.</div>}
      </div>
    </div>
  );
}
