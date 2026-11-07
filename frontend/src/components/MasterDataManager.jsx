import { useEffect, useState } from "react";
import api from "../lib/api";
import { invalidateMasterData } from "../hooks/useMasterData";
import {
  Plus, PencilSimple, Trash, Eye, EyeSlash, CaretUp, CaretDown, Check, X, Warning,
} from "@phosphor-icons/react";
import { confirmAction } from "../lib/confirm";
import RowActions from "./RowActions";

function fmtErr(d, fb = "Failed") {
  if (!d) return fb;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || String(e)).join(" · ");
  return d?.msg || String(d);
}

export default function MasterDataManager() {
  const [kinds, setKinds] = useState({});
  const [systemKinds, setSystemKinds] = useState([]);
  const [data, setData] = useState({});
  const [selected, setSelected] = useState("project_type");
  const [newLabel, setNewLabel] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editLabel, setEditLabel] = useState("");
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const { data: res } = await api.get("/master-data", { params: { include_inactive: true } });
    setKinds(res.kinds || {});
    setSystemKinds(res.system_kinds || []);
    setData(res.data || {});
  };
  useEffect(() => { load(); }, []);

  const rows = (data[selected] || []).slice().sort((a, b) => a.sort_order - b.sort_order);
  const isSystem = systemKinds.includes(selected);

  const flash = (msg) => { setNotice(msg); setTimeout(() => setNotice(""), 3000); };
  const fail = (e, fb) => { setErr(fmtErr(e?.response?.data?.detail, fb)); setTimeout(() => setErr(""), 4000); };

  const add = async (e) => {
    e.preventDefault();
    if (!newLabel.trim()) return;
    setBusy(true);
    try {
      await api.post(`/master-data/${selected}`, { label: newLabel.trim() });
      setNewLabel("");
      invalidateMasterData();
      await load();
      flash("Value added");
    } catch (ex) { fail(ex, "Add failed"); }
    finally { setBusy(false); }
  };

  const saveEdit = async (id) => {
    if (!editLabel.trim()) return;
    setBusy(true);
    try {
      await api.patch(`/master-data/items/${id}`, { label: editLabel.trim() });
      setEditingId(null);
      invalidateMasterData();
      await load();
      flash("Renamed");
    } catch (ex) { fail(ex, "Rename failed"); }
    finally { setBusy(false); }
  };

  const toggle = async (item) => {
    setBusy(true);
    try {
      await api.patch(`/master-data/items/${item.id}`, { is_active: !item.is_active });
      invalidateMasterData();
      await load();
    } catch (ex) { fail(ex, "Update failed"); }
    finally { setBusy(false); }
  };

  const remove = async (item) => {
    if (!await confirmAction(`Delete “${item.label}”? If it's referenced by records it will be deactivated instead.`)) return;
    setBusy(true);
    try {
      const { data: res } = await api.delete(`/master-data/items/${item.id}`);
      invalidateMasterData();
      await load();
      flash(res.deactivated ? "Referenced — deactivated instead of deleted" : "Deleted");
    } catch (ex) { fail(ex, "Delete failed"); }
    finally { setBusy(false); }
  };

  const move = async (item, dir) => {
    const idx = rows.findIndex((r) => r.id === item.id);
    const swap = rows[idx + dir];
    if (!swap) return;
    const ordered = rows.slice();
    [ordered[idx], ordered[idx + dir]] = [ordered[idx + dir], ordered[idx]];
    setBusy(true);
    try {
      await api.post(`/master-data/${selected}/reorder`, { ordered_ids: ordered.map((r) => r.id) });
      invalidateMasterData();
      await load();
    } catch (ex) { fail(ex, "Reorder failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6" data-testid="master-data-manager">
      {/* kind list */}
      <div className="border border-[var(--line)]">
        <div className="overline p-3 border-b border-[var(--line)] bg-[var(--surface-2)]">CONFIGURATION KINDS</div>
        {Object.entries(kinds).map(([k, label]) => (
          <button key={k} onClick={() => { setSelected(k); setEditingId(null); }}
            className={`w-full text-left px-3 py-2.5 text-sm border-b border-[var(--line-soft)] transition flex items-center justify-between ${
              selected === k ? "bg-[var(--hover)] text-[#5F5A4B] font-semibold" : "hover:bg-[var(--surface-2)]"
            }`}
            data-testid={`md-kind-${k}`}
          >
            <span>{label}</span>
            <span className="font-mono text-[10px] text-[var(--ink-3)]">{(data[k] || []).length}</span>
          </button>
        ))}
      </div>

      {/* items */}
      <div className="lg:col-span-3 space-y-4">
        {err && (
          <div className="border border-[var(--danger)] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)] flex items-center gap-2">
            <Warning size={13} /> {err}
          </div>
        )}
        {notice && (
          <div className="border border-[var(--success)] bg-[var(--success-soft)] px-3 py-2 text-sm text-[var(--success)] flex items-center gap-2">
            <Check size={13} /> {notice}
          </div>
        )}
        {isSystem && (
          <div className="border border-[var(--line)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--ink-2)]">
            System pipeline — order defines the workflow. Values can be renamed, reordered and deactivated but not deleted.
          </div>
        )}

        <form onSubmit={add} className="flex gap-2">
          <input className="input-flat flex-1" placeholder={`Add new ${kinds[selected] || "value"}…`}
            value={newLabel} onChange={(e) => setNewLabel(e.target.value)} data-testid="md-add-input" />
          <button className="btn-primary" disabled={busy || !newLabel.trim()} data-testid="md-add-btn">
            <Plus size={14} /> Add
          </button>
        </form>

        <div className="border border-[var(--line)]">
          <table className="w-full">
            <thead className="bg-[var(--surface-2)] border-b border-[var(--line)]">
              <tr className="text-left">
                <th className="px-4 py-2.5 overline w-10">#</th>
                <th className="px-4 py-2.5 overline">Value</th>
                <th className="px-4 py-2.5 overline w-24">Status</th>
                <th className="px-4 py-2.5 overline w-44 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, i) => (
                <tr key={item.id} className={`border-b border-[var(--line-soft)] ${!item.is_active ? "opacity-50" : ""}`}
                    data-testid={`md-row-${item.id}`}>
                  <td className="px-4 py-2 font-mono text-[10px] text-[var(--ink-3)]">{String(i + 1).padStart(2, "0")}</td>
                  <td className="px-4 py-2 text-sm">
                    {editingId === item.id ? (
                      <div className="flex items-center gap-2">
                        <input className="input-flat py-1 text-sm" value={editLabel}
                          onChange={(e) => setEditLabel(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && saveEdit(item.id)}
                          autoFocus data-testid="md-edit-input" />
                        <button onClick={() => saveEdit(item.id)} className="btn-ghost p-1" data-testid="md-edit-save"><Check size={13} /></button>
                        <button onClick={() => setEditingId(null)} className="btn-ghost p-1"><X size={13} /></button>
                      </div>
                    ) : (
                      <span className="font-semibold">{item.label}</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 ${
                      item.is_active ? "bg-[var(--success-soft)] text-[var(--success)]" : "bg-[var(--hover)] text-[var(--ink-3)]"
                    }`}>{item.is_active ? "Active" : "Inactive"}</span>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => move(item, -1)} disabled={i === 0 || busy} title="Move up"
                        className="btn-ghost p-1 disabled:opacity-30"><CaretUp size={12} /></button>
                      <button onClick={() => move(item, 1)} disabled={i === rows.length - 1 || busy} title="Move down"
                        className="btn-ghost p-1 disabled:opacity-30"><CaretDown size={12} /></button>
                      <RowActions label={item.label} testid={`md-actions-${item.id}`} actions={[
                        { label: "Rename", icon: PencilSimple, onSelect: () => { setEditingId(item.id); setEditLabel(item.label); }, testid: `md-rename-${item.id}` },
                        { label: item.is_active ? "Hide from lists" : "Show in lists", icon: item.is_active ? EyeSlash : Eye,
                          onSelect: () => toggle(item), testid: `md-toggle-${item.id}` },
                        { divider: true },
                        { label: "Delete", icon: Trash, danger: true, hidden: item.is_system, onSelect: () => remove(item), testid: `md-delete-${item.id}` },
                      ]} />
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan="4" className="p-6 text-center text-sm text-[var(--ink-2)]">No values yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
