import { useEffect, useRef, useState } from "react";

/**
 * Interactive geofence map (Leaflet via CDN global `L`).
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
  const [noLib, setNoLib] = useState(false);

  // Init map once (poll for the CDN library)
  useEffect(() => {
    let cancelled = false;
    let tries = 0;
    const boot = () => {
      if (cancelled) return;
      const L = window.L;
      if (!L) {
        tries += 1;
        if (tries > 40) { setNoLib(true); return; }
        setTimeout(boot, 250);
        return;
      }
      if (mapRef.current || !elRef.current) return;
      const hasPoint = lat !== "" && lat != null && lng !== "" && lng != null;
      const center = hasPoint ? [Number(lat), Number(lng)] : [20.5937, 78.9629];
      const map = L.map(elRef.current, { zoomControl: true, attributionControl: false })
        .setView(center, hasPoint ? 16 : 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      map.on("click", (e) => {
        if (onPick) onPick(Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6)));
      });
      mapRef.current = map;
      setTimeout(() => { try { map.invalidateSize(); } catch (_) {} }, 250);
      setReady(true);
    };
    boot();
    return () => {
      cancelled = true;
      if (mapRef.current) { try { mapRef.current.remove(); } catch (_) {} mapRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Selected pin + radius circle
  useEffect(() => {
    const L = window.L;
    const map = mapRef.current;
    if (!ready || !L || !map) return;
    const hasPoint = lat !== "" && lat != null && lng !== "" && lng != null;
    if (!hasPoint) {
      if (markerRef.current) { map.removeLayer(markerRef.current); markerRef.current = null; }
      if (circleRef.current) { map.removeLayer(circleRef.current); circleRef.current = null; }
      return;
    }
    const pos = [Number(lat), Number(lng)];
    if (!markerRef.current) {
      markerRef.current = L.marker(pos, { draggable: true }).addTo(map);
      markerRef.current.on("dragend", () => {
        const p = markerRef.current.getLatLng();
        if (onPick) onPick(Number(p.lat.toFixed(6)), Number(p.lng.toFixed(6)));
      });
    } else {
      markerRef.current.setLatLng(pos);
    }
    if (!circleRef.current) {
      circleRef.current = L.circle(pos, {
        radius: Number(radius) || 150, color: "#8B7F6A", weight: 2,
        fillColor: "#8B7F6A", fillOpacity: 0.12,
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
    const L = window.L;
    const layer = layerRef.current;
    if (!ready || !L || !layer) return;
    layer.clearLayers();
    (locations || []).forEach((l) => {
      if (l.lat == null || l.lng == null) return;
      L.circle([Number(l.lat), Number(l.lng)], {
        radius: Number(l.radius_m) || 150, color: "#76705E", weight: 1,
        fillColor: "#C9A84C", fillOpacity: 0.08, dashArray: "4 4",
      }).addTo(layer).bindPopup(`${l.name || "Location"} · ${l.radius_m || 150}m`);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, locations]);

  if (noLib) {
    return (
      <div className="rounded-xl border border-[#E8E6E1] bg-[#F5F4F0] flex items-center justify-center text-xs text-[#9B9B9B]"
           style={{ height }} data-testid="geofence-map-fallback">
        Map couldn't load. Coordinates can still be set with the fields below.
      </div>
    );
  }

  return (
    <div
      ref={elRef}
      data-testid="geofence-map"
      className="rounded-xl overflow-hidden border border-[#E8E6E1] leaflet-premium"
      style={{ height, width: "100%", zIndex: 0 }}
    />
  );
};

export default GeoFenceMap;
