import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

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
    const streets = L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      maxZoom: 20, subdomains: "abcd",
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
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
