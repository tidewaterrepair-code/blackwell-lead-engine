import { Mail, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Logo } from "../components/Logo";
import { api } from "../lib/api";
import { useApp } from "../lib/store";

export function AuthFrame({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="flex flex-col p-6 sm:p-10">
        <a href="/" aria-label="Pegasus home" className="self-start"><Logo width={128} /></a>
        <div className="flex-1 grid place-items-center py-10"><div className="w-full max-w-md">{children}</div></div>
      </div>
      <div className="hidden lg:flex relative overflow-hidden flex-col items-center justify-center gap-6 bg-[#050403] border-l border-line/10 text-[#F6EFE2]">
        <div className="absolute inset-0"
             style={{ background: "radial-gradient(55% 45% at 50% 40%, rgba(226,178,90,0.18), transparent 70%)" }} />
        <div className="absolute h-[640px] w-[640px] rounded-full animate-sweep opacity-60"
             style={{ background: "conic-gradient(from 0deg, transparent 0deg, rgba(226,178,90,0.16) 40deg, transparent 70deg)" }} />
        <img src="/static/brand/splash.png" alt="Pegasus · data & lead technology" draggable={false}
             className="relative w-[min(36vw,560px)] h-auto select-none" />
        <div className="relative max-w-md px-8 text-center">{aside}</div>
      </div>
    </div>
  );
}

export function Login() {
  const { refreshMe } = useApp();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [magic, setMagic] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(new URLSearchParams(location.search).get("error") === "expired"
    ? "That sign-in link expired. Request a new one." : "");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (magic) {
        await api("/api/auth/magic", { body: { email } });
        setSent(true);
      } else {
        await api("/api/auth/login", { body: { email, password } });
        await refreshMe();
        navigate("/");
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame aside={<div>
      <div className="text-[11px] uppercase tracking-[0.3em] font-semibold text-[#E2B25A] mb-3">Real data. Real people. Real jobs.</div>
      <div className="font-display text-3xl font-bold leading-tight uppercase">Higher quality <span className="gold-text">leads.</span><br />
        More projects. <span className="gold-text">Bigger business.</span></div>
      <p className="mt-4 text-[#C9BAA0]">Permits, bids, sales, storms and distressed properties: scored, predicted and delivered to you every morning.</p>
    </div>}>
      <h1 className="font-display text-3xl font-bold">Welcome back</h1>
      <p className="text-ink2 mt-1 mb-6">Your leads are waiting.</p>
      {sent ? (
        <div className="card p-5 text-center">
          <Mail className="mx-auto text-brand" />
          <div className="font-semibold mt-2">Check your email</div>
          <p className="text-sm text-ink2 mt-1">If {email} has an account, a sign-in link is on its way. It works for 30 minutes.</p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <label className="block"><span className="label">Email</span>
            <input className="input mt-1" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
          {!magic && (
            <label className="block"><span className="label">Password</span>
              <input className="input mt-1" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
          )}
          {error && <div className="text-sm text-bad">{error}</div>}
          <button className="btn-primary w-full" disabled={busy}>{magic ? <><Sparkles size={16} />Email me a link</> : "Log in"}</button>
          <button type="button" className="btn-ghost w-full" onClick={() => setMagic(!magic)}>
            {magic ? "Use a password instead" : "Email me a sign-in link instead"}
          </button>
        </form>
      )}
      <p className="text-sm text-ink2 mt-6 text-center">New to Pegasus? <Link to="/signup" className="text-brand font-semibold">Start free</Link></p>
    </AuthFrame>
  );
}
