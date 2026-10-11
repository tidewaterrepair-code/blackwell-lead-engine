import { MapPin, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { GeoResult } from "../lib/types";
import { MapView } from "./MapView";

export type AreaChoice = { kind: string; data: any; name: string };

/** Search a city / county / ZIP, then choose radius or exact boundary. */
export function AreaPicker({ maxMiles = 40, onChange }: { maxMiles?: number; onChange: (c: AreaChoice | null) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<GeoResult[]>([]);
  const [picked, setPicked] = useState<GeoResult | null>(null);
  const [mode, setMode] = useState<"radius" | "exact">("radius");
  const [miles, setMiles] = useState(Math.min(25, maxMiles));

  useEffect(() => {
    if (q.trim().length < 2 || (picked && q === picked.label)) { setResults([]); return; }
    const t = setTimeout(() => api<{ results: GeoResult[] }>(`/api/geo/search?q=${encodeURIComponent(q)}`)
      .then((r) => setResults(r.results)).catch(() => setResults([])), 180);
    return () => clearTimeout(t);
  }, [q, picked]);

  useEffect(() => {
    if (!picked) { onChange(null); return; }
    if (mode === "radius") {
      onChange({ kind: "radius", name: `${picked.label} + ${miles} mi`,
                 data: { lat: picked.lat, lng: picked.lng, miles, label: picked.label } });
    } else if (picked.type === "zip") {
      onChange({ kind: "zip", name: `ZIP ${picked.id}`, data: { zips: [picked.id] } });
    } else if (picked.type === "county") {
      onChange({ kind: "county", name: picked.label, data: { fips: [picked.id] } });
    } else {
      const [city, state] = picked.id.split("|");
      onChange({ kind: "city", name: picked.label, data: { city, state } });
    }
  }, [picked, mode, miles]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input className="input pl-9" placeholder="City, county or ZIP (e.g. Virginia Beach, VA or 23456)" value={q}
               onChange={(e) => { setQ(e.target.value); setPicked(null); }} autoFocus />
        {results.length > 0 && (
          <div className="card absolute z-[1100] mt-1 w-full p-1 max-h-72 overflow-y-auto">
            {results.map((r) => (
              <button key={`${r.type}-${r.id}`} className="w-full text-left px-3 py-2 rounded-lg hover:bg-surface2 flex items-center gap-2 text-sm"
                      onClick={() => { setPicked(r); setQ(r.label); setResults([]); }}>
                <MapPin size={14} className="text-brand" />{r.label}
                <span className="ml-auto text-xs text-muted uppercase">{r.type}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {picked && (
        <>
          <div className="flex gap-2">
            <button className={`chip ${mode === "radius" ? "chip-active" : ""}`} onClick={() => setMode("radius")}>Radius around it</button>
            <button className={`chip ${mode === "exact" ? "chip-active" : ""}`} onClick={() => setMode("exact")}>
              Exactly this {picked.type}
            </button>
          </div>
          {mode === "radius" && (
            <div>
              <div className="flex justify-between text-xs text-ink2"><span>Radius</span><span className="font-semibold text-ink">{miles} miles</span></div>
              <input type="range" min={3} max={maxMiles} value={miles} onChange={(e) => setMiles(+e.target.value)}
                     className="w-full accent-[rgb(var(--brand))]" />
            </div>
          )}
          <div className="h-56 rounded-2xl overflow-hidden">
            <MapView points={[]} center={[picked.lat, picked.lng]}
                     territories={mode === "radius" ? [{ id: 0, name: "", kind: "radius", trades: [], exclusive: false,
                                                          data: { lat: picked.lat, lng: picked.lng, miles } }] : []} />
          </div>
        </>
      )}
    </div>
  );
}
