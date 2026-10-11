import { FAMILIES, familyColor, tagMeta } from "../lib/tags";

export function TagChip({ tag, label, size = "sm" }: { tag: string; label: string; size?: "sm" | "md" }) {
  const { family, Icon } = tagMeta(tag);
  const color = familyColor(family);
  return (
    <span className={`chip ${size === "md" ? "text-sm px-3 py-1.5" : ""}`} title={FAMILIES[family].label}>
      <span className="grid place-items-center rounded-full" style={{ background: color, width: 16, height: 16 }}>
        <Icon size={10} color="#fff" strokeWidth={2.6} />
      </span>
      <span className="text-ink">{label}</span>
    </span>
  );
}

export function FamilyLegend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink2">
      {(Object.keys(FAMILIES) as (keyof typeof FAMILIES)[]).map((f) => (
        <span key={f} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: familyColor(f) }} />
          {FAMILIES[f].label}
        </span>
      ))}
    </div>
  );
}
