/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // "standalone" output bundles everything needed to run with `node server.js`.
  // Works on any cloud (AWS ECS, Azure Container Apps, GCP Cloud Run, etc.)
  // as well as Vercel. No platform-specific adapters needed.
  output: "standalone",
  logging: {
    fetches: { fullUrl: false },
  },
  // NEXT_PUBLIC_API_URL must be set at build time for the correct API host.
  // Default falls back to localhost for local development only.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};
export default nextConfig;
