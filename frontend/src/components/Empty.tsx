import type { ReactNode } from "react";
import { PegasusMark } from "./Logo";

export function Empty({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card p-10 text-center flex flex-col items-center gap-3">
      <PegasusMark size={64} className="animate-floaty" />
      <div className="font-display text-lg font-bold">{title}</div>
      {body && <div className="text-sm text-ink2 max-w-md">{body}</div>}
      {action}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}
