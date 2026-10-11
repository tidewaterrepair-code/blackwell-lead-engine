export function ScoreRing({ score, size = 52, locked = false }: { score: number; size?: number; locked?: boolean }) {
  const stroke = size > 60 ? 6 : 4.5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const hot = score >= 75;
  const id = `sr-${size}-${hot ? "h" : "n"}`;
  return (
    <div className={`relative shrink-0 ${hot ? "drop-shadow-[0_0_10px_rgba(240,138,44,0.55)]" : ""}`}
         style={{ width: size, height: size }} title={`Lead score ${score}/100`}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={hot ? "#FFE3A3" : "rgb(var(--brand) / 0.75)"} />
            <stop offset="1" stopColor={hot ? "#F08A2C" : "rgb(var(--brand))"} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--line) / 0.1)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${id})`} strokeWidth={stroke}
                strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - (locked ? 0.15 : score / 100))}
                style={{ transition: "stroke-dashoffset 900ms cubic-bezier(.2,.8,.2,1)" }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className={`font-display font-bold tabular-nums ${size > 60 ? "text-2xl" : "text-base"}`}>
          {locked ? "?" : score}
        </span>
      </div>
    </div>
  );
}
