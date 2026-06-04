import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        paper: "#f6f7f2",
        mist: "#e9f2ee",
        mint: "#0f8f72",
        leaf: "#4f7f63",
        clay: "#a05a3b",
        danger: "#b42318",
        line: "#d8ddd6",
      },
      boxShadow: {
        panel: "0 18px 60px rgba(17, 24, 39, 0.10)",
        lift: "0 24px 80px rgba(15, 143, 114, 0.16)",
      },
    },
  },
  plugins: [typography],
};

export default config;
