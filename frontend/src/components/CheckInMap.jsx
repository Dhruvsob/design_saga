import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Read-only map of check-in / site-visit pins and geo-fences.
// Keyless OpenStreetMap tiles (same providers as GeoFenceMap). Colours come
// from the existing palette: green = inside a fence, gold = outside / needs
// approval; a square marks a site visit, a dot an office check-in; finished
// visits and checked-out people are faded.
export const PIN_COLORS = { inside: "#1D633E", outside: "#B3923A" };
const FENCE_STYLE = {
  office: { color: "#2C2C2C", fillColor: "#5C5C5C" },
  site: { color: "#76705E", fillColor: "#8B7F6A" },
};

function pinIcon({ inside, shape, faded }) {
  const fill = inside ? PIN_COLORS.inside : PIN_COLORS.outside;
  const glyph = shape === "square"
    ? '<rect x="10" y="10" width="10" height="10" rx="1.5" fill="#fff"/>'
    : '<circle cx="15" cy="15" r="5.5" fill="#fff"/>';
  return L.divIcon({
    className: "checkin-pin",
    html: `<svg width="30" height="42" viewBox="0 0 30 42" aria-hidden="true" style="opacity:${faded ? 0.55 : 1}">`
      + `<path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.4 15 41 15 41s14-15.6 14-26.1C29 7.2 22.7 1 15 1z" fill="${fill}" stroke="#fff" stroke-width="2"/>`
      + `${glyph}</svg>`,
    iconSize: [30, 42],
    iconAnchor: [15, 41],
    popupAnchor: [0, -36],
  });
}

// Popup built from text nodes so names/notes can never inject markup.
function popupNode(lines) {
  const el = document.createElement("div");
  el.style.minWidth = "160px";
  lines.filter(Boolean).forEach((line, i) => {
    const row = document.createElement("div");
    row.textContent = line;
    row.style.fontSize = i === 0 ? "13px" : "12px";
    row.style.fontWeight = i === 0 ? "600" : "400";
    row.style.color = i === 0 ? "#2C2C2C" : "#5C5C5C";
    el.appendChild(row);
  });
  return el;
}

const valid = (p) => p && Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng))
  && p.lat !== null && p.lng !== null;

/**
 * pins:   [{ id, lat, lng, inside, shape: "dot"|"square", faded, title, lines: [] }]
 * fences: [{ id, lat, lng, radius_m, name, kind }]
 * focusId: pin id to centre on and open
 */
export default function CheckInMap({ pins = [], fences = [], height = 420, focusId, onSelect, testid = "checkin-map" }) {
  const elRef = useRef(null);
  const mapRef = useRef(null);
  const pinLayerRef = useRef(null);
  const fenceLayerRef = useRef(null);
  const markersRef = useRef({});
  const fittedRef = useRef("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (mapRef.current || !elRef.current) return undefined;
    const map = L.map(elRef.current, { zoomControl: true, attributionControl: true })
      .setView([20.5937, 78.9629], 5);
    map.attributionControl.setPrefix(false);
    const streets = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, referrerPolicy: "strict-origin-when-cross-origin",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    }).addTo(map);
    const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Imagery &copy; Esri",
    });
    L.control.layers({ Map: streets, Satellite: satellite }, null, { position: "topright" }).addTo(map);
    fenceLayerRef.current = L.layerGroup().addTo(map);
    pinLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    const t = setTimeout(() => { try { map.invalidateSize(); } catch { /* unmounted */ } }, 250);
    setReady(true);
    return () => {
      clearTimeout(t);
      try { map.remove(); } catch { /* already gone */ }
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    fenceLayerRef.current.clearLayers();
    pinLayerRef.current.clearLayers();
    markersRef.current = {};
    const bounds = [];
    fences.filter(valid).forEach((f) => {
      const style = FENCE_STYLE[f.kind] || FENCE_STYLE.site;
      const centre = [Number(f.lat), Number(f.lng)];
      L.circle(centre, {
        radius: Number(f.radius_m) || 150, weight: 2, dashArray: "6 4", fillOpacity: 0.1, ...style,
      }).addTo(fenceLayerRef.current)
        .bindPopup(popupNode([f.name || "Location", `${f.kind === "office" ? "Office" : "Site"} fence · ${f.radius_m || 150} m`]));
      bounds.push(centre);
    });
    pins.filter(valid).forEach((p) => {
      const pos = [Number(p.lat), Number(p.lng)];
      const marker = L.marker(pos, {
        icon: pinIcon(p), title: p.title || "Check-in", alt: p.title || "Check-in", keyboard: true,
      }).addTo(pinLayerRef.current);
      marker.bindPopup(popupNode(p.lines || [p.title]));
      if (onSelect) marker.on("click", () => onSelect(p.id));
      markersRef.current[p.id] = marker;
      bounds.push(pos);
    });
    // Fit once per distinct set of points so a refresh doesn't fight the user's zoom.
    const key = bounds.map((b) => b.join(",")).sort().join("|");
    if (bounds.length && key !== fittedRef.current) {
      fittedRef.current = key;
      if (bounds.length === 1) map.setView(bounds[0], 16);
      else map.fitBounds(bounds, { padding: [36, 36], maxZoom: 17 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, pins, fences]);

  useEffect(() => {
    const map = mapRef.current;
    const marker = focusId && markersRef.current[focusId];
    if (!ready || !map || !marker) return;
    map.setView(marker.getLatLng(), Math.max(map.getZoom(), 16));
    marker.openPopup();
  }, [ready, focusId]);

  return (
    <div
      ref={elRef}
      data-testid={testid}
      role="region"
      aria-label="Map of check-ins and site fences"
      className="rounded-xl overflow-hidden border border-[var(--line)]"
      style={{ height, width: "100%", zIndex: 0 }}
    />
  );
}

export function MapLegend({ className = "" }) {
  const dot = (color, square) => (
    <span aria-hidden="true" className="inline-block w-2.5 h-2.5 shrink-0"
          style={{ background: color, borderRadius: square ? 2 : 999 }} />
  );
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--ink-2)] ${className}`} data-testid="map-legend">
      <span className="inline-flex items-center gap-1.5">{dot(PIN_COLORS.inside)} Inside a fence</span>
      <span className="inline-flex items-center gap-1.5">{dot(PIN_COLORS.outside)} Outside / needs approval</span>
      <span className="inline-flex items-center gap-1.5">{dot("#6E6A63")} Office check-in</span>
      <span className="inline-flex items-center gap-1.5">{dot("#6E6A63", true)} Site visit</span>
      <span className="inline-flex items-center gap-1.5 opacity-60">{dot("#6E6A63")} Finished</span>
    </div>
  );
}
