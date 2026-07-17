import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import {
  ArrowUpRight, TrendUp, Warning, Clock, Money, Briefcase, Sparkle,
  CaretRight, ChartBar, Lightning,
} from "@phosphor-icons/react";

const fmtMoney = (n) => `₹${(n || 0).toLocaleString("en-IN")}`;
const compactMoney = (n) => {
  if (!n) return "₹0";
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)}Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${Math.round(n)}`;
};

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

  if (loading) return <DashboardSkeleton />;

  const kpis = stats?.kpis || {};
  const pipeline = stats?.pipeline || [];
  const alerts = stats?.alerts || [];
  const util = stats?.utilization || [];
  const sources = stats?.sources || [];

  const maxFunnel = Math.max(...pipeline.map((p) => p.count), 1);
  const maxUtil = Math.max(...util.map((u) => u.load), 1);
  const totalLeads = pipeline.reduce((s, p) => s + p.count, 0);
  const wonRate = totalLeads ? Math.round(((pipeline.find((p) => p.stage === "Won")?.count || 0) / totalLeads) * 100) : 0;

  return (
    <div className="space-y-10 stagger" data-testid="dashboard-page">
      {/* ============== HERO ============== */}
      <div className="fade-up flex items-start justify-between flex-wrap gap-4 pb-2 border-b border-[#E5E5E5]">
        <div>
          <div className="overline mb-3 flex items-center gap-3">
            <span className="live-dot" />
            OVERVIEW · {new Date().toDateString().toUpperCase()}
          </div>
          <h1 className="font-display font-bold tracking-tighter text-5xl lg:text-6xl leading-[0.95]">
            The control<br/>room.
          </h1>
          <p className="text-[#5C5C5C] mt-3 max-w-md text-lg">
            Every lead, line item, and late task — in one frame.
          </p>
        </div>
        <div className="flex items-center gap-3 mt-2">
          <button onClick={seed} disabled={seeding} className="btn-ghost" data-testid="seed-btn">
            <Sparkle size={14} /> {seeding ? "Seeding…" : "Seed demo data"}
          </button>
          <button onClick={() => navigate("/crm")} className="btn-primary" data-testid="add-lead-btn">
            <ArrowUpRight size={14} /> New lead
          </button>
        </div>
      </div>

      {/* ============== KPI ROW ============== */}
      <div className="fade-up">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 border-t border-l border-[#E5E5E5]">
          <Kpi
            label="Revenue collected"
            value={compactMoney(kpis.revenue)}
            sub={fmtMoney(kpis.revenue)}
            Icon={Money}
            accent="#1D633E"
            trend={kpis.revenue > 0 ? "+12%" : "—"}
            sparkData={[3, 5, 4, 7, 6, 9, 8]}
            testid="kpi-revenue"
          />
          <Kpi
            label="Active projects"
            value={kpis.active_projects || 0}
            sub={`${kpis.total_projects || 0} total`}
            Icon={Briefcase}
            accent="#002FA7"
            trend="LIVE"
            sparkData={[2, 3, 3, 4, 4, 5, kpis.active_projects || 0]}
            testid="kpi-active-projects"
          />
          <Kpi
            label="Overdue tasks"
            value={kpis.overdue_tasks || 0}
            sub={kpis.overdue_tasks > 0 ? "Action needed" : "All clear"}
            Icon={Warning}
            accent={kpis.overdue_tasks ? "#FF2A00" : "#5C5C5C"}
            trend={kpis.overdue_tasks > 0 ? "HOT" : "OK"}
            testid="kpi-overdue"
          />
          <Kpi
            label="Collection due"
            value={compactMoney(kpis.collection_due)}
            sub={fmtMoney(kpis.collection_due)}
            Icon={Clock}
            accent="#002FA7"
            trend={kpis.collection_due > 0 ? "FOLLOW UP" : "—"}
            sparkData={[1, 3, 2, 4, 3, 5, 4]}
            testid="kpi-collection"
          />
        </div>
      </div>

      {/* ============== ROW 2 ============== */}
      <div className="fade-up grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card-flat lg:col-span-2" data-testid="pipeline-funnel">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="overline mb-1">PIPELINE / FUNNEL</div>
              <div className="font-display font-bold text-2xl tracking-tighter">Leads by stage</div>
            </div>
            <div className="flex items-center gap-2 overline">
              <ChartBar size={14} className="text-[#002FA7]" />
              {totalLeads} TOTAL · {wonRate}% WIN
            </div>
          </div>
          <div className="space-y-3 mt-6">
            {pipeline.map((s, i) => (
              <div key={s.stage} className="flex items-center gap-4 group">
                <div className="w-28 flex items-center gap-2">
                  <span className="font-mono text-[10px] text-[#9A9A9A]">0{i + 1}</span>
                  <span className="text-xs font-mono tracking-wider uppercase text-[#5C5C5C] group-hover:text-[#0A0A0A] transition">{s.stage}</span>
                </div>
                <div className="flex-1 h-9 bg-[#FAFAFA] relative overflow-hidden border border-[#F0F0F0]">
                  <div
                    className="h-full transition-all duration-700 ease-out"
                    style={{
                      width: `${(s.count / maxFunnel) * 100}%`,
                      background: s.stage === "Won" ? "#1D633E" : s.stage === "Lost" ? "#FF2A00" : "#002FA7",
                      animation: "width-in 700ms cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                  />
                  {s.count > 0 && (
                    <div className="absolute inset-0 flex items-center px-3 text-xs font-mono font-semibold text-white mix-blend-difference">
                      {s.count} {s.count === 1 ? "lead" : "leads"}
                    </div>
                  )}
                </div>
                <div className="w-12 text-right font-mono font-semibold tabular-nums">{s.count}</div>
              </div>
            ))}
            {totalLeads === 0 && (
              <p className="text-sm text-[#5C5C5C] py-6 text-center">No leads yet. Tap "Seed demo data" or "New lead".</p>
            )}
          </div>
        </div>

        <div className="card-flat card-bordered-accent" data-testid="alerts-panel">
          <div className="flex items-center justify-between mb-4">
            <div className="overline">ALERTS / NOW</div>
            <Lightning size={16} className="text-[#FF2A00]" />
          </div>
          {alerts.length === 0 ? (
            <div className="py-8 text-center">
              <div className="font-display text-3xl tracking-tighter text-[#1D633E] mb-1">⏤</div>
              <p className="text-sm text-[#5C5C5C]">All clear.<br/>Proceed calmly.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {alerts.map((a, i) => (
                <div
                  key={i}
                  className="border-l-2 pl-3 py-2 hover:bg-[#FAFAFA] transition"
                  style={{ borderColor: a.level === "high" ? "#FF2A00" : "#002FA7" }}
                >
                  <div className="text-[10px] font-mono uppercase tracking-widest text-[#5C5C5C]">{a.level}</div>
                  <div className="text-sm font-medium">{a.message}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ============== ROW 3 ============== */}
      <div className="fade-up grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-flat" data-testid="utilization">
          <div className="flex items-center justify-between mb-4">
            <div className="overline">TEAM / UTILIZATION</div>
            <div className="overline">{util.length} {util.length === 1 ? "PERSON" : "PEOPLE"}</div>
          </div>
          {util.length === 0 ? (
            <p className="text-sm text-[#5C5C5C] py-6">No active tasks assigned.</p>
          ) : (
            <div className="space-y-4">
              {util.map((u, i) => {
                const pct = (u.load / maxUtil) * 100;
                return (
                  <div key={u.name} className="group">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-[#0A0A0A] text-white flex items-center justify-center text-[10px] font-display font-bold">
                          {u.name.slice(0, 1).toUpperCase()}
                        </div>
                        <span className="text-sm font-medium">{u.name}</span>
                      </div>
                      <span className="font-mono text-sm tabular-nums">
                        <span className="font-semibold">{u.load}</span>
                        <span className="text-[#9A9A9A]"> tasks</span>
                      </span>
                    </div>
                    <div className="h-2 bg-[#F0F0F0] relative overflow-hidden">
                      <div
                        className="h-2 bg-[#0A0A0A] group-hover:bg-[#002FA7] transition-colors"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card-flat" data-testid="sources">
          <div className="flex items-center justify-between mb-4">
            <div className="overline">LEADS / BY SOURCE</div>
            <button onClick={() => navigate("/crm")} className="overline hover:text-[#002FA7] flex items-center gap-1 transition">
              VIEW PIPELINE <CaretRight size={10} weight="bold" />
            </button>
          </div>
          {sources.length === 0 ? (
            <p className="text-sm text-[#5C5C5C] py-6">No leads recorded yet.</p>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {sources.map((s) => (
                <div key={s.source} className="border border-[#E5E5E5] p-4 hover:border-[#0A0A0A] hover:-translate-y-0.5 transition cursor-pointer">
                  <div className="overline">{s.source}</div>
                  <div className="font-display font-bold text-3xl tracking-tighter mt-1">{s.count}</div>
                  <div className="mt-2 h-0.5 bg-[#002FA7]" style={{ width: `${Math.min(100, s.count * 25)}%` }} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ============== MARQUEE FOOTER ============== */}
      <div className="fade-up border-t border-[#E5E5E5] pt-6 marquee">
        <div className="marquee-track text-[#5C5C5C]">
          {Array.from({ length: 2 }).map((_, k) => (
            <div key={k} className="flex items-center gap-12">
              <span className="overline">DESIGN SAGA STUDIO OS</span>
              <span className="overline">·  CRM</span>
              <span className="overline">·  PROJECTS</span>
              <span className="overline">·  TASKS</span>
              <span className="overline">·  CLIENTS</span>
              <span className="overline">·  INVOICES</span>
              <span className="overline">·  QUOTATIONS</span>
              <span className="overline">·  AI ASSISTANT</span>
              <span className="overline">·  CLIENT PORTAL</span>
              <span className="overline">·  PDF EXPORTS</span>
              <span className="overline">·  GOOGLE AUTH</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ============== KPI Card with sparkline ============== */
function Kpi({ label, value, sub, Icon, accent, trend, sparkData, testid }) {
  const max = sparkData ? Math.max(...sparkData, 1) : 0;
  return (
    <div
      className="border-r border-b border-[#E5E5E5] p-6 bg-white hover:bg-[#FAFAFA] transition relative group"
      data-testid={testid}
    >
      {/* hover left bar */}
      <div className="absolute left-0 top-0 bottom-0 w-[3px] opacity-0 group-hover:opacity-100 transition-opacity" style={{ background: accent || "#0A0A0A" }} />

      <div className="flex items-start justify-between mb-8">
        <div className="overline">{label}</div>
        <Icon size={18} style={{ color: accent || "#5C5C5C" }} weight="duotone" />
      </div>

      <div
        className="font-display font-bold tracking-tighter text-4xl lg:text-5xl"
        style={{ color: accent || "#0A0A0A" }}
      >
        {value}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="text-xs text-[#5C5C5C] truncate flex-1">{sub}</div>
        {trend && (
          <div className="font-mono text-[10px] font-semibold tracking-widest" style={{ color: accent || "#5C5C5C" }}>
            {trend}
          </div>
        )}
      </div>

      {/* Mini sparkline */}
      {sparkData && (
        <div className="mt-4 flex items-end gap-[3px] h-8">
          {sparkData.map((v, i) => (
            <div
              key={i}
              className="flex-1 transition-all"
              style={{
                height: `${(v / max) * 100}%`,
                background: i === sparkData.length - 1 ? (accent || "#0A0A0A") : "#E5E5E5",
                minHeight: 2,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ============== Skeleton ============== */
function DashboardSkeleton() {
  return (
    <div className="space-y-10" data-testid="dashboard-loading">
      <div className="space-y-3">
        <div className="skeleton h-3 w-40"></div>
        <div className="skeleton h-16 w-72"></div>
        <div className="skeleton h-4 w-96"></div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-px bg-[#E5E5E5]">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white p-6 space-y-3">
            <div className="skeleton h-3 w-24"></div>
            <div className="skeleton h-12 w-32"></div>
            <div className="skeleton h-8 w-full"></div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card-flat lg:col-span-2 space-y-3">
          <div className="skeleton h-4 w-32"></div>
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-8 w-full"></div>)}
        </div>
        <div className="card-flat space-y-3">
          <div className="skeleton h-4 w-32"></div>
          <div className="skeleton h-20 w-full"></div>
          <div className="skeleton h-20 w-full"></div>
        </div>
      </div>
    </div>
  );
}
