import { useCallback, useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { Calendar, Plus, Trash, ArrowsClockwise } from "@phosphor-icons/react";

const KINDS = [
  { id: "national", label: "National", color: "#B22B22" },
  { id: "festival", label: "Festival", color: "#B87F00" },
  { id: "optional", label: "Optional", color: "#6B7280" },
  { id: "company",  label: "Company",  color: "#8B7F6A" },
  { id: "regional", label: "Regional", color: "#1D633E" },
];

const kindMeta = (id) => KINDS.find((k) => k.id === id) || KINDS[3];

export default function Holidays() {
  const [year, setYear] = useState(new Date().getFullYear());
  const [rows, setRows] = useState([]);
  const [offs, setOffs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    date: "", name: "", kind: "company", recurring: false, description: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(
        `/holidays?year=${year}&include_weekly_off=true`,
      );
      setRows(data.holidays || []);
      setOffs(data.weekly_off_dates || []);
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const grouped = useMemo(() => {
    const g = {};
    rows.forEach((r) => {
      const m = r.date.slice(0, 7);
      (g[m] = g[m] || []).push(r);
    });
    return g;
  }, [rows]);

  const create = async () => {
    if (!form.date || !form.name.trim()) {
      toast.error("Date and name are required");
      return;
    }
    try {
      await api.post("/holidays", form);
      toast.success("Holiday added");
      setForm({ date: "", name: "", kind: "company", recurring: false, description: "" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add");
    }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this holiday?")) return;
    await api.delete(`/holidays/${id}`);
    toast.success("Deleted");
    load();
  };

  return (
    <div className="space-y-6" data-testid="holidays-page">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Calendar size={22} weight="fill" /> Holiday Calendar
          </h1>
          <div className="text-sm text-[#5C5C5C]">
            Company holidays, weekly offs, and festival days. Applied
            automatically to attendance and payroll.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="overline">YEAR</label>
          <input
            type="number" value={year}
            data-testid="holiday-year-input"
            onChange={(e) => setYear(Number(e.target.value) || new Date().getFullYear())}
            className="border border-[#E5E5E5] w-24 text-sm px-2 py-1"
          />
          <button className="btn-ghost text-xs" onClick={load} data-testid="holiday-refresh">
            <ArrowsClockwise size={14} /> Refresh
          </button>
        </div>
      </header>

      <div className="card-flat" data-testid="holiday-add">
        <div className="overline mb-2">ADD HOLIDAY</div>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
          <input
            type="date" value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
            className="input-flat md:col-span-1"
            data-testid="holiday-date-input"
          />
          <input
            type="text" placeholder="Holiday name (e.g., Republic Day)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="input-flat md:col-span-2"
            data-testid="holiday-name-input"
          />
          <select
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
            className="input-flat"
            data-testid="holiday-kind-select"
          >
            {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
          <label className="flex items-center gap-1 text-xs">
            <input
              type="checkbox" checked={form.recurring}
              onChange={(e) => setForm({ ...form, recurring: e.target.checked })}
              data-testid="holiday-recurring-checkbox"
            />
            Every year
          </label>
          <button
            className="btn-primary text-sm flex items-center gap-1 justify-center"
            onClick={create}
            data-testid="holiday-add-btn"
          >
            <Plus size={14} /> Add
          </button>
        </div>
      </div>

      {loading && <div className="overline">LOADING…</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Object.keys(grouped).sort().map((m) => (
          <div key={m} className="card-flat">
            <div className="overline mb-2">
              {new Date(m + "-01").toLocaleDateString("en-IN", { month: "long", year: "numeric" })}
            </div>
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <tbody>
                {grouped[m].sort((a, b) => a.date.localeCompare(b.date)).map((h) => {
                  const meta = kindMeta(h.kind);
                  return (
                    <tr key={h.id + h.date} className="border-b border-[#F5F5F5]" data-testid="holiday-row">
                      <td className="py-1.5 font-mono text-xs w-16">{h.date.slice(-2)}</td>
                      <td className="py-1.5">
                        <div className="font-medium">{h.name}</div>
                        <span className="text-xs" style={{ color: meta.color }}>{meta.label}{h.recurring && " · recurring"}</span>
                      </td>
                      <td className="py-1.5 text-right">
                        {!h.materialized_from_recurring && (
                          <button
                            className="text-[#B22B22] hover:opacity-70"
                            data-testid={`holiday-delete-${h.id}`}
                            onClick={() => del(h.id)}
                          >
                            <Trash size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table></div>
          </div>
        ))}
        {rows.length === 0 && !loading && (
          <div className="col-span-full text-sm text-[#9A9A9A] italic">
            No holidays configured for {year}. Add company + festival days above.
          </div>
        )}
      </div>

      {offs.length > 0 && (
        <div className="card-flat">
          <div className="overline mb-2">WEEKLY-OFF SUMMARY ({offs.length} DAYS IN {year})</div>
          <div className="text-xs text-[#5C5C5C]">
            Based on the attendance policy (Sunday by default). Adjust weekly-off days from Attendance → Policy.
          </div>
        </div>
      )}
    </div>
  );
}
