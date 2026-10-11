import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Toaster } from "./components/Toaster";
import { UpgradeModal } from "./components/UpgradeModal";
import { PegasusMark } from "./components/Logo";
import { AppProvider, useApp } from "./lib/store";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { Stream } from "./pages/Stream";

const LeadPage = lazy(() => import("./pages/LeadPage"));
const MapPage = lazy(() => import("./pages/MapPage"));
const Pipeline = lazy(() => import("./pages/Pipeline"));
const Deals = lazy(() => import("./pages/Deals"));
const Areas = lazy(() => import("./pages/Areas"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const Billing = lazy(() => import("./pages/Billing"));
const Admin = lazy(() => import("./pages/Admin"));

function Splash() {
  return <div className="min-h-screen grid place-items-center"><PegasusMark size={56} className="animate-floaty" /></div>;
}

function Private({ children }: { children: ReactNode }) {
  const { me, loading } = useApp();
  const location = useLocation();
  if (loading) return <Splash />;
  if (!me) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (!me.org.settings?.onboarded && location.pathname !== "/welcome") return <Navigate to="/welcome" replace />;
  return <Shell><Suspense fallback={<div className="skeleton h-40" />}>{children}</Suspense></Shell>;
}

export function App() {
  return (
    <AppProvider>
      <BrowserRouter basename="/app">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/join" element={<Signup invite />} />
          <Route path="/welcome" element={<Signup onboardingOnly />} />
          <Route path="/" element={<Private><Stream /></Private>} />
          <Route path="/leads/:id" element={<Private><LeadPage /></Private>} />
          <Route path="/map" element={<Private><MapPage /></Private>} />
          <Route path="/pipeline" element={<Private><Pipeline /></Private>} />
          <Route path="/deals" element={<Private><Deals /></Private>} />
          <Route path="/areas" element={<Private><Areas /></Private>} />
          <Route path="/settings" element={<Private><SettingsPage /></Private>} />
          <Route path="/billing" element={<Private><Billing /></Private>} />
          <Route path="/admin" element={<Private><Admin /></Private>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <UpgradeModal />
        <Toaster />
      </BrowserRouter>
    </AppProvider>
  );
}
