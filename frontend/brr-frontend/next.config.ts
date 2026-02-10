/** Configuracion de Next.js para el frontend. */

import type { NextConfig } from "next";

const DEFAULT_LOCAL_API = "http://127.0.0.1:8000";
const DEFAULT_RENDER_API = "https://global-overview-radar.onrender.com";
const USE_SERVER_PROXY = process.env.USE_SERVER_PROXY === "true";

const nextConfig: NextConfig = {
  outputFileTracingRoot: __dirname,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
    ];
  },
  async rewrites() {
    if (USE_SERVER_PROXY) {
      return [];
    }
    const defaultTarget = process.env.VERCEL ? DEFAULT_RENDER_API : DEFAULT_LOCAL_API;
    const apiTarget = (process.env.API_PROXY_TARGET ?? defaultTarget).replace(/\/+$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
