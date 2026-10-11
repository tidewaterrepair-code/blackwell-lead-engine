/** Pegasus brand artwork, cut from marketing/brand/source by `pegasus marketing brand`. */
const BRAND = "/static/brand";

/** The emblem alone (winged horse in the ring): compact headers, empty states. 340x342 source. */
export function PegasusMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return <img src={`${BRAND}/logo-mark.png`} alt="" aria-hidden="true" width={size} height={size}
              className={`object-contain ${className}`} draggable={false} />;
}

/** The primary logo: emblem + PEGASUS + DATA & LEAD TECHNOLOGY. Lives in the app's top corner. 476x428 source. */
export function Logo({ width = 168, className = "" }: { width?: number; className?: string }) {
  return <img src={`${BRAND}/logo.png`} alt="Pegasus · data & lead technology" width={width}
              height={Math.round(width * 428 / 476)} className={`select-none ${className}`} draggable={false} />;
}
