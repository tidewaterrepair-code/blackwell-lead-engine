import { FileText, Landmark } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Empty, Skeleton } from "../components/Empty";
import { Modal } from "../components/Modal";
import { api, qs } from "../lib/api";
import { money, pct } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Lead, PropertyInfo, Territory } from "../lib/types";

const DISTRESS = ["foreclosure", "tax_delinquent", "probate", "eviction", "violation", "vacant", "absentee"];
const GRADE_TONE: Record<string, string> = { A: "text-good", B: "text-ember", C: "text-gold", D: "text-ink2", F: "text-bad" };

export function DealAnalyzer({ propertyId }: { propertyId: number }) {
  const [arv, setArv] = useState("");
  const [repairs, setRepairs] = useState("");
  const [data, setData] = useState<any>(null);
  const run = async () => setData(await api("/api/deals/analyze", { body: {
    property_id: propertyId, arv: arv ? +arv.replace(/\D/g, "") : null, repairs: repairs ? +repairs.replace(/\D/g, "") : null } }));
  useEffect(() => { run(); }, [propertyId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return <Skeleton className="h-60" />;
  const a = data.analysis;
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-4 gap-3">
        {[["ARV", money(a.arv)], ["Repairs", money(a.repairs)], ["Max offer (70%)", money(a.mao)], ["Grade", a.grade]].map(([k, v]) => (
          <div key={k} className="rounded-xl bg-surface2/60 p-3"><div className="text-xs text-ink2">{k}</div>
            <div className={`font-display text-2xl font-bold ${k === "Grade" ? GRADE_TONE[a.grade] : ""}`}>{v || "–"}</div></div>
        ))}
      </div>
      <div className="text-sm text-ink2">ARV method: {a.arv_method}. {a.grade_reasons.join(" · ")}</div>
      <div className="grid sm:grid-cols-2 gap-3">
        <label><span className="label">Your ARV</span><input className="input mt-1" placeholder={money(a.arv, false)} value={arv} onChange={(e) => setArv(e.target.value)} /></label>
        <label><span className="label">Your repair estimate</span><input className="input mt-1" placeholder={money(a.repairs, false)} value={repairs} onChange={(e) => setRepairs(e.target.value)} /></label>
      </div>
      <button className="btn-primary" onClick={run}>Recalculate</button>
      {a.comps.length > 0 && (
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-ink2"><th className="py-2">Comp</th><th>Price</th><th>Sqft</th><th>Sold</th><th>Miles</th></tr></thead>
          <tbody>{a.comps.map((c: any, i: number) => (
            <tr key={i} className="border-t border-line/10"><td className="py-2">{c.address}{c.source === "mls" ? " · MLS" : ""}</td>
              <td className="tabular-nums">{money(c.price)}</td><td className="tabular-nums">{c.sqft ?? "–"}</td><td>{c.sold_on}</td><td className="tabular-nums">{c.miles}</td></tr>
          ))}</tbody></table></div>
      )}
    </div>
  );
}

export default function Deals() {
  const navigate = useNavigate();
  const { hasFeature, setUpgrade } = useApp();
  const [distress, setDistress] = useState<string | null>(null);
  const [sort, setSort] = useState<"motivation" | "sell">("motivation");
  const [analyze, setAnalyze] = useState<number | null>(null);
  const [farmOpen, setFarmOpen] = useState(false);
  const { data, loading } = useFetch<{ items: { lead: Lead; property: PropertyInfo }[] }>(
    `/api/deals${qs({ distress, sort })}`, [distress, sort]);
  const { data: terr } = useFetch<{ items: Territory[] }>("/api/territories");
  const [farmId, setFarmId] = useState<number | null>(null);
  const { data: farm } = useFetch<any>(farmId ? `/api/farm/${farmId}` : null, [farmId]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div><h1 className="font-display text-2xl font-bold flex items-center gap-2"><Landmark />Deal radar</h1>
          <p className="text-sm text-ink2">Off-market owners ranked by motivation and how likely they are to sell.</p></div>
        <div className="ml-auto flex gap-2">
          <button className="btn-ghost btn-sm" onClick={() => { setFarmOpen(true); setFarmId(terr?.items[0]?.id ?? null); }}>Farm stats</button>
        </div>
      </div>
      <div className="flex gap-2 overflow-x-auto scrollbar-none">
        <button className={`chip ${!distress ? "chip-active" : ""}`} onClick={() => setDistress(null)}>All</button>
        {DISTRESS.map((d) => <button key={d} className={`chip capitalize ${distress === d ? "chip-active" : ""}`} onClick={() => setDistress(d)}>{d.replace("_", " ")}</button>)}
        <span className="w-px bg-line/10" />
        <button className={`chip ${sort === "motivation" ? "chip-active" : ""}`} onClick={() => setSort("motivation")}>Most motivated</button>
        <button className={`chip ${sort === "sell" ? "chip-active" : ""}`} onClick={() => hasFeature("likely_to_sell") ? setSort("sell") : setUpgrade({ feature: "likely_to_sell" })}>Likely to sell</button>
      </div>
      {loading && <Skeleton className="h-48" />}
      {!loading && !data?.items.length && <Empty title="No deals yet" body="Distressed and likely-to-sell properties in your areas show up here as Pegasus finds tax, foreclosure, probate, violation and sale records." />}
      <div className="grid sm:grid-cols-2 gap-3">
        {data?.items.map(({ lead, property: p }) => (
          <div key={lead.id} className="card card-hover p-4 cursor-pointer" onClick={() => navigate(`/leads/${lead.id}`)}>
            <div className="flex items-start gap-3">
              <div className="text-center"><div className="font-display text-3xl font-bold text-gold">{p.motivation}</div><div className="text-[10px] text-ink2">MOTIVATION</div></div>
              <div className="min-w-0 flex-1">
                <div className="font-semibold truncate">{p.address}</div>
                <div className="text-xs text-ink2">{[p.city, p.zip].filter(Boolean).join(" ")} · {p.year_built ? `built ${p.year_built}` : ""}</div>
                <div className="mt-2 flex flex-wrap gap-1">{p.factors.slice(0, 5).map((f) => <span key={f} className="chip text-[11px]">{f}</span>)}</div>
                <div className="mt-2 text-xs text-ink2">
                  {hasFeature("likely_to_sell") ? <>Sell chance {pct(p.sell_probability)}</> : "Sell chance 🔒"}
                  {p.equity_est ? <> · Equity ~{money(p.equity_est)}</> : null}
                </div>
              </div>
            </div>
            <button className="btn-ghost btn-sm mt-3 w-full" onClick={(e) => { e.stopPropagation(); hasFeature("deal_analyzer") ? setAnalyze(p.id) : setUpgrade({ feature: "deal_analyzer" }); }}>Analyze deal</button>
          </div>
        ))}
      </div>
      <Modal open={analyze !== null} onClose={() => setAnalyze(null)} title="Deal analyzer" wide>{analyze !== null && <DealAnalyzer propertyId={analyze} />}</Modal>
      <Modal open={farmOpen} onClose={() => setFarmOpen(false)} title="Farm stats" wide>
        <div className="flex gap-2 flex-wrap mb-4">{terr?.items.map((t) => <button key={t.id} className={`chip ${farmId === t.id ? "chip-active" : ""}`} onClick={() => setFarmId(t.id)}>{t.name}</button>)}</div>
        {farm ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[["Sales (12 mo)", farm.sales_12mo], ["Turnover", farm.turnover_rate !== null ? pct(farm.turnover_rate) : "–"],
                ["Median price", money(farm.median_sale_price)], ["Absentee owners", farm.absentee_share !== null ? pct(farm.absentee_share) : "–"]].map(([k, v]) => (
                <div key={k as string} className="rounded-xl bg-surface2/60 p-3"><div className="text-xs text-ink2">{k}</div><div className="font-display text-xl font-bold">{v ?? "–"}</div></div>
              ))}
            </div>
            <div><div className="kicker mb-2">Hottest streets</div>
              <div className="flex flex-wrap gap-1.5">{farm.hottest_streets.map((s: any) => <span key={s.street} className="chip">{s.street} · {s.activity}</span>)}</div></div>
            <a className="btn-primary" href={`/reports/market/${farmId}`} target="_blank" rel="noreferrer"
               onClick={(e) => { if (!hasFeature("market_reports")) { e.preventDefault(); setUpgrade({ feature: "market_reports" }); } }}>
              <FileText size={16} />Branded market report</a>
          </div>
        ) : <Skeleton className="h-40" />}
      </Modal>
    </div>
  );
}
