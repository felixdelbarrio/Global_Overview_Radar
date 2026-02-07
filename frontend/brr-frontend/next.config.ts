/** Configuracion de Next.js para el frontend. */

import type { NextConfig } from "next";

const DEFAULT_LOCAL_API = "http://127.0.0.1:8000";
const DEFAULT_RENDER_API = "https://global-overview-radar.onrender.com";
const USE_SERVER_PROXY = process.env.USE_SERVER_PROXY === "true";

const nextConfig: NextConfig = {
  outputFileTracingRoot: __dirname,
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
