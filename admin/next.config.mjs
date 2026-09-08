import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // A stray lockfile higher in the KINGHENRYMORGAN_ANALYTICS tree (an
  // unrelated project) makes Next.js guess the wrong monorepo root —
  // pin it explicitly so builds (local and Vercel) don't depend on that.
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
