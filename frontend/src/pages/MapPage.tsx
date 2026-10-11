import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapView, type MapPoint } from "../components/MapView";
import { FamilyLegend } from "../components/TagChip";
import { qs } from "../lib/api";
import { useFetch, useLeadStream } from "../lib/hooks";
import type { Territory } from "../lib/types";

export default function MapPage() {
  const navigate = useNavigate();
  const [type, setType] = useState<string | undefined>();
  const [days, setDays] = useState(60);
  const [minScore, setMinScore] = useState<number | undefined>();
  const { data, setData } = useFetch<{ points: MapPoint[] }>(`/api/map${qs({ type, days, min_score: minScore })}`, [type, days, minScore]);
  const { data: terr } = useFetch<{ items: Territory[] }>("/api/territories");
  useLeadStream((lead: any) => {
    const s = lead.signal;
    if (!s?.lat || !data) return;
    setData({ points: [{ id: lead.id, lat: s.lat, lng: s.lng, score: lead.score, tag: lead.prediction?.tag ?? s.tag,
                         title: s.title, type: lead.type, fresh: true }, ...data.points] });
  });
  const center = terr?.items.find((t) => t.kind === "radius")?.data;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="font-display text-2xl font-bold mr-2">Radar</h1>
        {[["All", undefined], ["Direct", "signal"], ["Predicted", "prediction"]].map(([l, v]) => (
          <button key={l as string} className={`chip ${type === v ? "chip-active" : ""}`} onClick={() => setType(v as any)}>{l}</button>
        ))}
        <select className="input w-auto py-1.5" value={days} onChange={(e) => setDays(+e.target.value)}>
          {[7, 30, 60, 180].map((d) => <option key={d} value={d}>Last {d} days</option>)}
        </select>
        <select className="input w-auto py-1.5" value={minScore ?? ""} onChange={(e) => setMinScore(e.target.value ? +e.target.value : undefined)}>
          <option value="">Any score</option>{[50, 65, 75].map((s) => <option key={s} value={s}>Score {s}+</option>)}
        </select>
        <span className="ml-auto text-sm text-ink2">{data?.points.length ?? 0} on map</span>
      </div>
      <FamilyLegend />
      <div className="card p-1.5 h-[calc(100vh-220px)] min-h-[420px]">
        <MapView points={data?.points ?? []} territories={terr?.items ?? []} center={center ? [center.lat, center.lng] : undefined}
                 onSelect={(id) => navigate(`/leads/${id}`)} />
      </div>
      <p className="text-xs text-muted">Gold-ringed pins are predicted jobs. Pulsing pins just arrived.</p>
    </div>
  );
}
