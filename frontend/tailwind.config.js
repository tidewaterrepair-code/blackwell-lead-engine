/** Pegasus design system: colors come from CSS variables so light/dark swap in one place. */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        page: v("page"),
        surface: v("surface"),
        surface2: v("surface-2"),
        line: v("line"),
        ink: v("ink"),
        ink2: v("ink-2"),
        muted: v("muted"),
        violet: v("violet"),
        cyan: v("cyan"),
        gold: v("gold"),
        good: v("good"),
        bad: v("bad"),
      },
      fontFamily: {
        display: ['"Space Grotesk Variable"', "system-ui", "sans-serif"],
        sans: ['"Inter Variable"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: { xl2: "1.25rem" },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--violet) / 0.35), 0 8px 30px -8px rgb(var(--violet) / 0.45)",
        card: "0 1px 0 rgb(255 255 255 / 0.04) inset, 0 10px 30px -18px rgb(0 0 0 / 0.6)",
      },
      backgroundImage: {
        wing: "linear-gradient(135deg, rgb(var(--violet)) 0%, rgb(var(--cyan)) 100%)",
        "wing-soft": "linear-gradient(135deg, rgb(var(--violet) / 0.18) 0%, rgb(var(--cyan) / 0.12) 100%)",
      },
      keyframes: {
        pulsering: { "0%": { transform: "scale(0.6)", opacity: "0.9" }, "100%": { transform: "scale(2.6)", opacity: "0" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
        sweep: { "0%": { transform: "rotate(0deg)" }, "100%": { transform: "rotate(360deg)" } },
        floaty: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
      },
      animation: {
        pulsering: "pulsering 1.8s ease-out infinite",
        shimmer: "shimmer 1.4s linear infinite",
        sweep: "sweep 3s linear infinite",
        floaty: "floaty 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
