import { existsSync, readFileSync } from "node:fs";
import { parseEnv } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const localEnvPath = fileURLToPath(new URL("../.env.local", import.meta.url));
const repositoryEnvPath = fileURLToPath(new URL("../../.env", import.meta.url));
const nextCli = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const inheritedEnvironment = { ...process.env };

// The backend intentionally reads the repository-root .env, while Next.js
// normally reads only frontend/.env*. When no frontend override exists, copy
// only browser-public values into the dev process so both sides use the same
// auth mode without exposing backend secrets to Next.js.
if (!existsSync(localEnvPath) && existsSync(repositoryEnvPath)) {
  const repositoryEnvironment = parseEnv(readFileSync(repositoryEnvPath, "utf8"));
  for (const [key, value] of Object.entries(repositoryEnvironment)) {
    if (key.startsWith("NEXT_PUBLIC_") && inheritedEnvironment[key] === undefined) {
      process.env[key] = value;
    }
  }
}

// Run the Next CLI in this process instead of spawning a child. This preserves
// normal Ctrl+C behavior and prevents an orphaned dev server from retaining
// port 3000 after the wrapper exits.
process.chdir(frontendRoot);
process.argv = [process.execPath, nextCli, "dev", ...process.argv.slice(2)];
await import(pathToFileURL(nextCli).href);
