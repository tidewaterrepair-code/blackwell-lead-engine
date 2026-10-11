import { AnimatePresence, motion } from "framer-motion";
import { useApp } from "../lib/store";

const TONES = {
  good: "border-good/40", gold: "border-gold/60 shadow-[0_0_30px_-8px_rgba(255,194,75,0.6)]", bad: "border-bad/50",
  info: "border-brand/40",
};

export function Toaster() {
  const { toasts, dismiss } = useApp();
  return (
    <div className="fixed z-[3000] top-3 right-3 left-3 sm:left-auto sm:w-96 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.button key={t.id} layout onClick={() => dismiss(t.id)}
                         initial={{ opacity: 0, y: -16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                         exit={{ opacity: 0, x: 40 }}
                         className={`card pointer-events-auto text-left px-4 py-3 border ${TONES[t.tone ?? "info"]}`}>
            <div className="flex gap-3 items-start">
              {t.icon && <span className="text-xl leading-none">{t.icon}</span>}
              <div>
                <div className="font-semibold text-sm">{t.title}</div>
                {t.body && <div className="text-xs text-ink2 mt-0.5">{t.body}</div>}
              </div>
            </div>
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}
