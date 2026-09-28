import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'

const baseURL = process.env.PATHLAB_E2E_BASE_URL
const browser = process.env.PATHLAB_E2E_BROWSER ?? 'chromium'
const device = {
  chromium: devices['Desktop Chrome'],
  firefox: devices['Desktop Firefox'],
  webkit: devices['Desktop Safari'],
  'mobile-chromium': devices['Pixel 5'],
}[browser]
if (!device) throw new Error(`Unsupported isolated browser: ${browser}`)
const workflowProject = `fullstack-${browser}`
if (!baseURL || new URL(baseURL).hostname !== '127.0.0.1'
  || new URL(baseURL).protocol !== 'http:') {
  throw new Error('Full-stack tests require the isolated loopback stack launcher')
}

export default defineConfig({
  testDir: './e2e-fullstack',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: process.env.PATHLAB_E2E_REPORT_DIR
    ? path.join(process.env.PATHLAB_E2E_REPORT_DIR, 'browser-artifacts') : undefined,
  timeout: 180_000,
  reporter: 'line',
  expect: { timeout: 10_000 },
  use: { baseURL, actionTimeout: 15_000, trace: 'off',
    screenshot: process.env.PATHLAB_E2E_REPORT_DIR ? 'only-on-failure' : 'off', video: 'off' },
  projects: [
    { name: workflowProject, testIgnore: '**/security-boundary.spec.ts', use: { ...device } },
    // Admission tests intentionally exhaust the shared loopback login budget.
    { name: 'fullstack-security', testMatch: '**/security-boundary.spec.ts',
      dependencies: [workflowProject], use: { ...device } },
  ],
})
