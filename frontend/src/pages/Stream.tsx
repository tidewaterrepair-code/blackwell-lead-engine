import { AnimatePresence, motion } from "framer-motion";
import { Bell, Flame, Share2, Sparkles, Sun, Trophy, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Empty, Skeleton } from "../components/Empty";
import { LeadCard } from "../components/LeadCard";
import { GoalRing } from "../components/Meters";
import { TagChip } from "../components/TagChip";
import { api, qs } from "../lib/api";
import { celebrate } from "../lib/confetti";
import { money, plural } from "../lib/format";
import { useCountdown, useFetch, useHotkeys, useLeadStream } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Lead, Stats } from "../lib/types";

const TABS = [
  { key: "all", label: "For you", params: { status: "new" } },
  { key: "predicted", label: "Predicted", params: { status: "open", type: "prediction" } },
  { key: "saved", label: "Saved", params: { status: "saved" } },
  { key: "hot", label: "🔥 Hot", params: { status: "new", min_score: 75 } },
] as const;

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function Stream() {
  const { me, toast, refreshMe, setUpgrade } = useApp();
  const navigate = useNavigate();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("all");
  const [tag, setTag] = useState<string | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [next, setNext] = useState<number | null>(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState(0);
  const [freshIds, setFreshIds] = useState<Set<number>>(new Set());
  const { data: stats, reload: reloadStats } = useFetch<Stats>("/api/stats");
  const { data: recap } = useFetch<any>("/api/recap");
  const sentinel = useRef<HTMLDivElement>(null);
  const countdown = useCountdown(stats?.next_drop_at);

  const load = useCallback(async (offset: number, replace = false) => {
    const params = TABS.find((t) => t.key === tab)!.params;
    setLoading(true);
    try {
      const r = await api<{ items: Lead[]; total: number; next: number | null }>(
        `/api/leads${qs({ ...params, tag, offset, limit: 20 })}`);
      setLeads((cur) => (replace ? r.items : [...cur, ...r.items.filter((x) => !cur.some((c) => c.id === x.id))]));
      setNext(r.next);
      setTotal(r.total);
    } finally {
      setLoading(false);
    }
  }, [tab, tag]);

  useEffect(() => { setCursor(0); load(0, true); }, [load]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && next !== null && !loading) load(next);
    }, { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [next, loading, load]);

  useLeadStream((lead: Lead) => {
    if (tab !== "all") return;
    setLeads((cur) => (cur.some((c) => c.id === lead.id) ? cur : [lead, ...cur]));
    setFreshIds((s) => new Set(s).add(lead.id));
    toast({ title: `New lead · ${lead.signal?.tag_label ?? "Lead"}`, body: lead.signal?.title ?? undefined,
            icon: "⚡", tone: lead.score >= 75 ? "gold" : "info" });
    reloadStats();
  });

  const act = async (lead: Lead, status: "saved" | "passed") => {
    if (lead.locked) { setUpgrade({ feature: "predictions" }); return; }
    setLeads((cur) => cur.filter((l) => l.id !== lead.id));
    try {
      const r = await api<{ badges: string[]; xp: number }>(`/api/leads/${lead.id}`, { method: "PATCH", body: { status } });
      if (status === "saved") toast({ title: "Saved to pipeline", body: "+2 XP", tone: "good", icon: "📌" });
      r.badges.forEach((b) => { celebrate(); toast({ title: `Badge unlocked: ${b}`, tone: "gold", icon: "🏅" }); });
      refreshMe();
      reloadStats();
    } catch {
      load(0, true);
    }
  };

  useHotkeys({
    j: () => setCursor((c) => Math.min(c + 1, leads.length - 1)),
    k: () => setCursor((c) => Math.max(c - 1, 0)),
    s: () => leads[cursor] && act(leads[cursor], "saved"),
    p: () => leads[cursor] && act(leads[cursor], "passed"),
    enter: () => leads[cursor] && navigate(`/leads/${leads[cursor].id}`),
  });

  const shareRecap = async () => {
    const text = `${recap?.share_text} ${location.origin}${recap?.share_url}`;
    try {
      if (navigator.share) await navigator.share({ text });
      else await navigator.clipboard.writeText(text);
      const r = await api<{ awarded: number }>("/api/recap/share", { method: "POST" });
      toast({ title: r.awarded ? `+${r.awarded} credits for sharing!` : "Recap shared", tone: "gold", icon: "🎁" });
      refreshMe();
    } catch { /* share cancelled */ }
  };

  if (!me) return null;
  const xpToNext = me.user.level.next ? me.user.level.next - me.user.xp : 0;
  const goal = me.org.settings?.monthly_goal as number | undefined;

  return (
    <div className="grid lg:grid-cols-[1fr_300px] gap-6">
      <div className="min-w-0 space-y-4">
        <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                        className="card relative overflow-hidden p-5 sm:p-6">
          <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-wing opacity-20 blur-3xl" />
          <div className="relative flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="kicker flex items-center gap-1.5"><Sun size={12} />Morning Drop</div>
              <h1 className="font-display text-2xl sm:text-3xl font-bold mt-1">
                {greeting()}, {me.user.name?.split(" ")[0] ?? "boss"}. <span className="gradient-text">{plural(stats?.new_24h ?? 0, "new lead")}</span>
              </h1>
              <p className="text-ink2 text-sm mt-1">
                {countdown ? <>Next drop in <span className="font-semibold text-ink tabular-nums">
                  {countdown.h}h {String(countdown.m).padStart(2, "0")}m {String(countdown.s).padStart(2, "0")}s</span></> : null}
                {me.plan.lead_delay_days > 0 && <> · Free plan leads arrive {me.plan.lead_delay_days} days late</>}
              </p>
            </div>
            <div className="grid grid-cols-4 gap-2 w-full sm:w-auto">
              {[{ l: "Hot", v: stats?.hot, I: Flame, c: "text-gold" }, { l: "Predicted", v: stats?.predicted, I: Sparkles, c: "text-violet" },
                { l: "Follow-ups", v: stats?.follow_ups_due, I: Bell, c: "text-cyan" },
                { l: "Pipeline", v: money(stats?.pipeline_value ?? 0), I: Trophy, c: "text-good" }].map(({ l, v, I, c }) => (
                <div key={l} className="rounded-xl bg-surface2/60 px-3 py-2 min-w-[72px]">
                  <div className="flex items-center gap-1 text-[11px] text-ink2"><I size={12} className={c} />{l}</div>
                  <div className="font-display text-xl font-bold tabular-nums">{v ?? "–"}</div>
                </div>
              ))}
            </div>
          </div>
        </motion.section>

        <div className="flex gap-2 overflow-x-auto scrollbar-none -mx-4 px-4 sm:mx-0 sm:px-0">
          {TABS.map((t) => (
            <button key={t.key} className={`chip text-sm py-1.5 ${tab === t.key ? "chip-active" : ""}`} onClick={() => setTab(t.key)}>{t.label}</button>
          ))}
          <span className="w-px bg-line/10 mx-1" />
          {(stats?.radar ?? []).map((r) => (
            <button key={r.tag} onClick={() => setTag(tag === r.tag ? null : r.tag)} className={tag === r.tag ? "rounded-full ring-2 ring-violet" : ""}>
              <TagChip tag={r.tag} label={`${r.label} · ${r.count}`} />
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between text-xs text-ink2">
          <span>{plural(total, "lead")} · swipe right to save, left to pass</span>
          <span className="hidden sm:inline">Keys: J/K move · S save · P pass · Enter open</span>
        </div>

        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {leads.map((lead, i) => (
              <div key={lead.id} className={freshIds.has(lead.id) ? "rounded-2xl ring-2 ring-gold/60" : ""}>
                <LeadCard lead={lead} active={i === cursor} onOpen={() => navigate(`/leads/${lead.id}`)}
                          onSave={() => act(lead, "saved")} onPass={() => act(lead, "passed")}
                          onUnlock={() => setUpgrade({ feature: "predictions" })} />
              </div>
            ))}
          </AnimatePresence>
          {loading && leads.length === 0 && [0, 1, 2].map((i) => <Skeleton key={i} className="h-32" />)}
          {!loading && leads.length === 0 && (
            <Empty title={tab === "saved" ? "Nothing saved yet" : "You're all caught up"}
                   body={tab === "all" ? "New leads land here as Pegasus finds them. Add another area or trade to widen your radar."
                     : "Swipe right on leads you like to save them here."}
                   action={<button className="btn-primary" onClick={() => navigate("/areas")}>Widen my radar</button>} />
          )}
          <div ref={sentinel} />
        </div>
      </div>

      <aside className="space-y-4">
        <div className="card p-5">
          <div className="kicker">Your level</div>
          <div className="flex items-center gap-3 mt-2">
            <div className="font-display text-4xl font-bold gradient-text">{me.user.level.level}</div>
            <div className="flex-1">
              <div className="h-2 rounded-full bg-line/10 overflow-hidden"><div className="h-full bg-gold" style={{ width: `${me.user.level.progress * 100}%` }} /></div>
              <div className="text-xs text-ink2 mt-1">{xpToNext ? `${xpToNext} XP to level ${me.user.level.level + 1}` : "Max level!"}</div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <Flame size={16} className="text-gold" fill="currentColor" />
            <span><b>{me.user.streak}-day</b> streak. Come back tomorrow to keep it.</span>
          </div>
        </div>

        <div className="card p-5 text-center">
          <div className="kicker text-left">Won this month</div>
          <div className="relative mx-auto w-fit my-2">
            <GoalRing value={stats?.won_this_month ?? 0} goal={goal ?? 50000} />
            <div className="absolute inset-0 grid place-items-center">
              <div><div className="font-display text-xl font-bold">{money(stats?.won_this_month ?? 0)}</div>
                <div className="text-[11px] text-ink2">of {money(goal ?? 50000)} goal</div></div>
            </div>
          </div>
        </div>

        {recap && (
          <div className="card p-5 bg-wing-soft">
            <div className="kicker flex items-center gap-1.5"><Zap size={12} />This week</div>
            <div className="font-display text-2xl font-bold mt-1">{money(recap.value_found)} in jobs found</div>
            <div className="text-sm text-ink2">{plural(recap.leads, "lead")} · {recap.predicted} predicted</div>
            <button className="btn-primary w-full mt-4" onClick={shareRecap}><Share2 size={16} />Share & earn 5 credits</button>
          </div>
        )}
      </aside>
    </div>
  );
}
