import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Catalog, Me } from "./types";

type Toast = { id: number; title: string; body?: string; tone?: "good" | "gold" | "bad" | "info"; icon?: string };

type Ctx = {
  me: Me | null;
  catalog: Catalog | null;
  loading: boolean;
  refreshMe: () => Promise<Me | null>;
  toast: (t: Omit<Toast, "id">) => void;
  toasts: Toast[];
  dismiss: (id: number) => void;
  hasFeature: (f: string) => boolean;
  upgrade: { feature?: string; message?: string } | null;
  setUpgrade: (u: { feature?: string; message?: string } | null) => void;
  theme: "dark" | "light";
  toggleTheme: () => void;
};

const AppCtx = createContext<Ctx | null>(null);
let toastId = 1;

export function AppProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [upgrade, setUpgrade] = useState<{ feature?: string; message?: string } | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(
    document.documentElement.classList.contains("dark") ? "dark" : "light");

  const refreshMe = useCallback(async () => {
    try {
      const data = await api<Me>("/api/me");
      setMe(data);
      return data;
    } catch {
      setMe(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api<Catalog>("/api/catalog").then(setCatalog).catch(() => undefined);
    const publicPage = /^\/app\/(login|signup|join)/.test(location.pathname);
    if (publicPage) setLoading(false);
    else refreshMe();
  }, [refreshMe]);

  useEffect(() => {
    const onUpgrade = (e: Event) => setUpgrade((e as CustomEvent).detail ?? {});
    window.addEventListener("pegasus:upgrade", onUpgrade);
    return () => window.removeEventListener("pegasus:upgrade", onUpgrade);
  }, []);

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = toastId++;
    setToasts((all) => [...all.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts((all) => all.filter((x) => x.id !== id)), 4800);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((x) => x.id !== id)), []);
  const hasFeature = useCallback((f: string) => !!me?.plan.features.includes(f), [me]);
  const toggleTheme = useCallback(() => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try { localStorage.setItem("pegasus-theme", next); } catch { /* private mode */ }
    setTheme(next);
  }, [theme]);

  const value = useMemo(() => ({ me, catalog, loading, refreshMe, toast, toasts, dismiss, hasFeature, upgrade,
    setUpgrade, theme, toggleTheme }), [me, catalog, loading, refreshMe, toast, toasts, dismiss, hasFeature, upgrade,
    theme, toggleTheme]);
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp() {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}
