import { motion, useMotionValue, useTransform, type PanInfo } from "framer-motion";
import { Bookmark, Clock, Lock, MapPin, Sparkles, X } from "lucide-react";
import { ago, money, pct, windowLabel } from "../lib/format";
import type { Lead } from "../lib/types";
import { ScoreRing } from "./ScoreRing";
import { TagChip } from "./TagChip";

type Props = {
  lead: Lead;
  active?: boolean;
  onOpen: () => void;
  onSave: () => void;
  onPass: () => void;
  onUnlock?: () => void;
};

export function LeadCard({ lead, active, onOpen, onSave, onPass, onUnlock }: Props) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 200], [-6, 6]);
  const saveOpacity = useTransform(x, [30, 120], [0, 1]);
  const passOpacity = useTransform(x, [-120, -30], [1, 0]);
  const s = lead.signal;
  const pred = lead.prediction;
  const tag = pred?.tag ?? s?.tag ?? "other";
  const tagLabel = pred?.tag_label ?? s?.tag_label ?? "Lead";

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.x > 120) onSave();
    else if (info.offset.x < -120) onPass();
  };

  return (
    <motion.article layout initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: x.get() >= 0 ? 260 : -260, transition: { duration: 0.22 } }}
                    style={{ x, rotate }} drag="x" dragConstraints={{ left: 0, right: 0 }} dragElastic={0.6}
                    onDragEnd={onDragEnd}
                    className={`card card-hover relative overflow-hidden p-4 sm:p-5 cursor-pointer touch-pan-y
                                ${active ? "ring-2 ring-violet/70" : ""}`}
                    onClick={onOpen}>
      <motion.div style={{ opacity: saveOpacity }}
                  className="pointer-events-none absolute inset-0 bg-good/15 grid place-items-start p-4">
        <span className="chip border-good/60 text-good font-bold">SAVE</span>
      </motion.div>
      <motion.div style={{ opacity: passOpacity }}
                  className="pointer-events-none absolute inset-0 bg-bad/10 grid place-items-start justify-items-end p-4">
        <span className="chip border-bad/60 text-bad font-bold">PASS</span>
      </motion.div>

      <div className="flex gap-4">
        <ScoreRing score={lead.score} locked={lead.locked} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
            <TagChip tag={tag} label={tagLabel} />
            {lead.type === "prediction" && (
              <span className="chip border-violet/50 text-ink"><Sparkles size={12} className="text-violet" />Predicted</span>
            )}
            {s?.kind && s.kind !== "permit" && lead.type !== "prediction" && <span className="chip">{s.kind_label}</span>}
            {lead.status !== "new" && <span className="chip chip-active">{lead.status_label}</span>}
          </div>
          <h3 className="font-semibold leading-snug line-clamp-2">{s?.title ?? "Lead"}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink2">
            {(s?.address || s?.city) && (
              <span className="inline-flex items-center gap-1"><MapPin size={12} />
                {s?.address ? `${s.address}${s.city && !s.address.includes(s.city) ? `, ${s.city}` : ""}` : s?.city}
              </span>
            )}
            {s?.value ? <span className="font-semibold text-ink">{money(s.value)}</span> : null}
            <span className="inline-flex items-center gap-1"><Clock size={12} />{ago(s?.posted_at ?? lead.created_at)}</span>
            {lead.trade_label && <span className="text-muted">for {lead.trade_label}</span>}
          </div>

          {pred && (
            <div className="mt-3 rounded-xl bg-wing-soft border border-violet/20 px-3 py-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold">{windowLabel(pred.window_start, pred.window_end)}</span>
                <span className="text-ink2">{pct(pred.probability)} likely</span>
              </div>
              <div className="mt-1.5 h-1.5 rounded-full bg-line/10 overflow-hidden">
                <div className="h-full rounded-full bg-wing" style={{ width: pct(pred.probability) }} />
              </div>
              {!lead.locked && <div className="mt-1.5 text-xs text-ink2 line-clamp-2">{pred.reason}</div>}
            </div>
          )}

          {lead.reasons.length > 0 && !lead.locked && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {lead.reasons.map((r) => <span key={r} className="text-[11px] text-ink2 bg-surface2/70 rounded-md px-2 py-0.5">{r}</span>)}
            </div>
          )}
        </div>

        <div className="hidden sm:flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
          <button className="btn-ghost btn-sm" onClick={onSave} title="Save (S)"><Bookmark size={14} />Save</button>
          <button className="btn-ghost btn-sm text-ink2" onClick={onPass} title="Pass (P)"><X size={14} />Pass</button>
        </div>
      </div>

      {lead.locked && (
        <div className="absolute inset-0 backdrop-blur-[3px] bg-page/40 grid place-items-center" onClick={(e) => { e.stopPropagation(); onUnlock?.(); }}>
          <button className="btn-gold"><Lock size={14} />Unlock predicted jobs</button>
        </div>
      )}
    </motion.article>
  );
}
