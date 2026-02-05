/** Configuracion de Next.js para el frontend. */

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: __dirname,
  async rewrites() {
    const apiTarget = (process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000").replace(
      /\/+$/,
      "",
    );
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
