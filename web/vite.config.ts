import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `pnpm dev` on :5173 proxies the API/WS to the Python server on :8765.
// `code-deck serve --player-url http://127.0.0.1:5173/player?device=1` then
// gives hot reload on the physical screen.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // deterministic device rendering: no code-splitting surprises
    rollupOptions: { output: { manualChunks: undefined } },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
