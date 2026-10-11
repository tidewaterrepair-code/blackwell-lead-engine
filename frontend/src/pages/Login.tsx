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
        <a href="/"><Logo /></a>
        <div className="flex-1 grid place-items-center py-10"><div className="w-full max-w-md">{children}</div></div>
      </div>
      <div className="hidden lg:flex relative overflow-hidden items-center justify-center bg-wing-soft border-l border-line/10">
        <div className="absolute h-[620px] w-[620px] rounded-full border border-violet/20" />
        <div className="absolute h-[420px] w-[420px] rounded-full border border-cyan/20" />
        <div className="absolute h-[620px] w-[620px] rounded-full animate-sweep"
             style={{ background: "conic-gradient(from 0deg, transparent 0deg, rgb(var(--violet) / 0.25) 40deg, transparent 70deg)" }} />
        <div className="relative max-w-sm p-8">{aside}</div>
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
      <div className="kicker mb-3">Pegasus</div>
      <div className="font-display text-4xl font-bold leading-tight">See the job <span className="gradient-text">before</span> your competition does.</div>
      <p className="mt-4 text-ink2">Permits, bids, sales, storms and distressed properties: scored, predicted and delivered to you every morning.</p>
    </div>}>
      <h1 className="font-display text-3xl font-bold">Welcome back</h1>
      <p className="text-ink2 mt-1 mb-6">Your leads are waiting.</p>
      {sent ? (
        <div className="card p-5 text-center">
          <Mail className="mx-auto text-violet" />
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
      <p className="text-sm text-ink2 mt-6 text-center">New to Pegasus? <Link to="/signup" className="text-violet font-semibold">Start free</Link></p>
    </AuthFrame>
  );
}
