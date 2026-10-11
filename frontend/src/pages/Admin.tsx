import { Check, Gauge, Play, Radar, X } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { ago, money } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";

function Bars({ data, unit = "" }: { data: [string, number][]; unit?: string }) {
  const max = Math.max(1, ...data.map(([, v]) => v));
  return (
    <div className="space-y-2">
      {data.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[110px_1fr_48px] items-center gap-2 text-sm" title={`${k}: ${v}${unit}`}>
          <span className="truncate text-ink2">{k}</span>
          <div className="h-3 rounded-r bg-line/5"><div className="h-full rounded-r bg-[rgb(var(--brand))]" style={{ width: `${(v / max) * 100}%` }} /></div>
          <span className="tabular-nums text-right">{v}{unit}</span>
        </div>
      ))}
    </div>
  );
}

export default function Admin() {
  const { me, toast } = useApp();
  const ov = useFetch<any>("/api/admin/overview");
  const src = useFetch<any>("/api/admin/sources");
  const scout = useFetch<any>("/api/admin/scout");
  const [fips, setFips] = useState("");
  if (!me?.user.is_admin) return null;
  const o = ov.data;

  const setStatus = async (id: string, status: string) => { await api(`/api/admin/sources/${id}`, { method: "PATCH", body: { status } }); src.reload(); };
  const run = async (id: string) => { await api(`/api/admin/sources/${id}/run`, { method: "POST" }); toast({ title: "Queued", tone: "good" }); };
  const doScout = async () => { await api("/api/admin/scout", { body: { fips } }); toast({ title: `Scouting ${fips}`, tone: "good" }); setFips(""); scout.reload(); };

  return (
    <div className="space-y-5">
      <h1 className="font-display text-2xl font-bold flex items-center gap-2"><Gauge />Mission Control</h1>
      {o && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {[["MRR", money(o.mrr, false)], ["ARR", money(o.arr)], ["Paying", o.customers.paying], ["Trialing", o.customers.trialing],
              ["Churned (30d)", o.customers.churned_30d]].map(([k, v]) => (
              <div key={k as string} className="card p-4"><div className="text-xs text-ink2">{k}</div><div className="font-display text-3xl font-bold">{v}</div></div>
            ))}
          </div>
          <div className="grid lg:grid-cols-3 gap-3">
            <div className="card p-5"><div className="kicker mb-3">Signup funnel (30 days)</div>
              <Bars data={[["Signed up", o.funnel_30d.signups], ["Set an area", o.funnel_30d.set_area], ["Worked a lead", o.funnel_30d.worked_a_lead], ["Paying", o.funnel_30d.paying]]} /></div>
            <div className="card p-5"><div className="kicker mb-3">Signups by source (30 days)</div>
              <Bars data={Object.entries(o.signups_by_source_30d) as [string, number][]} /></div>
            <div className="card p-5 space-y-1 text-sm"><div className="kicker mb-2">Data engine</div>
              <div>Signals: <b>{o.data.signals_24h}</b> today · <b>{o.data.signals_7d}</b> this week</div>
              <div>Leads delivered (7d): <b>{o.data.leads_7d}</b></div>
              <div>Revenue (30d): <b>{money(o.revenue_30d, false)}</b> · Founding members: <b>{o.customers.founding_members}</b></div>
              <div>Counties: {Object.entries(o.data.jurisdictions).map(([k, v]) => `${v} ${k}`).join(" · ")}</div>
              <div>Jobs: {Object.entries(o.jobs).map(([k, v]) => `${v} ${k}`).join(" · ") || "idle"}</div>
              <div>Waitlist: <b>{o.waitlist}</b></div></div>
          </div>
        </>
      )}

      <div className="card p-5">
        <div className="flex items-center gap-2 mb-3"><div className="kicker flex items-center gap-1.5"><Radar size={12} />Source Scout</div>
          <input className="input w-40 ml-auto py-1.5" placeholder="County FIPS" value={fips} onChange={(e) => setFips(e.target.value)} />
          <button className="btn-primary btn-sm" onClick={doScout} disabled={fips.length !== 5}>Scout</button></div>
        <ul className="space-y-1 text-sm">{scout.data?.items.slice(0, 8).map((j: any) => (
          <li key={j.id} className="flex gap-3"><span className="chip">{j.status}</span><span>{j.jurisdiction}</span>
            <span className="text-ink2 truncate">{(j.log ?? []).slice(-1)[0]}</span><span className="ml-auto text-muted">{ago(j.created_at)}</span></li>))}</ul>
      </div>

      <div className="card p-5 overflow-x-auto">
        <div className="kicker mb-3">Sources</div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-ink2"><th className="py-2">Source</th><th>Kind</th><th>Status</th><th>Confidence</th><th>Last run</th><th>New</th><th /></tr></thead>
          <tbody>{src.data?.items.map((s: any) => (
            <tr key={s.id} className="border-t border-line/10 align-top">
              <td className="py-2"><div className="font-medium">{s.name}</div><div className="text-xs text-muted">{s.id} · {s.type}</div>
                {s.status === "pending_review" && s.sample && <div className="mt-1 text-xs text-ink2">{s.sample.slice(0, 2).map((x: any) => x.title).join(" · ")}</div>}
                {s.last_error && <div className="text-xs text-bad mt-1 line-clamp-2">{s.last_error}</div>}</td>
              <td>{s.kind}</td><td><span className="chip">{s.status}</span></td>
              <td className="tabular-nums">{s.confidence ?? "–"}</td><td className="text-ink2">{s.last_run_at ? `${s.last_status} ${ago(s.last_run_at)}` : "never"}</td>
              <td className="tabular-nums">{s.last_new}</td>
              <td className="whitespace-nowrap text-right">
                {s.status !== "active" && <button className="btn-ghost btn-sm" title="Approve" onClick={() => setStatus(s.id, "active")}><Check size={14} /></button>}
                {s.status === "active" && <button className="btn-ghost btn-sm" title="Run now" onClick={() => run(s.id)}><Play size={14} /></button>}
                {s.status !== "disabled" && <button className="btn-ghost btn-sm" title="Disable" onClick={() => setStatus(s.id, "disabled")}><X size={14} /></button>}
              </td></tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}
