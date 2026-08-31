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
    // Multiple jsdom workers intermittently time out during startup on
    // Windows. One thread is stable and this suite is small enough that file
    // parallelism provides no meaningful speedup.
    pool: "threads",
    fileParallelism: false,
    maxWorkers: 1,
  },
});
