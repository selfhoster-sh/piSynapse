// @ts-check
const { defineConfig } = require('@playwright/test');

// E2E for the tool-marking flow. All API calls are stubbed by
// tests/e2e/stubs.cjs, so only static assets come from the running server.
// The dev service (systemd: pisynapse.service, port 8765) must be up; static
// paths are auth-exempt on purpose.
module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    // The app registers a service worker that serves cached GETs (including
    // '/' and '/tools/groups') straight from the SW cache/network, which would
    // bypass our route stubs and hit the real (auth'd) API. Keep the SW out.
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python -m uvicorn main:app --host 127.0.0.1 --port 8765',
    url: 'http://127.0.0.1:8765/health',
    timeout: 30_000,
    reuseExistingServer: true,
  },
});