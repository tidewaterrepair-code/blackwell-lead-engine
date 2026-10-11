import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ScoreRing } from "../components/ScoreRing";
import { TagChip } from "../components/TagChip";
import { api } from "../lib/api";
import { celebrate } from "../lib/confetti";
import { ago, money } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Lead } from "../lib/types";

const COLUMNS = [
  { key: "saved", label: "Saved", tone: "bg-brand" }, { key: "contacted", label: "Contacted", tone: "bg-ember" },
  { key: "quoted", label: "Quoted", tone: "bg-gold" }, { key: "won", label: "Won", tone: "bg-good" },
  { key: "lost", label: "Lost", tone: "bg-muted" },
];

export default function Pipeline() {
  const navigate = useNavigate();
  const { toast, refreshMe } = useApp();
  const { data, reload } = useFetch<{ items: Lead[] }>("/api/leads?status=pipeline&sort=newest&limit=100");
  const [dragId, setDragId] = useState<number | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const leads = (data?.items ?? []).filter((l) => l.status !== "new" && l.status !== "passed");

  const move = async (lead: Lead, status: string) => {
    if (lead.status === status) return;
    const r = await api<{ celebrate: boolean; badges: string[] }>(`/api/leads/${lead.id}`, { method: "PATCH", body: { status } });
    if (r.celebrate) { celebrate(); toast({ title: "Job won! 🎉", tone: "gold", icon: "🏆" }); }
    r.badges.forEach((b) => toast({ title: `Badge unlocked: ${b}`, tone: "gold", icon: "🏅" }));
    refreshMe();
    reload();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div><h1 className="font-display text-2xl font-bold">Pipeline</h1><p className="text-sm text-ink2">Drag cards between stages.</p></div>
        <div className="text-right"><div className="kicker">Won</div>
          <div className="font-display text-2xl font-bold text-good">{money(leads.filter((l) => l.status === "won").reduce((a, l) => a + (l.value_won ?? 0), 0))}</div></div>
      </div>
      <div className="grid grid-flow-col auto-cols-[minmax(260px,1fr)] gap-3 overflow-x-auto pb-4 -mx-4 px-4 lg:mx-0 lg:px-0">
        {COLUMNS.map((col) => {
          const items = leads.filter((l) => l.status === col.key);
          return (
            <div key={col.key} onDragOver={(e) => { e.preventDefault(); setOver(col.key); }} onDragLeave={() => setOver(null)}
                 onDrop={() => { const l = leads.find((x) => x.id === dragId); setOver(null); if (l) move(l, col.key); }}
                 className={`rounded-2xl p-3 min-h-[60vh] transition ${over === col.key ? "bg-wing-soft ring-2 ring-brand/50" : "bg-surface2/40"}`}>
              <div className="flex items-center gap-2 mb-3 px-1">
                <span className={`h-2.5 w-2.5 rounded-full ${col.tone}`} />
                <span className="font-semibold text-sm">{col.label}</span>
                <span className="ml-auto text-xs text-muted">{items.length}</span>
              </div>
              <div className="space-y-2">
                {items.map((l) => (
                  <div key={l.id} draggable onDragStart={() => setDragId(l.id)} onClick={() => navigate(`/leads/${l.id}`)}
                       className="card card-hover p-3 cursor-grab active:cursor-grabbing">
                    <div className="flex gap-3">
                      <ScoreRing score={l.score} size={38} />
                      <div className="min-w-0">
                        <div className="text-sm font-semibold line-clamp-2">{l.signal?.title}</div>
                        <div className="mt-1 flex items-center gap-2"><TagChip tag={l.prediction?.tag ?? l.signal?.tag ?? ""} label={l.prediction?.tag_label ?? l.signal?.tag_label ?? ""} /></div>
                        <div className="text-[11px] text-muted mt-1">{l.value_won ? money(l.value_won) : money(l.signal?.value)} · {ago(l.created_at)}</div>
                      </div>
                    </div>
                    <select className="input mt-2 py-1 text-xs lg:hidden" value={l.status} onClick={(e) => e.stopPropagation()}
                            onChange={(e) => move(l, e.target.value)}>
                      {COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
