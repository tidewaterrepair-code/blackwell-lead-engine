import { motion } from "framer-motion";
import { useEffect } from "react";

/** Full-screen brand splash: the pack's Pegasus artwork with a slow glow and a gold progress sweep.
 *  Same look as the pre-JavaScript splash in index.html, which it removes once React is on screen. */
export function Splash({ label = "Opportunity finds you" }: { label?: string }) {
  useEffect(() => { document.getElementById("boot-splash")?.remove(); }, []);
  return (
    <motion.div className="fixed inset-0 z-[5000] grid place-items-center bg-[#050403] overflow-hidden"
                initial={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.45 } }} role="status"
                aria-label="Loading Pegasus">
      <div className="absolute inset-0"
           style={{ background: "radial-gradient(60% 50% at 50% 45%, rgba(226,178,90,0.16), transparent 70%)" }} />
      <div className="relative flex flex-col items-center px-6">
        <motion.img src="/static/brand/splash.webp" alt="Pegasus · data & lead technology" draggable={false}
                    className="w-[min(92vw,calc(70svh*1.32),1100px)] h-auto select-none"
                    initial={{ opacity: 0, scale: 0.96, filter: "brightness(0.7)" }}
                    animate={{ opacity: 1, scale: 1, filter: ["brightness(0.95)", "brightness(1.12)", "brightness(0.95)"] }}
                    transition={{ opacity: { duration: 0.5 }, scale: { duration: 0.9, ease: [0.2, 0.8, 0.2, 1] },
                                  filter: { duration: 2.6, repeat: Infinity, ease: "easeInOut" } }} />
        <div className="mt-6 h-[2px] w-48 overflow-hidden rounded-full bg-[#2a2216]">
          <motion.div className="h-full w-1/3 rounded-full"
                      style={{ background: "linear-gradient(90deg, transparent, #FFE3A3, #E2B25A, transparent)" }}
                      animate={{ x: ["-120%", "320%"] }} transition={{ duration: 1.3, repeat: Infinity, ease: "easeInOut" }} />
        </div>
        <div className="mt-4 text-[11px] uppercase tracking-[0.45em] text-[#C9B48C]">{label}</div>
      </div>
    </motion.div>
  );
}
