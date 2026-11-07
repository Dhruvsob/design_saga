import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Drawn pin (no image files): Leaflet's default marker PNGs are not bundled by Vite
// and showed as a broken image.
const PIN_ICON = L.divIcon({
  className: "geofence-pin",
  html: '<svg width="30" height="42" viewBox="0 0 30 42" aria-hidden="true">'
    + '<path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.4 15 41 15 41s14-15.6 14-26.1C29 7.2 22.7 1 15 1z" fill="#1D633E" stroke="#fff" stroke-width="2"/>'
    + '<circle cx="15" cy="15" r="5.5" fill="#fff"/></svg>',
  iconSize: [30, 42],
  iconAnchor: [15, 41],
  popupAnchor: [0, -36],
});

/**
 * Interactive geofence map.
 * - Shows a draggable pin + radius circle for the selected fence.
 * - Click the map or drag the pin to set coordinates (onPick).
 * - Plots existing saved geofence locations as dashed circles.
 * Mirrors the Jewellers ERP attendance map.
 */
export const GeoFenceMap = ({ lat, lng, radius = 150, locations = [], onPick, height = 320 }) => {
  const elRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const circleRef = useRef(null);
  const layerRef = useRef(null);
  const [ready, setReady] = useState(false);

  // Init map once.
  useEffect(() => {
    if (mapRef.current || !elRef.current) return undefined;
    const hasPoint = lat !== "" && lat != null && lng !== "" && lng != null;
    const center = hasPoint ? [Number(lat), Number(lng)] : [20.5937, 78.9629];
    const map = L.map(elRef.current, { zoomControl: true, attributionControl: true })
      .setView(center, hasPoint ? 16 : 5);
    map.attributionControl.setPrefix(false);
    // Colourful street map (default) + satellite imagery to see the actual building.
    // Both providers work without an API key (CARTO now refuses unregistered domains).
    const streets = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, referrerPolicy: "strict-origin-when-cross-origin",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    }).addTo(map);
    const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Imagery &copy; Esri",
    });
    L.control.layers({ Map: streets, Satellite: satellite }, null, { position: "topright" }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    map.on("click", (e) => {
      if (onPick) onPick(Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6)));
    });
    mapRef.current = map;
    setTimeout(() => { try { map.invalidateSize(); } catch (_) {} }, 250);
    setReady(true);
    return () => {
      if (mapRef.current) { try { mapRef.current.remove(); } catch (_) {} mapRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Selected pin + radius circle
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const hasPoint = lat !== "" && lat != null && lng !== "" && lng != null;
    if (!hasPoint) {
      if (markerRef.current) { map.removeLayer(markerRef.current); markerRef.current = null; }
      if (circleRef.current) { map.removeLayer(circleRef.current); circleRef.current = null; }
      return;
    }
    const pos = [Number(lat), Number(lng)];
    if (!markerRef.current) {
      markerRef.current = L.marker(pos, { draggable: true, icon: PIN_ICON, title: "Office location", alt: "Office location" }).addTo(map);
      markerRef.current.on("dragend", () => {
        const p = markerRef.current.getLatLng();
        if (onPick) onPick(Number(p.lat.toFixed(6)), Number(p.lng.toFixed(6)));
      });
    } else {
      markerRef.current.setLatLng(pos);
    }
    if (!circleRef.current) {
      circleRef.current = L.circle(pos, {
        radius: Number(radius) || 150, color: "#1D633E", weight: 2.5,
        fillColor: "#2E9E62", fillOpacity: 0.18,
      }).addTo(map);
    } else {
      circleRef.current.setLatLng(pos);
      circleRef.current.setRadius(Number(radius) || 150);
    }
    map.setView(pos, Math.max(map.getZoom(), 15));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, lat, lng, radius]);

  // Existing saved locations
  useEffect(() => {
    const layer = layerRef.current;
    if (!ready || !layer) return;
    layer.clearLayers();
    (locations || []).forEach((l) => {
      if (l.lat == null || l.lng == null) return;
      L.circle([Number(l.lat), Number(l.lng)], {
        radius: Number(l.radius_m) || 150, color: "#2B5299", weight: 2,
        fillColor: "#4C7BD9", fillOpacity: 0.14, dashArray: "6 4",
      }).addTo(layer).bindPopup(`${l.name || "Location"} · ${l.radius_m || 150}m`);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, locations]);

  return (
    <div
      ref={elRef}
      data-testid="geofence-map"
      className="rounded-xl overflow-hidden border border-[var(--line)]"
      style={{ height, width: "100%", zIndex: 0 }}
    />
  );
};

export default GeoFenceMap;
