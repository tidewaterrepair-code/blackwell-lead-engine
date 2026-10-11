import { motion } from "framer-motion";
import {
  ArrowLeft, Bookmark, Bot, CalendarClock, Check, Copy, ExternalLink, Gauge, Lock, MapPin, Phone, PhoneOff, Send, Sparkles, Trophy, X,
} from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Skeleton } from "../components/Empty";
import { MapView } from "../components/MapView";
import { Modal } from "../components/Modal";
import { ScoreRing } from "../components/ScoreRing";
import { TagChip } from "../components/TagChip";
import { api } from "../lib/api";
import { celebrate } from "../lib/confetti";
import { ago, money, pct, shortDate, windowLabel } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Brief, LeadDetail } from "../lib/types";
import { DealAnalyzer } from "./Deals";

const ACTIONS = [
  { status: "saved", label: "Save", icon: Bookmark },
  { status: "contacted", label: "Contacted", icon: Phone },
  { status: "quoted", label: "Quoted", icon: Send },
  { status: "won", label: "Won", icon: Trophy },
  { status: "lost", label: "Lost", icon: X },
];

export default function LeadPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast, refreshMe, hasFeature, setUpgrade, me } = useApp();
  const { data: lead, setData, reload } = useFetch<LeadDetail>(`/api/leads/${id}`, [id]);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [briefBusy, setBriefBusy] = useState(false);
  const [note, setNote] = useState("");
  const [wonOpen, setWonOpen] = useState(false);
  const [wonValue, setWonValue] = useState("");
  const [analyze, setAnalyze] = useState(false);
  const [tracing, setTracing] = useState(false);

  if (!lead) return <div className="space-y-3"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;
  const s = lead.signal;
  const p = lead.property;
  const shownBrief = brief ?? lead.brief ?? null;

  const setStatus = async (status: string, value_won?: number) => {
    const r = await api<{ celebrate: boolean; badges: string[]; xp: number }>(`/api/leads/${lead.id}`, {
      method: "PATCH", body: { status, value_won } });
    if (r.celebrate) { celebrate(); toast({ title: "Job won! 🎉", body: "+100 XP. Nice work.", tone: "gold", icon: "🏆" }); }
    r.badges.forEach((b) => toast({ title: `Badge unlocked: ${b}`, tone: "gold", icon: "🏅" }));
    setData({ ...lead, status, status_label: status[0].toUpperCase() + status.slice(1) });
    refreshMe();
    reload();
  };

  const getBrief = async () => {
    setBriefBusy(true);
    try { setBrief(await api<Brief>(`/api/leads/${lead.id}/brief`, { method: "POST" })); }
    finally { setBriefBusy(false); }
  };

  const addNote = async (kind = "note") => {
    if (!note.trim()) return;
    await api(`/api/leads/${lead.id}/notes`, { body: { body: note, kind } });
    setNote("");
    reload();
  };

  const skipTrace = async () => {
    setTracing(true);
    try {
      await api(`/api/leads/${lead.id}/skiptrace`, { method: "POST" });
      toast({ title: "Owner contact unlocked", body: "1 credit used", tone: "good", icon: "📇" });
      refreshMe();
      reload();
    } catch (e: any) {
      toast({ title: e.message ?? "Lookup failed", tone: "bad" });
    } finally { setTracing(false); }
  };

  const setFollowUp = async (date: string) => {
    await api(`/api/leads/${lead.id}`, { method: "PATCH", body: { follow_up_at: date ? new Date(date).toISOString() : null } });
    toast({ title: "Follow-up set", tone: "good", icon: "⏰" });
  };

  const mapsUrl = s?.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.address} ${s.city ?? ""} ${s.state ?? ""}`)}` : null;

  return (
    <div className="space-y-4">
      <button className="btn-ghost btn-sm" onClick={() => navigate(-1)}><ArrowLeft size={14} />Back</button>

      <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5 sm:p-6">
        <div className="flex gap-5 items-start">
          <ScoreRing score={lead.score} size={76} locked={lead.locked} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap gap-1.5 mb-2">
              {s && <TagChip tag={lead.prediction?.tag ?? s.tag} label={lead.prediction?.tag_label ?? s.tag_label} size="md" />}
              {lead.type === "prediction" && <span className="chip border-violet/50"><Sparkles size={12} className="text-violet" />Predicted job</span>}
              {s && <span className="chip">{s.kind_label}</span>}
              {lead.trade_label && <span className="chip">For {lead.trade_label}</span>}
            </div>
            <h1 className="font-display text-2xl sm:text-3xl font-bold leading-tight">{s?.title}</h1>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink2">
              {s?.address && <span className="inline-flex items-center gap-1"><MapPin size={14} />{s.address}{s.city ? `, ${s.city}` : ""}</span>}
              {s?.value ? <span className="font-semibold text-ink">{money(s.value, false)}</span> : null}
              <span>{ago(s?.posted_at)}</span>
              {mapsUrl && <a className="text-violet inline-flex items-center gap-1" href={mapsUrl} target="_blank" rel="noreferrer">Map<ExternalLink size={12} /></a>}
              {s?.url && <a className="text-violet inline-flex items-center gap-1" href={s.url} target="_blank" rel="noreferrer">Original record<ExternalLink size={12} /></a>}
            </div>
            {lead.reasons.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{lead.reasons.map((r) => <span key={r} className="chip">{r}</span>)}</div>}
          </div>
        </div>
        {lead.locked ? (
          <button className="btn-gold mt-5" onClick={() => setUpgrade({ feature: "predictions" })}><Lock size={16} />Unlock predicted jobs</button>
        ) : (
          <div className="mt-5 flex flex-wrap gap-2">
            {ACTIONS.map(({ status, label, icon: Icon }) => (
              <button key={status} onClick={() => (status === "won" ? setWonOpen(true) : setStatus(status))}
                      className={`btn-sm ${lead.status === status ? "btn-primary" : "btn-ghost"}`}><Icon size={14} />{label}</button>
            ))}
            <label className="btn-ghost btn-sm cursor-pointer"><CalendarClock size={14} />Follow up
              <input type="date" className="bg-transparent outline-none text-xs" onChange={(e) => setFollowUp(e.target.value)}
                     defaultValue={lead.follow_up_at?.slice(0, 10)} /></label>
          </div>
        )}
      </motion.section>

      <div className="grid lg:grid-cols-[1fr_340px] gap-4">
        <div className="space-y-4 min-w-0">
          {lead.prediction && !lead.locked && (
            <section className="card p-5 bg-wing-soft">
              <div className="kicker">Why Pegasus predicts this</div>
              <div className="mt-2 font-semibold">{lead.prediction.reason}</div>
              <div className="mt-2 text-sm text-ink2">{windowLabel(lead.prediction.window_start, lead.prediction.window_end)} · {pct(lead.prediction.probability)} likely</div>
            </section>
          )}

          <section className="card p-5">
            <div className="flex items-center justify-between">
              <div className="kicker flex items-center gap-1.5"><Bot size={12} />Lead brief</div>
              {!shownBrief && !lead.locked && <button className="btn-primary btn-sm" onClick={getBrief} disabled={briefBusy}>
                <Sparkles size={14} />{briefBusy ? "Writing…" : hasFeature("ai_briefs") ? "Write with AI" : "Write brief"}</button>}
            </div>
            {shownBrief ? (
              <div className="mt-3 space-y-3 text-sm">
                <p>{shownBrief.summary}</p>
                <p className="text-ink2"><b className="text-ink">Why now:</b> {shownBrief.why_now}</p>
                <div className="rounded-xl bg-surface2/70 p-3">
                  <div className="flex items-center justify-between mb-1"><span className="label">Opener</span>
                    <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(shownBrief.opener); toast({ title: "Copied", tone: "good" }); }}><Copy size={12} />Copy</button></div>
                  <p>{shownBrief.opener}</p>
                </div>
                <ul className="space-y-1">{shownBrief.talking_points.map((t) => <li key={t} className="flex gap-2"><Check size={16} className="text-good shrink-0" />{t}</li>)}</ul>
                {shownBrief.source === "template" && !hasFeature("ai_briefs") && <p className="text-xs text-muted">AI-written briefs are included in Growth.</p>}
              </div>
            ) : <p className="text-sm text-ink2 mt-2">A one-minute read on this lead, plus an opener you can send.</p>}
          </section>

          {s?.description && (
            <section className="card p-5">
              <div className="kicker">Details</div>
              <p className="mt-2 text-sm whitespace-pre-line">{s.description}</p>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {[["Permit type", s.permit_type], ["Contractor", s.contractor], ["Owner", s.owner_name], ["Contact", s.contact_name],
                  ["Phone", s.phone], ["Email", s.email], ["Due", shortDate(s.due_at)]].filter(([, v]) => v).map(([k, v]) => (
                  <div key={k as string}><dt className="text-ink2 text-xs">{k}</dt><dd className="font-medium break-words">{v as string}</dd></div>
                ))}
              </dl>
            </section>
          )}

          {(lead.next_jobs?.length ?? 0) > 0 && (
            <section className="card p-5">
              <div className="kicker">What happens next at this address</div>
              <ol className="mt-3 relative border-l border-line/15 ml-2 space-y-4">
                {lead.next_jobs!.slice(0, 12).map((j) => (
                  <li key={j.trade + j.tag_label} className="ml-4">
                    <span className={`absolute -left-[7px] mt-1 h-3.5 w-3.5 rounded-full ${j.yours ? "bg-gold ring-4 ring-gold/20" : "bg-violet/60"}`} />
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-sm">{j.trade_label}</span>
                      {j.yours && <span className="chip border-gold/60 text-gold text-[10px]">Your trade</span>}
                      <span className="text-xs text-ink2">{windowLabel(j.window_start, j.window_end)} · {pct(j.probability)}</span>
                    </div>
                    <div className="text-xs text-ink2 mt-0.5">{j.reason}</div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {(lead.history?.length ?? 0) > 0 && (
            <section className="card p-5">
              <div className="kicker">The property's story</div>
              <ul className="mt-3 space-y-2">
                {lead.history!.map((h) => (
                  <li key={h.id} className="flex items-center gap-2 text-sm">
                    <TagChip tag={h.tag} label={h.tag_label} /><span className="truncate">{h.title}</span>
                    <span className="ml-auto text-xs text-muted shrink-0">{ago(h.posted_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="card p-5">
            <div className="kicker">Notes & activity</div>
            <div className="mt-3 flex gap-2">
              <input className="input" placeholder="Called, left voicemail… / Quoted $18,500…" value={note}
                     onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addNote()} />
              <button className="btn-primary" onClick={() => addNote()}>Add</button>
            </div>
            <ul className="mt-4 space-y-3">
              {lead.activities.map((a) => (
                <li key={a.id} className="text-sm"><span className="text-xs text-muted">{ago(a.created_at)} · {a.kind}</span><div>{a.body}</div></li>
              ))}
              {lead.activities.length === 0 && <li className="text-sm text-ink2">No activity yet.</li>}
            </ul>
          </section>
        </div>

        <div className="space-y-4">
          {s?.lat && s?.lng && !lead.locked && (
            <div className="card p-1.5 h-56"><MapView points={[{ id: lead.id, lat: s.lat, lng: s.lng, score: lead.score, tag: s.tag, title: s.title }]} /></div>
          )}

          {p && (
            <section className="card p-5">
              <div className="kicker flex items-center gap-1.5"><Gauge size={12} />Property intelligence</div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div><div className="text-xs text-ink2">Motivation</div><div className="font-display text-2xl font-bold">{p.motivation}</div>
                  <div className="h-1.5 mt-1 rounded-full bg-line/10"><div className="h-full rounded-full bg-gold" style={{ width: `${p.motivation}%` }} /></div></div>
                <div><div className="text-xs text-ink2">Likely to sell (12 mo)</div>
                  <div className="font-display text-2xl font-bold">{hasFeature("likely_to_sell") ? pct(p.sell_probability) : <Lock size={18} className="inline" />}</div></div>
                {p.est_value ? <div><div className="text-xs text-ink2">Est. value</div><div className="font-semibold">{money(p.est_value)}</div></div> : null}
                {p.equity_est ? <div><div className="text-xs text-ink2">Est. equity</div><div className="font-semibold">{money(p.equity_est)}</div></div> : null}
                {p.year_built ? <div><div className="text-xs text-ink2">Built</div><div className="font-semibold">{p.year_built}</div></div> : null}
                {p.sqft ? <div><div className="text-xs text-ink2">Size</div><div className="font-semibold">{p.sqft.toLocaleString()} sqft</div></div> : null}
              </div>
              {p.factors.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{p.factors.map((f) => <span key={f} className="chip">{f}</span>)}</div>}
              {me?.org.mode !== "trades" && (
                <button className="btn-ghost w-full mt-4" onClick={() => hasFeature("deal_analyzer") ? setAnalyze(true) : setUpgrade({ feature: "deal_analyzer" })}>
                  Analyze deal (ARV · MAO)</button>
              )}
            </section>
          )}

          {!lead.locked && s?.address && (
            <section className="card p-5">
              <div className="kicker">Owner contact</div>
              {lead.contacts && lead.contacts.length > 0 ? lead.contacts.map((c) => (
                <div key={c.id} className="mt-3 space-y-2 text-sm">
                  {c.name && <div className="font-semibold">{c.name}</div>}
                  {c.phones.map((ph) => (
                    <div key={ph.number} className="flex items-center gap-2">
                      {ph.dnc || ph.litigator ? <PhoneOff size={14} className="text-bad" /> : <Phone size={14} className="text-good" />}
                      {ph.dnc || ph.litigator ? <span className="line-through text-muted">{ph.number}</span> : <a href={`tel:${ph.number}`} className="font-medium">{ph.number}</a>}
                      <span className="text-xs text-muted">{ph.type}</span>
                      {(ph.dnc || ph.litigator) && <span className="chip border-bad/50 text-bad text-[10px]">{ph.litigator ? "Litigator: don't call" : "Do not call"}</span>}
                    </div>
                  ))}
                  {c.emails.map((em) => <a key={em} href={`mailto:${em}`} className="block text-violet">{em}</a>)}
                </div>
              )) : (
                <>
                  <p className="text-sm text-ink2 mt-2">Get the owner's phone and email. Numbers on the Do Not Call list are flagged so you stay compliant.</p>
                  <button className="btn-primary w-full mt-3" disabled={tracing} onClick={() => hasFeature("contacts") ? skipTrace() : setUpgrade({ feature: "contacts" })}>
                    {tracing ? "Looking up…" : "Unlock contact · 1 credit"}</button>
                </>
              )}
            </section>
          )}
        </div>
      </div>

      <Modal open={wonOpen} onClose={() => setWonOpen(false)} title="🏆 You won the job!">
        <label className="block"><span className="label">Job value (for your stats and goal)</span>
          <input className="input mt-1" inputMode="decimal" placeholder="$18,500" value={wonValue} onChange={(e) => setWonValue(e.target.value)} /></label>
        <button className="btn-gold w-full mt-4" onClick={() => { setWonOpen(false); setStatus("won", Number(wonValue.replace(/[^0-9.]/g, "")) || undefined); }}>
          <Trophy size={16} />Mark as won</button>
      </Modal>
      {p && <Modal open={analyze} onClose={() => setAnalyze(false)} title="Deal analyzer" wide><DealAnalyzer propertyId={p.id} /></Modal>}
    </div>
  );
}
