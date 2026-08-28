import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // The default forks pool times out spawning workers on Windows hosts;
    // threads start reliably in the same process.
    pool: "threads",
  },
});
