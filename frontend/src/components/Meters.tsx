import { Flame } from "lucide-react";

export function LevelRing({ level, progress, size = 36 }: { level: number; progress: number; size?: number }) {
  const r = (size - 4) / 2, c = 2 * Math.PI * r;
  return (
    <div className="relative" style={{ width: size, height: size }} title={`Level ${level}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--line) / 0.12)" strokeWidth={3} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--gold))" strokeWidth={3} strokeLinecap="round"
                strokeDasharray={c} strokeDashoffset={c * (1 - progress)} style={{ transition: "stroke-dashoffset .8s" }} />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[11px] font-bold">{level}</span>
    </div>
  );
}

export function Streak({ days }: { days: number }) {
  const lit = days >= 2;
  return (
    <span className={`chip ${lit ? "border-gold/50" : ""}`} title={`${days}-day streak: open Pegasus daily to keep it`}>
      <Flame size={14} className={lit ? "text-gold animate-floaty" : "text-muted"} fill={lit ? "currentColor" : "none"} />
      <span className="font-bold tabular-nums">{days}</span>
    </span>
  );
}

export function GoalRing({ value, goal, size = 120 }: { value: number; goal: number; size?: number }) {
  const r = (size - 12) / 2, c = 2 * Math.PI * r, p = Math.min(1, goal ? value / goal : 0);
  return (
    <svg width={size} height={size} className="-rotate-90" role="img" aria-label={`${Math.round(p * 100)}% of goal`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--line) / 0.1)" strokeWidth={10} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--good))" strokeWidth={10} strokeLinecap="round"
              strokeDasharray={c} strokeDashoffset={c * (1 - p)} style={{ transition: "stroke-dashoffset 1s" }} />
    </svg>
  );
}
