import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      borderRadius: { xl: "1rem", "2xl": "1.25rem" },
      boxShadow: { card: "0 8px 30px rgb(15 23 42 / 0.06)" },
      colors: {
        surface: "hsl(var(--surface))",
        line: "hsl(var(--line))",
        muted: "hsl(var(--muted))",
        ink: "hsl(var(--ink))",
        brand: "hsl(var(--brand))",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
