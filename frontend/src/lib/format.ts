export const money = (v: number | null | undefined, compact = true) => {
  if (v === null || v === undefined) return "";
  if (compact && v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (compact && v >= 10_000) return `$${Math.round(v / 1000)}k`;
  return `$${Math.round(v).toLocaleString()}`;
};

export const ago = (iso: string | null | undefined) => {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 0) {
    const d = Math.round(-diff / 86400);
    return d <= 0 ? "today" : d === 1 ? "tomorrow" : `in ${d} days`;
  }
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  const d = Math.floor(diff / 86400);
  if (d === 1) return "yesterday";
  if (d < 45) return `${d}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
};

export const shortDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";

export const windowLabel = (start: string, end: string) => {
  const s = new Date(start).getTime(), e = new Date(end).getTime(), now = Date.now();
  if (now >= s && now <= e) return `Now → ${shortDate(end)}`;
  const weeks = Math.round((s - now) / (7 * 86400e3));
  if (weeks <= 1) return `Next week → ${shortDate(end)}`;
  if (weeks < 9) return `In ${weeks} weeks`;
  return `${shortDate(start)} → ${shortDate(end)}`;
};

export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
