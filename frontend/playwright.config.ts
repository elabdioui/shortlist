// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "uv run --project .. python e2e/start_backend.py",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "pnpm start",
      url: "http://127.0.0.1:3000/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
