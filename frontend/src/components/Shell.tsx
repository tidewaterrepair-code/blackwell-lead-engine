import { Coins, CreditCard, Crosshair, Gauge, Home, KanbanSquare, Landmark, LogOut, Map, Moon, Settings, SunMedium } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/store";
import { Logo } from "./Logo";
import { LevelRing, Streak } from "./Meters";

const SHORT: Record<string, string> = { "/": "Leads", "/map": "Radar", "/pipeline": "Pipeline", "/deals": "Deals",
  "/areas": "Areas", "/settings": "Settings" };

export function Shell({ children }: { children: ReactNode }) {
  const { me, theme, toggleTheme } = useApp();
  const navigate = useNavigate();
  if (!me) return null;
  const re = me.org.mode !== "trades";
  const nav = [
    { to: "/", label: "Lead Stream", icon: Home, end: true },
    { to: "/map", label: "Radar map", icon: Map },
    { to: "/pipeline", label: "Pipeline", icon: KanbanSquare },
    ...(re ? [{ to: "/deals", label: "Deal radar", icon: Landmark }] : []),
    { to: "/areas", label: "My areas", icon: Crosshair },
    { to: "/settings", label: "Team & settings", icon: Settings },
    { to: "/billing", label: "Plan & credits", icon: CreditCard },
    ...(me.user.is_admin ? [{ to: "/admin", label: "Mission Control", icon: Gauge }] : []),
  ];
  const mobile = nav.filter((n) => ["/", "/map", "/pipeline", re ? "/deals" : "/areas", "/settings"].includes(n.to));
  const trialDays = me.org.plan_status === "trialing" && me.org.trial_ends_at
    ? Math.max(0, Math.ceil((new Date(me.org.trial_ends_at).getTime() - Date.now()) / 86400e3)) : null;

  const logout = async () => { await api("/api/auth/logout", { method: "POST" }); location.href = "/app/login"; };

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 flex-col gap-1 border-r border-line/10 bg-surface/60 backdrop-blur-xl p-4">
        <div className="px-2 py-3"><Logo /></div>
        <nav className="flex flex-col gap-1 mt-2">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
                     className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition
                        ${isActive ? "bg-wing-soft text-ink shadow-glow" : "text-ink2 hover:bg-surface2/70 hover:text-ink"}`}>
              <Icon size={18} />{label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          {trialDays !== null && (
            <button onClick={() => navigate("/billing")} className="w-full text-left rounded-xl bg-wing-soft border border-brand/30 p-3">
              <div className="text-xs text-ink2">Free trial</div>
              <div className="font-semibold text-sm">{trialDays} day{trialDays === 1 ? "" : "s"} of {me.plan.label} left</div>
              <div className="text-xs text-brand mt-1">Lock in founding pricing →</div>
            </button>
          )}
          <div className="flex items-center gap-2 px-1">
            <div className="h-9 w-9 rounded-full bg-wing grid place-items-center font-bold text-onbrand">
              {(me.user.name ?? me.user.email)[0].toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{me.user.name ?? me.user.email}</div>
              <div className="truncate text-xs text-muted">{me.org.name}</div>
            </div>
            <button className="btn-ghost btn-sm" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "dark" ? <SunMedium size={14} /> : <Moon size={14} />}
            </button>
            <button className="btn-ghost btn-sm" onClick={logout} aria-label="Log out"><LogOut size={14} /></button>
          </div>
        </div>
      </aside>

      <header className="sticky top-0 z-[900] border-b border-line/10 bg-page/70 backdrop-blur-xl">
        <div className="mx-auto max-w-6xl flex items-center gap-3 px-4 h-14">
          <div className="lg:hidden"><Logo size={26} withWord={false} /></div>
          <div className="font-display font-semibold truncate">{me.org.name}</div>
          <span className="chip hidden sm:inline-flex">{me.plan.label}</span>
          <div className="ml-auto flex items-center gap-2">
            <button className="chip" onClick={() => navigate("/billing")} title="Contact credits">
              <Coins size={14} className="text-gold" /><span className="font-bold tabular-nums">{me.org.credits}</span>
            </button>
            <Streak days={me.user.streak} />
            <button onClick={() => navigate("/settings")} title={`Level ${me.user.level.level} · ${me.user.xp} XP`}>
              <LevelRing level={me.user.level.level} progress={me.user.level.progress} />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pt-5 pb-28 lg:pb-12">{children}</main>

      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-[950] border-t border-line/10 bg-surface/90 backdrop-blur-xl
                      grid grid-cols-5 pb-[env(safe-area-inset-bottom)]">
        {mobile.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end}
                   className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium
                      ${isActive ? "text-ink" : "text-muted"}`}>
            {({ isActive }) => (<>
              <span className={`grid place-items-center h-8 w-12 rounded-full ${isActive ? "bg-wing-soft" : ""}`}><Icon size={19} /></span>
              {SHORT[to] ?? label.split(" ")[0]}
            </>)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
