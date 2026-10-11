import confetti from "canvas-confetti";

export function celebrate() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const colors = ["#FFE3A3", "#E2B25A", "#F08A2C", "#FFF6E0", "#B9802F"];
  confetti({ particleCount: 120, spread: 80, origin: { y: 0.7 }, colors, zIndex: 4000 });
  setTimeout(() => confetti({ particleCount: 80, angle: 60, spread: 60, origin: { x: 0 }, colors, zIndex: 4000 }), 200);
  setTimeout(() => confetti({ particleCount: 80, angle: 120, spread: 60, origin: { x: 1 }, colors, zIndex: 4000 }), 350);
}
