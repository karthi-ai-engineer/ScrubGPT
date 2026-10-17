import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const appServer = "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@contracts": fileURLToPath(new URL("../../contracts/ts", import.meta.url)),
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": appServer,
      "/media": appServer,
    },
  },
  preview: {
    proxy: {
      "/api": appServer,
      "/media": appServer,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // The default `include` is kept so Tester 2's tests/acceptance/** also run.
    restoreMocks: true,
  },
});
