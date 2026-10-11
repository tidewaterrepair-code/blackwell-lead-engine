/** Pegasus mark: three swept wing feathers rising into a spark (data -> lift). */
export function PegasusMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="pg-wing" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#7C5CFF" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <path d="M8 52 C 20 50, 30 42, 38 30 L 44 34 C 36 46, 24 54, 8 52 Z" fill="url(#pg-wing)" opacity="0.55" />
      <path d="M12 42 C 22 39, 31 31, 37 20 L 44 23 C 38 35, 28 43, 12 42 Z" fill="url(#pg-wing)" opacity="0.8" />
      <path d="M18 31 C 26 28, 32 20, 35 10 L 43 12 C 40 24, 32 31, 18 31 Z" fill="url(#pg-wing)" />
      <path d="M50 8 L52.2 13.8 L58 16 L52.2 18.2 L50 24 L47.8 18.2 L42 16 L47.8 13.8 Z" fill="#FFC24B" />
    </svg>
  );
}

export function Logo({ size = 30, withWord = true }: { size?: number; withWord?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 select-none">
      <PegasusMark size={size} />
      {withWord && <span className="font-display text-lg font-bold tracking-tight">Pegasus</span>}
    </span>
  );
}
