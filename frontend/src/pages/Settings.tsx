import { Award, Bell, Building, Database, Lock, UserPlus, Users } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { ago } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";
import { TRADE_ICONS } from "../lib/tags";

const BADGES = [
  ["first_contact", "First contact"], ["closer", "Closer: first win"], ["hat_trick", "Hat trick"], ["hustler", "Hustler: 25 contacts"],
  ["streak_7", "7-day streak"], ["streak_30", "30-day streak"], ["six_figures", "$100k won"],
];

export default function Settings() {
  const { me, catalog, refreshMe, toast, hasFeature, setUpgrade } = useApp();
  const team = useFetch<any>("/api/team");
  const mls = useFetch<any>(hasFeature("mls") ? "/api/mls" : null);
  const [profile, setProfile] = useState({ name: me?.user.name ?? "", phone: me?.user.phone ?? "" });
  const [company, setCompany] = useState({ name: me?.org.name ?? "", goal: String(me?.org.settings?.monthly_goal ?? "") });
  const [trades, setTrades] = useState<string[]>(me?.org.trades ?? []);
  const [alerts, setAlerts] = useState({ digest: me?.org.settings?.digest !== false, min: me?.org.settings?.alerts_min_score ?? 75,
                                         topic: me?.org.settings?.ntfy_topic ?? "" });
  const [inviteEmail, setInviteEmail] = useState("");
  const [mlsForm, setMlsForm] = useState({ mls_name: "", base_url: "", token_url: "", client_id: "", secret: "", vendor: "reso" });
  if (!me) return null;
  const isAdmin = me.org.role !== "member";

  const save = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); await refreshMe(); toast({ title: `${label} saved`, tone: "good" }); }
    catch (e: any) { toast({ title: e.message, tone: "bad" }); }
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="font-display text-2xl font-bold">Team & settings</h1>

      <section className="card p-5 space-y-3">
        <div className="kicker flex items-center gap-1.5"><Award size={12} />Badges · {me.user.xp} XP · level {me.user.level.level}</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {BADGES.map(([k, l]) => {
            const on = me.user.badges.includes(k);
            return <div key={k} className={`rounded-xl p-3 text-center text-xs font-semibold border ${on ? "border-gold/60 bg-gold/10" : "border-line/10 opacity-50"}`}>
              <div className="text-2xl">{on ? "🏅" : "🔒"}</div>{l}</div>;
          })}
        </div>
      </section>

      <section className="card p-5 space-y-3">
        <div className="kicker">Your profile</div>
        <div className="grid sm:grid-cols-2 gap-3">
          <label><span className="label">Name</span><input className="input mt-1" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} /></label>
          <label><span className="label">Phone</span><input className="input mt-1" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} /></label>
        </div>
        <button className="btn-primary" onClick={() => save("Profile", () => api("/api/me", { method: "PATCH", body: profile }))}>Save profile</button>
      </section>

      {isAdmin && (
        <section className="card p-5 space-y-3">
          <div className="kicker flex items-center gap-1.5"><Building size={12} />Company & trades</div>
          <div className="grid sm:grid-cols-2 gap-3">
            <label><span className="label">Company name</span><input className="input mt-1" value={company.name} onChange={(e) => setCompany({ ...company, name: e.target.value })} /></label>
            <label><span className="label">Monthly revenue goal ($)</span><input className="input mt-1" inputMode="numeric" value={company.goal} onChange={(e) => setCompany({ ...company, goal: e.target.value })} /></label>
          </div>
          <div className="label">Trades ({trades.length}/{me.plan.trades})</div>
          <div className="flex flex-wrap gap-2">
            {catalog?.trades.map((t) => {
              const Icon = TRADE_ICONS[t.icon];
              const on = trades.includes(t.key);
              return <button key={t.key} className={`chip ${on ? "chip-active" : ""}`}
                             onClick={() => setTrades(on ? trades.filter((x) => x !== t.key) : [...trades, t.key])}>{Icon && <Icon size={12} />}{t.label}</button>;
            })}
          </div>
          <button className="btn-primary" onClick={() => save("Company", () => api("/api/org", { method: "PATCH", body: {
            name: company.name, trades, settings: { monthly_goal: company.goal ? +company.goal : null } } }))}>Save company</button>
        </section>
      )}

      <section className="card p-5 space-y-3">
        <div className="kicker flex items-center gap-1.5"><Bell size={12} />Alerts</div>
        <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={alerts.digest} onChange={(e) => setAlerts({ ...alerts, digest: e.target.checked })} className="accent-[rgb(var(--brand))] h-4 w-4" />
          Morning Drop email at {me.digest_hour}:00</label>
        <div><div className="flex justify-between text-xs text-ink2"><span>Instant phone alert for leads scoring</span><span className="font-semibold text-ink">{alerts.min}+</span></div>
          <input type="range" min={50} max={95} value={alerts.min} onChange={(e) => setAlerts({ ...alerts, min: +e.target.value })} className="w-full accent-[rgb(var(--brand))]" /></div>
        <label className="block"><span className="label">Phone alerts: your ntfy topic (free ntfy app, iOS/Android)</span>
          <input className="input mt-1" placeholder="pegasus-yourname-7k2" value={alerts.topic} onChange={(e) => setAlerts({ ...alerts, topic: e.target.value.replace(/[^\w-]/g, "") })} /></label>
        <p className="text-xs text-muted">Install ntfy, subscribe to the same topic name, and hot leads will buzz your phone.</p>
        <button className="btn-primary" onClick={() => save("Alerts", () => api("/api/org", { method: "PATCH", body: { settings: {
          digest: alerts.digest, alerts_min_score: alerts.min, ntfy_topic: alerts.topic } } }))}>Save alerts</button>
      </section>

      <section className="card p-5 space-y-3">
        <div className="kicker flex items-center gap-1.5"><Users size={12} />Team · {team.data?.seats.used ?? 1}/{team.data?.seats.limit ?? me.plan.seats} seats</div>
        <ul className="divide-y divide-line/10">
          {team.data?.members.map((m: any) => <li key={m.id} className="py-2 flex items-center gap-3 text-sm">
            <span className="h-8 w-8 rounded-full bg-wing grid place-items-center text-onbrand font-bold">{(m.name ?? m.email)[0].toUpperCase()}</span>
            <span className="flex-1">{m.name ?? m.email}<span className="block text-xs text-muted">{m.email}</span></span>
            <span className="chip capitalize">{m.role}</span><span className="text-xs text-ink2">{m.xp} XP · 🔥{m.streak}</span></li>)}
          {team.data?.invites.map((i: any) => <li key={i.id} className="py-2 text-sm text-ink2">{i.email} · invited {ago(i.created_at)}</li>)}
        </ul>
        {isAdmin && <div className="flex gap-2">
          <input className="input" type="email" placeholder="crew@yourcompany.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
          <button className="btn-primary" onClick={() => save("Invite", async () => { await api("/api/team/invite", { body: { email: inviteEmail } }); setInviteEmail(""); team.reload(); })}><UserPlus size={16} />Invite</button>
        </div>}
      </section>

      <section className="card p-5 space-y-3">
        <div className="kicker flex items-center gap-1.5"><Database size={12} />MLS connect</div>
        {!hasFeature("mls") ? (
          <button className="btn-gold" onClick={() => setUpgrade({ feature: "mls" })}><Lock size={14} />Connect your MLS with Agent Elite</button>
        ) : (
          <>
            <p className="text-sm text-ink2">Ask your MLS's data vendor (Trestle, Bridge, Spark, MLS Grid…) for a RESO Web API feed naming Pegasus as your technology provider, then paste the credentials. Your listing data stays private to your team. No feed yet? Upload an MLS CSV export instead.</p>
            {mls.data?.items.map((c: any) => <div key={c.id} className="text-sm flex items-center gap-2"><span className="chip">{c.status}</span>{c.mls_name} · {c.listings} listings
              {c.last_error && <span className="text-bad text-xs">{c.last_error}</span>}
              <label className="btn-ghost btn-sm ml-auto cursor-pointer">Upload CSV<input type="file" accept=".csv" hidden onChange={async (e) => {
                const f = e.target.files?.[0]; if (!f) return; const form = new FormData(); form.append("file", f);
                const r = await api<any>(`/api/mls/${c.id}/import`, { form }); toast({ title: `Imported ${r.created + r.updated} listings`, tone: "good" }); mls.reload(); }} /></label></div>)}
            <div className="grid sm:grid-cols-2 gap-3">
              <label><span className="label">MLS name</span><input className="input mt-1" value={mlsForm.mls_name} onChange={(e) => setMlsForm({ ...mlsForm, mls_name: e.target.value })} /></label>
              <label><span className="label">Connection</span><select className="input mt-1" value={mlsForm.vendor} onChange={(e) => setMlsForm({ ...mlsForm, vendor: e.target.value })}>
                <option value="reso">RESO Web API</option><option value="csv">CSV uploads only</option></select></label>
              {mlsForm.vendor === "reso" && <>
                <label><span className="label">API base URL</span><input className="input mt-1" placeholder="https://api.vendor.com/odata" value={mlsForm.base_url} onChange={(e) => setMlsForm({ ...mlsForm, base_url: e.target.value })} /></label>
                <label><span className="label">Token URL (OAuth)</span><input className="input mt-1" value={mlsForm.token_url} onChange={(e) => setMlsForm({ ...mlsForm, token_url: e.target.value })} /></label>
                <label><span className="label">Client ID</span><input className="input mt-1" value={mlsForm.client_id} onChange={(e) => setMlsForm({ ...mlsForm, client_id: e.target.value })} /></label>
                <label><span className="label">Client secret or token</span><input className="input mt-1" type="password" value={mlsForm.secret} onChange={(e) => setMlsForm({ ...mlsForm, secret: e.target.value })} /></label>
              </>}
            </div>
            <button className="btn-primary" onClick={() => save("MLS connection", async () => { await api("/api/mls", { body: mlsForm }); mls.reload(); })}>Connect</button>
          </>
        )}
      </section>
    </div>
  );
}
