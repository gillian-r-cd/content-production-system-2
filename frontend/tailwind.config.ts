// frontend/tailwind.config.ts
// 功能: Tailwind CSS配置

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // 品牌色 - 深邃的蓝紫色调
        brand: {
          50: "#f0f4ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
        },
        // 背景色 - 暗色主题
        surface: {
          0: "#0a0a0b",
          1: "#111113",
          2: "#18181b",
          3: "#27272a",
          4: "#3f3f46",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "monospace"],
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
  ],
};

export default config;

