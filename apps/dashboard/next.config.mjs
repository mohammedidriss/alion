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
  async rewrites() {
    return [
      // Same-origin proxy to the API so LAN phones (multi-camera, ADR-010) need no
      // CORS and only the dashboard's TLS cert. Dev/LAN; prod sets NEXT_PUBLIC_API_URL.
      { source: "/api/:path*", destination: "http://127.0.0.1:8000/:path*" },
    ];
  },
  // NEXT_PUBLIC_API_URL is auto-exposed by Next when it's set in the environment
  // (e.g. a production deploy). We deliberately do NOT default it to localhost:
  // when unset, the client derives the API host from window.location (lib/api.ts),
  // so a phone joining over the LAN (multi-camera, ADR-010) reaches the coach's
  // machine instead of its own localhost.
};
export default nextConfig;
