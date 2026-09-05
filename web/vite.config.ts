import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// The legacy app (`app.js`/`index.html`) is served at the site root by the
// `web` nginx container. The React port builds to `dist/` and is served from
// the same origin, with API calls going to the same-origin `/api/*` proxy.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  server: {
    port: 5173,
    // In dev, proxy /api to a locally running backend so the shell can show
    // real config health without CORS.
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});