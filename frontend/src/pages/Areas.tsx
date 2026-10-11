import { Plus, Radar, Trash2 } from "lucide-react";
import { useState } from "react";
import { AreaPicker, type AreaChoice } from "../components/AreaPicker";
import { MapView } from "../components/MapView";
import { Modal } from "../components/Modal";
import { api } from "../lib/api";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Coverage, Territory } from "../lib/types";

const COVERAGE = {
  covered: { label: "Covered", pct: 100, tone: "bg-good" }, partial: { label: "Partial", pct: 55, tone: "bg-gold" },
  scouting: { label: "Scouting…", pct: 25, tone: "bg-violet animate-pulse" }, none: { label: "Queued", pct: 8, tone: "bg-muted" },
} as Record<string, { label: string; pct: number; tone: string }>;

export default function Areas() {
  const { me, toast, refreshMe } = useApp();
  const { data, reload } = useFetch<{ items: Territory[]; coverage: Coverage[] }>("/api/territories");
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<AreaChoice | null>(null);
  const [error, setError] = useState("");

  const add = async () => {
    if (!choice) return;
    setError("");
    try {
      await api("/api/territories", { body: choice });
      setOpen(false);
      toast({ title: "Area added", body: "Backfilling the last 30 days of leads…", tone: "good", icon: "📡" });
      reload();
      refreshMe();
    } catch (e: any) { setError(e.message); }
  };
  const remove = async (t: Territory) => {
    if (!confirm(`Stop watching ${t.name}?`)) return;
    await api(`/api/territories/${t.id}`, { method: "DELETE" });
    reload();
    refreshMe();
  };
  const used = data?.items.length ?? 0;
  const allowed = me?.plan.territories ?? 1;

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div><h1 className="font-display text-2xl font-bold">My areas</h1>
          <p className="text-sm text-ink2">{used} of {allowed} areas used. Anywhere in the US: if we don't cover it yet, Source Scout maps it.</p></div>
        <button className="btn-primary ml-auto" onClick={() => setOpen(true)} disabled={used >= allowed}><Plus size={16} />Add area</button>
      </div>
      <div className="grid lg:grid-cols-[1fr_380px] gap-4">
        <div className="card p-1.5 h-[420px]"><MapView points={[]} territories={data?.items ?? []}
          center={data?.items.find((t) => t.kind === "radius") ? [data.items.find((t) => t.kind === "radius")!.data.lat, data.items.find((t) => t.kind === "radius")!.data.lng] : undefined} /></div>
        <div className="space-y-3">
          {data?.items.map((t) => (
            <div key={t.id} className="card p-4 flex items-center gap-3">
              <span className="h-10 w-10 rounded-xl bg-wing-soft grid place-items-center text-violet"><Radar size={18} /></span>
              <div className="min-w-0 flex-1"><div className="font-semibold truncate">{t.name}</div>
                <div className="text-xs text-ink2 capitalize">{t.kind}{t.exclusive ? " · exclusive" : ""}</div></div>
              <button className="btn-ghost btn-sm" onClick={() => remove(t)} aria-label="Remove"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </div>
      <div className="card p-5">
        <div className="kicker mb-3">Data coverage by county</div>
        <div className="space-y-3">
          {data?.coverage.map((c) => {
            const meta = COVERAGE[c.coverage] ?? COVERAGE.none;
            return (
              <div key={c.fips}>
                <div className="flex justify-between text-sm"><span className="font-medium">{c.name}</span><span className="text-ink2">{meta.label} · {c.sources.filter((s) => s.status === "active").length} sources</span></div>
                <div className="h-2 mt-1 rounded-full bg-line/10 overflow-hidden"><div className={`h-full rounded-full ${meta.tone}`} style={{ width: `${meta.pct}%` }} /></div>
                <div className="mt-1 flex flex-wrap gap-1">{c.sources.filter((s) => s.status === "active").map((s) => <span key={s.id} className="text-[11px] text-ink2 bg-surface2/70 rounded px-1.5">{s.name}</span>)}</div>
              </div>
            );
          })}
        </div>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Add an area">
        <AreaPicker maxMiles={me?.plan.max_radius_miles ?? 40} onChange={setChoice} />
        {error && <div className="text-sm text-bad mt-3">{error}</div>}
        <button className="btn-primary w-full mt-4" disabled={!choice} onClick={add}>Add area</button>
      </Modal>
    </div>
  );
}
