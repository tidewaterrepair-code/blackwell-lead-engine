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
        brand: v("brand"),
        ember: v("ember"),
        onbrand: v("onbrand"),
        gold: v("gold"),
        good: v("good"),
        bad: v("bad"),
      },
      fontFamily: {
        display: ['"Oswald Variable"', '"Arial Narrow"', "system-ui", "sans-serif"],
        brand: ["Cinzel", "Georgia", "serif"],
        sans: ['"Inter Variable"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: { xl2: "1.25rem" },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--brand) / 0.4), 0 8px 30px -8px rgb(var(--ember) / 0.45)",
        card: "0 1px 0 rgb(255 255 255 / 0.04) inset, 0 10px 30px -18px rgb(0 0 0 / 0.6)",
      },
      backgroundImage: {
        wing: "linear-gradient(180deg, #FFE3A3 0%, #E2B25A 55%, #B9802F 100%)",
        "wing-soft": "linear-gradient(135deg, rgb(var(--brand) / 0.16) 0%, rgb(var(--ember) / 0.08) 100%)",
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
