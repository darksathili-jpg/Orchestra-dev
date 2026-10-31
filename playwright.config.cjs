const { defineConfig } = require('@playwright/test');
const { mkdtempSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
// Every invocation gets new evidence and a disposable DB; preserve older runs.
const runDir = process.env.ORCHESTRA_E2E_RUN || mkdtempSync(join(tmpdir(), 'orchestra-v032-e2e-'));
process.env.ORCHESTRA_E2E_RUN = runDir;
console.log('ORCHESTRA E2E artifacts: ' + runDir);
module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 0,
  workers: 1,
  outputDir: join(runDir, 'test-results'),
  use: { baseURL: 'http://127.0.0.1:8766', browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: {
    command: 'python run.py',
    url: 'http://127.0.0.1:8766/api/snapshot',
    reuseExistingServer: false,
    timeout: 30000,
    env: { ORCHESTRA_DB: join(runDir, 'registry.sqlite3'), ORCHESTRA_PORT: '8766' }
  },
  reporter: [['list'], ['html', { outputFolder: join(runDir, 'playwright-report'), open: 'never' }]],
});
