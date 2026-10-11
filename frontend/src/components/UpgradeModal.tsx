import { Check, Crown } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../lib/store";
import { Modal } from "./Modal";

const FEATURE_COPY: Record<string, string> = {
  predictions: "See jobs before they're permitted: Pegasus forecasts the next trade at every new build, sale and storm.",
  ai_briefs: "AI lead briefs and ready-to-send openers for every lead.",
  deal_analyzer: "Run ARV, repairs and max offer on any property in seconds.",
  mls: "Connect your MLS and merge your listings with public data.",
  market_reports: "Branded market reports for your farm, ready to send.",
  csv_export: "Export your leads to CSV.",
  contacts: "Unlock owner phone numbers and emails.",
};

export function UpgradeModal() {
  const { upgrade, setUpgrade, catalog, me } = useApp();
  const navigate = useNavigate();
  const target = catalog?.plans.find((p) => upgrade?.feature && p.features.includes(upgrade.feature) && p.monthly > 0);
  return (
    <Modal open={!!upgrade} onClose={() => setUpgrade(null)}
           title={<span className="inline-flex items-center gap-2"><Crown className="text-gold" size={20} />Unlock more with {target?.label ?? "an upgrade"}</span>}>
      <p className="text-ink2 text-sm">{FEATURE_COPY[upgrade?.feature ?? ""] ?? upgrade?.message ?? "That's part of a higher plan."}</p>
      {target && (
        <div className="mt-4 rounded-xl bg-wing-soft p-4 border border-brand/25">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-3xl font-bold">${me?.org.founding_member ? target.founding_monthly : target.monthly}</span>
            <span className="text-ink2 text-sm">/ month</span>
            {me?.org.founding_member && <span className="chip border-gold/60 text-gold">Founding price, locked for life</span>}
          </div>
          <ul className="mt-3 space-y-1.5 text-sm">
            {target.highlights.map((h) => <li key={h} className="flex gap-2"><Check size={16} className="text-good shrink-0 mt-0.5" />{h}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-5 flex gap-2 justify-end">
        <button className="btn-ghost" onClick={() => setUpgrade(null)}>Not now</button>
        <button className="btn-primary" onClick={() => { setUpgrade(null); navigate("/billing"); }}>See plans</button>
      </div>
    </Modal>
  );
}
