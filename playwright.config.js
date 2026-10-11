// @ts-check
const { defineConfig } = require('@playwright/test');
const os = require('os');
const path = require('path');

// E2E for the tool-marking flow. All API calls are stubbed by
// tests/e2e/stubs.cjs, so only static assets come from the running server.
// Self-contained: the e2e server boots on its OWN port with a throwaway
// database (test-DB isolation rule — tests must never touch the live
// database file, 2026-09-09 incident class). No dev/systemd service needs
// to be running; static paths are auth-exempt on purpose.
const E2E_PORT = 8770;

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${E2E_PORT}`,
    // The app registers a service worker that serves cached GETs (including
    // '/' and '/tools/groups') straight from the SW cache/network, which would
    // bypass our route stubs and hit the real (auth'd) API. Keep the SW out.
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `python -m uvicorn main:app --host 127.0.0.1 --port ${E2E_PORT}`,
    url: `http://127.0.0.1:${E2E_PORT}/health`,
    timeout: 30_000,
    // Never attach to a dev/systemd instance running the LIVE database.
    reuseExistingServer: false,
    env: {
      ...process.env,
      // Unique per run: fresh state, no cross-run bleed; the OS collects
      // tmp leftovers.
      DB_PATH: path.join(os.tmpdir(), `pisynapse-e2e-${process.pid}.db`),
    },
  },
});
