import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import {
  ArrowUpRight, TrendUp, Warning, Clock, Money, Briefcase, Sparkle,
} from "@phosphor-icons/react";

const fmtMoney = (n) => `₹${(n || 0).toLocaleString("en-IN")}`;

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const { data } = await api.get("/dashboard/stats");
      setStats(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const seed = async () => {
    setSeeding(true);
    try { await api.post("/seed"); await load(); } finally { setSeeding(false); }
  };

  if (loading) return <div className="overline">LOADING…</div>;

  const kpis = stats?.kpis || {};
  const pipeline = stats?.pipeline || [];
  const alerts = stats?.alerts || [];
  const util = stats?.utilization || [];
  const sources = stats?.sources || [];

  const maxFunnel = Math.max(...pipeline.map((p) => p.count), 1);
  const maxUtil = Math.max(...util.map((u) => u.load), 1);

  return (
    <div className="space-y-8" data-testid="dashboard-page">
      {/* Hero */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="overline mb-2">OVERVIEW / TODAY</div>
          <h1 className="font-display font-bold tracking-tight text-4xl lg:text-5xl">
            The control room.
          </h1>
          <p className="text-[#5C5C5C] mt-2 max-w-lg">
            Every lead, line item, and late task — in one frame.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={seed} disabled={seeding} className="btn-ghost" data-testid="seed-btn">
            <Sparkle size={14} /> {seeding ? "Seeding…" : "Seed demo data"}
          </button>
          <button onClick={() => navigate("/crm")} className="btn-primary" data-testid="add-lead-btn">
            <ArrowUpRight size={14} /> New lead
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 border-t border-l border-[#E5E5E5]">
        <Kpi label="Revenue collected" value={fmtMoney(kpis.revenue)} Icon={Money} testid="kpi-revenue" />
        <Kpi label="Active projects" value={kpis.active_projects || 0} Icon={Briefcase} testid="kpi-active-projects" />
        <Kpi label="Overdue tasks" value={kpis.overdue_tasks || 0} Icon={Warning} accent={kpis.overdue_tasks ? "#FF2A00" : undefined} testid="kpi-overdue" />
        <Kpi label="Collection due" value={fmtMoney(kpis.collection_due)} Icon={Clock} accent="#002FA7" testid="kpi-collection" />
      </div>

      {/* Row 2: funnel + alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card-flat lg:col-span-2" data-testid="pipeline-funnel">
          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="overline mb-1">PIPELINE / FUNNEL</div>
              <div className="font-display font-bold text-xl tracking-tight">Leads by stage</div>
            </div>
            <TrendUp size={20} className="text-[#002FA7]" />
          </div>
          <div className="space-y-3">
            {pipeline.map((s) => (
              <div key={s.stage} className="flex items-center gap-4">
                <div className="w-28 text-sm font-mono tracking-wider uppercase text-[#5C5C5C]">{s.stage}</div>
                <div className="flex-1 h-8 bg-[#FAFAFA] relative">
                  <div
                    className="h-full bg-[#002FA7]"
                    style={{ width: `${(s.count / maxFunnel) * 100}%` }}
                  />
                </div>
                <div className="w-10 text-right font-mono font-semibold">{s.count}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card-flat" data-testid="alerts-panel">
          <div className="overline mb-4">ALERTS / NOW</div>
          {alerts.length === 0 ? (
            <p className="text-sm text-[#5C5C5C]">All clear. Proceed calmly.</p>
          ) : (
            <div className="space-y-3">
              {alerts.map((a, i) => (
                <div
                  key={i}
                  className="border-l-2 pl-3 py-2"
                  style={{ borderColor: a.level === "high" ? "#FF2A00" : "#002FA7" }}
                >
                  <div className="text-xs font-mono uppercase tracking-wider text-[#5C5C5C]">{a.level}</div>
                  <div className="text-sm">{a.message}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Row 3: utilization + sources */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-flat" data-testid="utilization">
          <div className="overline mb-4">TEAM / UTILIZATION</div>
          {util.length === 0 ? (
            <p className="text-sm text-[#5C5C5C]">No active tasks assigned.</p>
          ) : (
            <div className="space-y-3">
              {util.map((u) => (
                <div key={u.name} className="flex items-center gap-4">
                  <div className="w-40 truncate text-sm">{u.name}</div>
                  <div className="flex-1 h-4 bg-[#FAFAFA] relative">
                    <div className="h-full bg-[#0A0A0A]" style={{ width: `${(u.load / maxUtil) * 100}%` }} />
                  </div>
                  <div className="w-10 text-right font-mono text-sm">{u.load}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card-flat" data-testid="sources">
          <div className="overline mb-4">LEADS / BY SOURCE</div>
          {sources.length === 0 ? (
            <p className="text-sm text-[#5C5C5C]">No leads recorded yet.</p>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {sources.map((s) => (
                <div key={s.source} className="border border-[#E5E5E5] p-3">
                  <div className="overline">{s.source}</div>
                  <div className="font-display font-bold text-2xl tracking-tight mt-1">{s.count}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, Icon, accent, testid }) {
  return (
    <div
      className="border-r border-b border-[#E5E5E5] p-6 bg-white hover:bg-[#FAFAFA] transition"
      data-testid={testid}
    >
      <div className="flex items-start justify-between mb-6">
        <div className="overline">{label}</div>
        <Icon size={18} style={{ color: accent || "#5C5C5C" }} />
      </div>
      <div
        className="font-display font-bold tracking-tight text-4xl"
        style={{ color: accent || "#0A0A0A" }}
      >
        {value}
      </div>
    </div>
  );
}
