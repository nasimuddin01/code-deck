import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `pnpm dev` on :5173 proxies the API/WS to the Python server
// (CODE_DECK_PORT from the repo-root .env, default 8765).
// `code-deck serve --player-url http://127.0.0.1:5173/player?device=1` then
// gives hot reload on the physical screen.
export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, "..", "CODE_DECK_"), ...process.env };
  const port = env.CODE_DECK_PORT || "8765";
  return {
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${port}`,
      "/ws": { target: `ws://127.0.0.1:${port}`, ws: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // deterministic device rendering: no code-splitting surprises
    rollupOptions: {
      output: { manualChunks: undefined },
      // zod ships /* @__PURE__ */ comments rollup can't place; harmless, just noisy
      onwarn(warning, warn) {
        if (warning.code === "INVALID_ANNOTATION") return;
        warn(warning);
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  };
});
