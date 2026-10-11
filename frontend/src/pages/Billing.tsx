import { Check, Coins, Copy, Crown, Gift, MapPinned, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { ago, money } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";

export default function Billing() {
  const { me, toast } = useApp();
  const { data } = useFetch<any>("/api/billing");
  const [annual, setAnnual] = useState(false);
  const status = new URLSearchParams(location.search).get("status");
  if (!me || !data) return <div className="skeleton h-80" />;

  const checkout = async (item: string, quantity = 1) => {
    try {
      const r = await api<{ url: string }>("/api/billing/checkout", { body: { item, interval: annual ? "annual" : "monthly", quantity } });
      location.href = r.url;
    } catch (e: any) { toast({ title: e.message, tone: "bad" }); }
  };
  const portal = async () => {
    try { location.href = (await api<{ url: string }>("/api/billing/portal", { method: "POST" })).url; }
    catch (e: any) { toast({ title: e.message, tone: "bad" }); }
  };

  return (
    <div className="space-y-6">
      {status === "success" && <div className="card p-4 border-good/50 text-good font-semibold">🎉 You're all set. Welcome aboard!</div>}
      <div className="flex flex-wrap items-end gap-3">
        <div><h1 className="font-display text-2xl font-bold">Plan & credits</h1>
          <p className="text-sm text-ink2">You're on <b className="text-ink">{me.plan.label}</b>{me.org.plan_status === "trialing" ? " (trial)" : ""}.
            {data.founding_member && <span className="ml-2 chip border-gold/60 text-gold"><Crown size={12} />Founding member: 40% off for life</span>}</p></div>
        <div className="ml-auto flex items-center gap-2">
          <span className={`text-sm ${!annual ? "font-semibold" : "text-ink2"}`}>Monthly</span>
          <button onClick={() => setAnnual(!annual)} className={`relative h-7 w-12 rounded-full transition ${annual ? "bg-wing" : "bg-surface2"}`} aria-label="Toggle annual billing">
            <span className={`absolute top-1 h-5 w-5 rounded-full bg-white transition ${annual ? "left-6" : "left-1"}`} /></button>
          <span className={`text-sm ${annual ? "font-semibold" : "text-ink2"}`}>Annual <span className="text-good">2 months free</span></span>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {data.catalog.filter((p: any) => p.key !== "free").map((p: any) => {
          const current = me.org.plan === p.key && me.org.plan_status === "active";
          const popular = p.key === "growth";
          const price = annual ? Math.round(p.annual / 12) : p.monthly;
          const founding = data.founding_member ? Math.round(price * 0.6) : null;
          return (
            <div key={p.key} className={`card p-5 flex flex-col ${popular ? "ring-2 ring-brand shadow-glow" : ""}`}>
              {popular && <span className="chip chip-active self-start mb-2"><Sparkles size={12} />Most popular</span>}
              <div className="font-display text-xl font-bold">{p.label}</div>
              <div className="text-xs text-ink2">{p.tagline}</div>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="font-display text-4xl font-bold">${founding ?? price}</span><span className="text-ink2 text-sm">/mo</span>
                {founding !== null && <span className="text-sm text-muted line-through">${price}</span>}
              </div>
              <ul className="mt-4 space-y-2 text-sm flex-1">
                {p.highlights.map((h: string) => <li key={h} className="flex gap-2"><Check size={16} className="text-good shrink-0 mt-0.5" />{h}</li>)}
              </ul>
              <button className={`${popular ? "btn-primary" : "btn-ghost"} mt-5`} disabled={current} onClick={() => checkout(p.key)}>
                {current ? "Current plan" : me.org.has_billing ? "Switch" : "Choose " + p.label}</button>
            </div>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-3 gap-3">
        <div className="card p-5">
          <div className="kicker flex items-center gap-1.5"><Coins size={12} />Contact credits</div>
          <div className="font-display text-4xl font-bold mt-1">{data.credits}</div>
          <p className="text-sm text-ink2">1 credit = 1 owner contact lookup (phone + email, DNC-flagged).</p>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {Object.entries(data.addons.credit_packs).map(([k, v]: any) => (
              <button key={k} className="btn-ghost flex-col py-3" onClick={() => checkout(k)}>
                <span className="font-bold">{v.credits}</span><span className="text-xs text-ink2">${v.price}</span></button>
            ))}
          </div>
        </div>
        <div className="card p-5">
          <div className="kicker flex items-center gap-1.5"><MapPinned size={12} />Add-ons</div>
          <div className="mt-3 space-y-3 text-sm">
            <div className="flex items-center gap-3"><div className="flex-1"><b>Extra area</b><div className="text-ink2 text-xs">One more county or radius</div></div>
              <button className="btn-ghost btn-sm" onClick={() => checkout("territory_addon")}>${data.addons.territory}/mo</button></div>
            <div className="flex items-center gap-3"><div className="flex-1"><b>Exclusive ZIP</b><div className="text-ink2 text-xs">Only you get leads in that ZIP for your trade</div></div>
              <button className="btn-gold btn-sm" onClick={() => checkout("exclusive_zip")}>${data.addons.exclusive_zip}/mo</button></div>
          </div>
          {me.org.has_billing && <button className="btn-ghost w-full mt-4" onClick={portal}>Manage billing & invoices</button>}
        </div>
        <div className="card p-5 bg-wing-soft">
          <div className="kicker flex items-center gap-1.5"><Gift size={12} />Refer & earn 30% for life</div>
          <p className="text-sm mt-1">Share your link. You earn 30% of every payment from everyone you refer, every month.</p>
          <div className="mt-3 flex gap-2"><input className="input text-xs" readOnly value={data.referral.url} />
            <button className="btn-primary btn-sm" onClick={() => { navigator.clipboard.writeText(data.referral.url); toast({ title: "Link copied", tone: "good" }); }}><Copy size={14} /></button></div>
          <div className="mt-3 grid grid-cols-3 text-center">
            <div><div className="font-display text-xl font-bold">{data.referral.signups}</div><div className="text-[11px] text-ink2">signups</div></div>
            <div><div className="font-display text-xl font-bold">{data.referral.paying}</div><div className="text-[11px] text-ink2">paying</div></div>
            <div><div className="font-display text-xl font-bold text-good">{money(data.referral.earned_cents / 100)}</div><div className="text-[11px] text-ink2">earned</div></div>
          </div>
        </div>
      </div>

      {data.ledger.length > 0 && (
        <div className="card p-5"><div className="kicker mb-2">Credit history</div>
          <table className="w-full text-sm"><tbody>{data.ledger.map((l: any, i: number) => (
            <tr key={i} className="border-t border-line/10"><td className="py-2 capitalize">{l.reason.replace("_", " ")}</td>
              <td className={`tabular-nums ${l.delta > 0 ? "text-good" : ""}`}>{l.delta > 0 ? "+" : ""}{l.delta}</td>
              <td className="tabular-nums text-ink2">bal {l.balance}</td><td className="text-right text-ink2">{ago(l.at)}</td></tr>))}</tbody></table></div>
      )}
      {!data.billing_enabled && <p className="text-xs text-muted">Payments aren't switched on for this server yet (STRIPE_SECRET_KEY).</p>}
    </div>
  );
}
