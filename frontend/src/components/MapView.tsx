import L from "leaflet";
import { useEffect, useMemo } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Circle, GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import { familyColor, tagMeta } from "../lib/tags";
import type { Territory } from "../lib/types";

export type MapPoint = { id: number; lat: number; lng: number; score: number; tag: string; title: string; type?: string; fresh?: boolean };

function pinIcon(p: MapPoint) {
  const { family, Icon } = tagMeta(p.tag);
  const color = familyColor(family);
  const size = p.score >= 75 ? 34 : 28;
  const html = renderToStaticMarkup(
    <div style={{ position: "relative", width: size, height: size }}>
      {p.fresh && <span className="animate-pulsering" style={{ position: "absolute", inset: 0, borderRadius: 999, background: color }} />}
      <div style={{ position: "absolute", inset: 0, borderRadius: 999, background: color, display: "grid", placeItems: "center",
                    border: `2px solid ${p.type === "prediction" ? "#FFC24B" : "rgba(255,255,255,0.9)"}`,
                    boxShadow: "0 4px 14px rgba(0,0,0,0.35)" }}>
        <Icon size={size * 0.48} color="#fff" strokeWidth={2.4} />
      </div>
    </div>,
  );
  return L.divIcon({ html, className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function FitBounds({ points, fallback }: { points: MapPoint[]; fallback: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lng])), { padding: [40, 40], maxZoom: 13 });
    else map.setView(fallback, 10);
  }, [points.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function MapView({ points, territories = [], center, onSelect, height = "100%" }: {
  points: MapPoint[]; territories?: Territory[]; center?: [number, number]; onSelect?: (id: number) => void; height?: string;
}) {
  const fallback: [number, number] = center ?? [36.85, -76.2];
  const icons = useMemo(() => new Map(points.map((p) => [p.id, pinIcon(p)])), [points]);
  return (
    <MapContainer center={fallback} zoom={10} style={{ height, width: "100%", borderRadius: 16 }} scrollWheelZoom>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19}
                 attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' />
      {territories.map((t) => t.kind === "radius" ? (
        <Circle key={t.id} center={[t.data.lat, t.data.lng]} radius={t.data.miles * 1609.34}
                pathOptions={{ color: "#7C5CFF", weight: 1.5, fillOpacity: 0.05, dashArray: "6 6" }} />
      ) : t.kind === "polygon" ? (
        <GeoJSON key={t.id} data={t.data.geojson} style={{ color: "#22D3EE", weight: 1.5, fillOpacity: 0.05 }} />
      ) : null)}
      {points.map((p) => (
        <Marker key={p.id} position={[p.lat, p.lng]} icon={icons.get(p.id)!}
                eventHandlers={{ click: () => onSelect?.(p.id) }}>
          <Popup><div className="text-sm font-semibold">{p.title}</div><div className="text-xs">Score {p.score}</div></Popup>
        </Marker>
      ))}
      <FitBounds points={points} fallback={fallback} />
    </MapContainer>
  );
}
