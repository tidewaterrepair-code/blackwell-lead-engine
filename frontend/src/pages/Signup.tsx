import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Check, HardHat, KeyRound, Radar } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AreaPicker, type AreaChoice } from "../components/AreaPicker";
import { api } from "../lib/api";
import { useApp } from "../lib/store";
import { TRADE_ICONS } from "../lib/tags";
import { AuthFrame } from "./Login";

type Step = "audience" | "trades" | "account" | "area" | "scan";

export function Signup({ invite = false, onboardingOnly = false }: { invite?: boolean; onboardingOnly?: boolean }) {
  const { catalog, refreshMe, me } = useApp();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const [step, setStep] = useState<Step>(invite ? "account" : onboardingOnly ? "area" : "audience");
  const [audience, setAudience] = useState<"trades" | "realestate">("trades");
  const [trades, setTrades] = useState<string[]>([]);
  const [form, setForm] = useState({ name: "", org_name: "", email: "", password: "" });
  const [area, setArea] = useState<AreaChoice | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<number | null>(null);

  const options = useMemo(() => (catalog?.trades ?? []).filter((t) => t.group === audience), [catalog, audience]);
  const ref = params.get("ref") ?? document.cookie.match(/pegasus_ref=([^;]+)/)?.[1] ?? undefined;
  const utm = Object.fromEntries([...params.entries()].filter(([k]) => k.startsWith("utm_") || k === "gclid" || k === "fbclid"));

  const toggle = (k: string) => setTrades((t) => t.includes(k) ? t.filter((x) => x !== k) : t.length >= 3 ? t : [...t, k]);

  const createAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/signup", { body: { ...form, trades, ref, utm, invite: invite ? params.get("invite") : undefined } });
      await refreshMe();
      if (invite) {
        await api("/api/org", { method: "PATCH", body: { settings: { onboarded: true } } }).catch(() => undefined);
        await refreshMe();
        navigate("/");
      } else setStep("area");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const saveArea = async () => {
    if (!area) return;
    setBusy(true);
    setError("");
    try {
      await api("/api/territories", { body: area });
      setStep("scan");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (step !== "scan") return;
    let stop = false;
    const poll = async (n: number) => {
      try {
        const r = await api<{ total: number }>("/api/leads?limit=1&status=all");
        if (!stop) setFound(r.total);
      } catch { /* keep scanning */ }
      if (!stop && n < 8) setTimeout(() => poll(n + 1), 1500);
    };
    poll(0);
    return () => { stop = true; };
  }, [step]);

  const finish = async () => {
    await api("/api/org", { method: "PATCH", body: { settings: { onboarded: true } } });
    await refreshMe();
    navigate("/");
  };

  const steps: Step[] = invite ? ["account"] : onboardingOnly ? ["area", "scan"] : ["audience", "trades", "account", "area", "scan"];
  const progress = (steps.indexOf(step) + 1) / steps.length;

  return (
    <AuthFrame aside={<div className="space-y-4">
      <div className="font-display text-3xl font-bold leading-tight">Every permit, sale and storm in your area. <span className="gradient-text">Ranked for you.</span></div>
      {["Leads from public records in your area, updated daily", "Predicted jobs before they're permitted",
        "AI briefs and ready-to-send openers", "14 days free. No card."].map((t) => (
        <div key={t} className="flex gap-2 text-sm"><Check size={18} className="text-good shrink-0" />{t}</div>
      ))}
    </div>}>
      <div className="h-1.5 rounded-full bg-line/10 mb-8 overflow-hidden">
        <motion.div className="h-full bg-wing" animate={{ width: `${progress * 100}%` }} />
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={step} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
          {step === "audience" && (
            <div>
              <h1 className="font-display text-3xl font-bold">What do you do?</h1>
              <p className="text-ink2 mt-1 mb-6">We'll tune your leads to it.</p>
              <div className="grid gap-3">
                {[{ k: "trades" as const, t: "I'm in the trades", d: "Builders, framers, remodelers, roofers, HVAC, plumbing, electrical, pools, landscaping and more", I: HardHat },
                  { k: "realestate" as const, t: "I'm in real estate", d: "Agents, investors and wholesalers looking for off-market and likely-to-sell homes", I: KeyRound }].map(({ k, t, d, I }) => (
                  <button key={k} onClick={() => { setAudience(k); setTrades([]); setStep("trades"); }}
                          className="card card-hover text-left p-5 flex gap-4 items-start">
                    <span className="h-12 w-12 shrink-0 rounded-2xl bg-wing grid place-items-center text-white"><I /></span>
                    <span><span className="font-display font-bold text-lg block">{t}</span><span className="text-sm text-ink2">{d}</span></span>
                  </button>
                ))}
              </div>
              <p className="text-sm text-ink2 mt-6 text-center">Already have an account? <Link to="/login" className="text-violet font-semibold">Log in</Link></p>
            </div>
          )}

          {step === "trades" && (
            <div>
              <h1 className="font-display text-3xl font-bold">Pick up to 3</h1>
              <p className="text-ink2 mt-1 mb-5">You can change these any time.</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[52vh] overflow-y-auto pr-1">
                {options.map((t) => {
                  const Icon = TRADE_ICONS[t.icon] ?? HardHat;
                  const on = trades.includes(t.key);
                  return (
                    <button key={t.key} onClick={() => toggle(t.key)}
                            className={`card p-3 text-left text-sm font-medium flex flex-col gap-2 transition ${on ? "ring-2 ring-violet shadow-glow" : "hover:border-violet/40"}`}>
                      <span className={`h-9 w-9 rounded-xl grid place-items-center ${on ? "bg-wing text-white" : "bg-surface2 text-ink2"}`}><Icon size={18} /></span>
                      {t.label}
                    </button>
                  );
                })}
              </div>
              <div className="flex gap-2 mt-5">
                <button className="btn-ghost" onClick={() => setStep("audience")}>Back</button>
                <button className="btn-primary flex-1" disabled={!trades.length} onClick={() => setStep("account")}>Continue <ArrowRight size={16} /></button>
              </div>
            </div>
          )}

          {step === "account" && (
            <form onSubmit={createAccount} className="space-y-3">
              <h1 className="font-display text-3xl font-bold">{invite ? "Join your team" : "Create your account"}</h1>
              <p className="text-ink2 mb-3">{invite ? "Set a password to get started." : "14 days of Growth, free. No credit card."}</p>
              <div className="grid sm:grid-cols-2 gap-3">
                <label><span className="label">Your name</span><input className="input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" /></label>
                {!invite && <label><span className="label">Company</span><input className="input mt-1" value={form.org_name} onChange={(e) => setForm({ ...form, org_name: e.target.value })} autoComplete="organization" /></label>}
              </div>
              <label className="block"><span className="label">Email</span><input className="input mt-1" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" /></label>
              <label className="block"><span className="label">Password (8+ characters)</span><input className="input mt-1" type="password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" /></label>
              {error && <div className="text-sm text-bad">{error}</div>}
              <button className="btn-primary w-full" disabled={busy}>{invite ? "Join team" : "Create account"} <ArrowRight size={16} /></button>
              <p className="text-xs text-muted">By continuing you agree to the <a className="underline" href="/legal/terms">Terms</a> and <a className="underline" href="/legal/privacy">Privacy Policy</a>.</p>
            </form>
          )}

          {step === "area" && (
            <div>
              <h1 className="font-display text-3xl font-bold">Where do you work?</h1>
              <p className="text-ink2 mt-1 mb-5">Pick a city, county or ZIP anywhere in the US. If we don't cover it yet, Pegasus scouts it for you.</p>
              <AreaPicker maxMiles={me?.plan.max_radius_miles ?? 40} onChange={setArea} />
              {error && <div className="text-sm text-bad mt-3">{error}</div>}
              <button className="btn-primary w-full mt-5" disabled={!area || busy} onClick={saveArea}>Start scanning <Radar size={16} /></button>
            </div>
          )}

          {step === "scan" && (
            <div className="text-center">
              <div className="relative mx-auto h-56 w-56 my-4">
                <div className="absolute inset-0 rounded-full border border-violet/30" />
                <div className="absolute inset-8 rounded-full border border-cyan/25" />
                <div className="absolute inset-16 rounded-full border border-violet/20" />
                <div className="absolute inset-0 rounded-full animate-sweep"
                     style={{ background: "conic-gradient(from 0deg, transparent 0deg, rgb(var(--violet) / 0.45) 50deg, transparent 80deg)" }} />
                {[...Array(Math.min(found ?? 0, 9))].map((_, i) => (
                  <span key={i} className="absolute h-2.5 w-2.5 rounded-full bg-gold animate-pulse"
                        style={{ left: `${20 + ((i * 37) % 60)}%`, top: `${18 + ((i * 53) % 64)}%` }} />
                ))}
              </div>
              <h1 className="font-display text-3xl font-bold">{found ? <><span className="gradient-text">{found}</span> leads found</> : "Scanning your area…"}</h1>
              <p className="text-ink2 mt-2">Permits, bids, sales and storms are scored as they come in. New areas fill in as Pegasus maps local data sources.</p>
              <button className="btn-primary w-full mt-6" onClick={finish}>Open my Lead Stream <ArrowRight size={16} /></button>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </AuthFrame>
  );
}
