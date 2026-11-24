// SPDX-License-Identifier: AGPL-3.0-or-later

import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT_STANDALONE === "1" ? "standalone" : undefined,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return {
      afterFiles: [
        {
          source: "/api/:path*",
          destination: `${apiUrl}/api/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
