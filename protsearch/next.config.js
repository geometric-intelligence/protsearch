import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

/** @type {import("next").NextConfig} */
const config = {
  // Make both roots the same (Vercel sets outputFileTracingRoot to repo root)
  typescript: { ignoreBuildErrors: true },
  turbopack: { root: repoRoot },
  outputFileTracingRoot: repoRoot,
};

export default config;