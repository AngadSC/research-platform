import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      // Keep the browser's Host so Django's CSRF Origin check matches (Vite defaults to the target's host).
      "/api": { target: apiProxyTarget, changeOrigin: false },
      "/_allauth": { target: apiProxyTarget, changeOrigin: false },
      // OAuth provider callbacks (Google redirect URI: http://localhost:5173/accounts/google/login/callback/).
      "/accounts": { target: apiProxyTarget, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    // jsdom is slower than happy-dom; the full suite runs close to the 5s default.
    testTimeout: 15000,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
