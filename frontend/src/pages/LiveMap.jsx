import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowsClockwise, MapPin } from "@phosphor-icons/react";
import api from "../lib/api";
import { dateForInput, formatDate, formatTime, statusLabel } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import PageHero from "../components/PageHero";
import CheckInMap, { MapLegend } from "../components/CheckInMap";
import { GEO_LABEL, errText } from "../components/SiteVisits";

const TYPE_LABEL = {
  office: "Office check-in", site_visit: "Site visit", client_meeting: "Client meeting",
  warehouse: "Warehouse", vendor_visit: "Vendor visit",
};
const FILTERS = [
  { id: "all", label: "Everyone" },
  { id: "on_site", label: "On site now" },
  { id: "office", label: "Office check-ins" },
  { id: "outside", label: "Outside a fence" },
];

const todayIST = () => dateForInput(new Date());

function pinLines(p) {
  const time = `${formatTime(p.at)}${p.checked_out_at ? ` – ${formatTime(p.checked_out_at)}` : p.open ? " · on site now" : ""}`;
  if (p.type === "site_visit") {
    return [p.employee_name, `Site visit · ${p.place || "Project"}`, time,
      GEO_LABEL[p.geo_status]?.label, p.photo_count ? `${p.photo_count} photo${p.photo_count === 1 ? "" : "s"}` : null];
  }
  return [p.employee_name, `${TYPE_LABEL[p.attendance_type] || "Check-in"}${p.place ? ` · ${p.place}` : ""}`, time,
    p.geo_inside === false ? "Outside the fence" : null,
    p.approval_status === "pending" ? "Waiting for approval" : null];
}

export default function LiveMap() {
  const { hasPerm } = useAuth();
  const [date, setDate] = useState(todayIST());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [focusId, setFocusId] = useState(null);
  const mapBox = useRef(null);
  const isToday = date === todayIST();
  const canOpenProjects = hasPerm("projects.read");

  const load = useCallback(async () => {
    try {
      const { data: body } = await api.get("/site-visits/live-map", { params: { date } });
      setData(body);
      setError("");
    } catch (e) {
      setError(errText(e, "Could not load the live map"));
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { setLoading(true); load(); }, [load]);
  // Refresh every minute while looking at today (paused in background tabs).
  useEffect(() => {
    if (!isToday) return undefined;
    const t = setInterval(() => { if (document.visibilityState === "visible") load(); }, 60_000);
    return () => clearInterval(t);
  }, [isToday, load]);

  const pins = useMemo(() => {
    const rows = (data?.pins || []).filter((p) => {
      if (filter === "on_site") return p.type === "site_visit" && p.open;
      if (filter === "office") return p.type === "check_in";
      if (filter === "outside") return p.geo_inside === false;
      return true;
    });
    return [...rows].sort((a, b) => String(a.at || "").localeCompare(String(b.at || "")));
  }, [data, filter]);

  const mapPins = useMemo(() => pins.map((p) => ({
    id: p.id, lat: p.lat, lng: p.lng, inside: p.geo_inside !== false,
    shape: p.type === "site_visit" ? "square" : "dot",
    faded: p.type === "site_visit" ? !p.open : !!p.checked_out_at,
    title: p.employee_name, lines: pinLines(p),
  })), [pins]);

  const focus = (id) => {
    setFocusId(null);
    setTimeout(() => setFocusId(id), 0);
    if (mapBox.current && window.matchMedia && window.matchMedia("(max-width: 1023px)").matches) {
      mapBox.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const s = data?.summary || {};
  const stats = [
    ["Checked in", s.checked_in], ["On site now", s.on_site_now], ["Site visits", s.site_visits],
    ["Outside a fence", s.outside_fence], ["No location", s.no_location],
  ];

  return (
    <div className="space-y-6" data-testid="live-map-page">
      <PageHero title="Live map"
                kicker={data?.scope === "team"
                  ? "Check-ins and site visits of your project teams."
                  : "Where the team checked in today, with office and site fences."}>
        <label className="sr-only" htmlFor="live-map-date">Date</label>
        <input id="live-map-date" type="date" className="input-flat" value={date} max={todayIST()}
               onChange={(e) => setDate(e.target.value || todayIST())} data-testid="live-map-date" />
        <button type="button" className="btn-ghost" onClick={() => { setLoading(true); load(); }} data-testid="live-map-refresh">
          <ArrowsClockwise size={14} /> Refresh
        </button>
      </PageHero>

      {error && <div className="card-flat text-sm text-[var(--danger)]" role="alert">{error}</div>}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3" data-testid="live-map-summary">
        {stats.map(([label, value]) => (
          <div key={label} className="card-flat !p-3">
            <div className="text-xs text-[var(--ink-3)]">{label}</div>
            <div className="font-display font-bold text-2xl tabular-nums">{loading && !data ? "–" : (value ?? 0)}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter pins">
          {FILTERS.map((f) => (
            <button key={f.id} type="button" onClick={() => setFilter(f.id)} aria-pressed={filter === f.id}
                    className={`px-3 h-8 rounded-full text-xs font-semibold border transition ${filter === f.id
                      ? "bg-[var(--accent-strong)] text-white border-[var(--accent-strong)]"
                      : "bg-white text-[var(--ink-2)] border-[var(--line)] hover:border-[var(--line-strong)]"}`}
                    data-testid={`live-map-filter-${f.id}`}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="text-xs text-[var(--ink-3)]">
          {isToday ? `Updated ${data?.generated_at || "—"} · refreshes every minute` : formatDate(date)}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-4 items-start">
        <div ref={mapBox} className="space-y-2 lg:sticky lg:top-4">
          <CheckInMap pins={mapPins} fences={data?.fences || []} height={520} focusId={focusId} testid="live-map" />
          <MapLegend />
        </div>
        <div className="space-y-2" data-testid="live-map-list">
          {!loading && pins.length === 0 && (
            <div className="card-flat text-sm text-[var(--ink-3)] text-center py-8">
              {filter === "all" ? `No check-ins with a location ${isToday ? "yet today" : "on this day"}.` : "Nobody matches this filter."}
            </div>
          )}
          {pins.map((p) => {
            const outside = p.geo_inside === false;
            return (
              <div key={`${p.type}-${p.id}`} className="card-flat !p-3 flex items-start gap-3" data-testid="live-map-row">
                <button type="button" onClick={() => focus(p.id)}
                        className="mt-0.5 shrink-0 w-8 h-8 rounded-full flex items-center justify-center border border-[var(--line)] hover:border-[var(--line-strong)]"
                        aria-label={`Show ${p.employee_name} on the map`}>
                  <MapPin size={16} weight="fill" color={outside ? "#B3923A" : "#1D633E"} />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm">{p.employee_name}</span>
                    {p.type === "site_visit" && p.open && <span className="status-chip chip-sent">On site</span>}
                    {outside && <span className="status-chip chip-pending">{p.type === "site_visit" ? GEO_LABEL[p.geo_status]?.label : "Outside fence"}</span>}
                    {p.approval_status === "pending" && <span className="status-chip chip-pending">{statusLabel("pending")}</span>}
                  </div>
                  <div className="text-xs text-[var(--ink-2)] mt-0.5">
                    {p.type === "site_visit"
                      ? (canOpenProjects && p.project_id
                        ? <Link to={`/projects/${p.project_id}`} className="underline underline-offset-2 hover:text-[var(--ink)]">{p.place}</Link>
                        : p.place)
                      : `${TYPE_LABEL[p.attendance_type] || "Check-in"}${p.place ? ` · ${p.place}` : ""}`}
                  </div>
                  <div className="text-xs text-[var(--ink-3)] tabular-nums mt-0.5">
                    {formatTime(p.at)}{p.checked_out_at ? ` – ${formatTime(p.checked_out_at)}` : ""}
                    {p.photo_count ? ` · ${p.photo_count} photo${p.photo_count === 1 ? "" : "s"}` : ""}
                    {p.accuracy_m ? ` · ±${Math.round(p.accuracy_m)} m` : ""}
                  </div>
                </div>
              </div>
            );
          })}
          {(data?.no_location || []).length > 0 && (
            <div className="card-flat !p-3" data-testid="live-map-no-location">
              <div className="overline mb-2">CHECKED IN WITHOUT A LOCATION</div>
              <ul className="space-y-1 text-sm">
                {data.no_location.map((n) => (
                  <li key={`${n.employee_id}-${n.at}`} className="flex justify-between gap-3">
                    <span>{n.employee_name}</span>
                    <span className="text-[var(--ink-3)] tabular-nums">{formatTime(n.at)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
