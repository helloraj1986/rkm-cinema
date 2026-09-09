/** @type {import('tailwindcss').Config} */
/**
 * RKM Cinema — Premium Media Library design tokens (2026-09).
 * Source of truth: RKM-CINEMA_NEW_UX/RKM_Cinema_Premium_Media_Library_Design_Spec.md
 * §2.3 (colour foundation), §3 (typography), §41 (design tokens).
 *
 * The zinc scale is deliberately remapped to the spec's layered dark surfaces
 * so every existing utility (bg-zinc-950 = page background etc.) inherits the
 * new system; amber is remapped to the signature yellow accent. New semantic
 * aliases (canvas/surface/elevated/accent) are available for fresh markup.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Spec colour foundation (§2.3).
        canvas: "#08090B",
        surface: { DEFAULT: "#101216", 2: "#15171C", 3: "#1B1E24" },
        card: "#17191E",
        accent: { DEFAULT: "#FFC400", hover: "#FFD43B" },
        // Legacy zinc utilities now resolve to the layered surfaces.
        zinc: {
          950: "#08090B", // --bg
          900: "#101216", // --surface-1
          800: "#15171C", // --surface-2 / card-border tone
          700: "#1B1E24", // --surface-3 (elevated)
          600: "#26292F", // hairline / strong border
          500: "#70747E", // --text-muted
          400: "#A7AAB2", // --text-secondary
          300: "#C2C5CB",
          200: "#E3E5E9",
          100: "#F5F5F7", // --text-primary
          50: "#FAFAFB",
        },
        // Legacy amber utilities resolve to the signature yellow accent.
        amber: {
          50: "#FFF8E1",
          100: "#FFF0C2",
          200: "#FFE7A3",
          300: "#FFD43B", // accent hover
          400: "#FFC400", // accent
          500: "#E0AE00",
          600: "#B78F00",
          700: "#8F6F00",
          800: "#6B5300",
          900: "#4A3900",
        },
        // Success colour (§2.3).
        emerald: {
          50: "#E9FBF1",
          100: "#C9F5DE",
          200: "#9EEDC4",
          300: "#6EE3A7",
          400: "#4CDB8F",
          500: "#35D07F",
          600: "#2BB46C",
          700: "#1F8B53",
          800: "#16643C",
          900: "#0E4429",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "SF Pro Display",
          "SF Pro Text",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        // Premium layered shadows (spec §52) — soft, never heavy.
        card: "0 4px 20px rgba(0,0,0,.32)",
        "card-hover": "0 20px 40px rgba(0,0,0,.38)",
        modal: "0 24px 80px rgba(0,0,0,.5)",
        glow: "0 0 0 3px rgba(255,196,0,.12)",
      },
    },
  },
  plugins: [],
};
