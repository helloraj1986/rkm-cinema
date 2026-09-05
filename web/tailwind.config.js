/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // RKM-ish accent palette; overridden later by the design theme pass.
        accent: { DEFAULT: "#ff9500", soft: "#ffb340" },
      },
    },
  },
  plugins: [],
};