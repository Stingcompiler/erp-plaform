/** @type {import('tailwindcss').Config} */
function withAlpha(v) {
  return `rgb(var(${v}) / <alpha-value>)`;
}

module.exports = {
  content: ["./app/**/*.{js,jsx}", "./components/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: withAlpha("--ink"),
        paper: withAlpha("--paper"),
        surface: withAlpha("--surface"),
        line: withAlpha("--line"),
        muted: withAlpha("--muted"),
        accent: {
          DEFAULT: withAlpha("--accent"),
          strong: withAlpha("--accent-strong"),
        },
        ok: withAlpha("--ok"),
        warn: withAlpha("--warn"),
        danger: withAlpha("--danger"),
      },
      fontFamily: {
        // These resolve to Inter/Sora in LTR and Cairo/Tajawal in RTL — the
        // --font-body / --font-display vars are swapped by [dir="rtl"] in
        // globals.css when the language flips.
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: { card: "12px", control: "8px" },
      boxShadow: {
        card: "0 1px 2px rgba(18,37,59,0.04), 0 1px 3px rgba(18,37,59,0.06)",
      },
    },
  },
  darkMode: "class",
  plugins: [],
};
