/** Tailwind v3 standalone-CLI config (no Node build step).
 *
 * Rebuild CSS after changing templates or this file:
 *   tools\tailwindcss.exe -i static_src\input.css -o billing\static\billing\css\app.css --minify
 * (CLI download: see deploy/README.md, "Frontend CSS build".)
 */
module.exports = {
  content: [
    "./billing/templates/**/*.html",
    // crispy-tailwind composes its widget classes in Python code.
    "./.venv/Lib/site-packages/crispy_tailwind/**/*.html",
    "./.venv/Lib/site-packages/crispy_tailwind/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#F6F5F1",
        ink: { DEFAULT: "#232B33", soft: "#5C6670" },
        line: "#DDDCD4",
        accent: { DEFAULT: "#005E9E", light: "#E8F2F9" },
        paid: { DEFAULT: "#1A7F37", bg: "#E6F4EA" },
        pending: { DEFAULT: "#9A6700", bg: "#FBF0D2" },
        unpaid: { DEFAULT: "#B3372E", bg: "#FBE9E7" },
      },
      fontFamily: {
        sans: ['"PT Sans"', "system-ui", "sans-serif"],
        mono: ['"PT Mono"', "ui-monospace", "monospace"],
      },
    },
  },
};
