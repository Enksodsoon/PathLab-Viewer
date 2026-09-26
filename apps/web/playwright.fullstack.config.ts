import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PATHLAB_E2E_BASE_URL
const browser = process.env.PATHLAB_E2E_BROWSER ?? 'chromium'
const profiles = {
  chromium: devices['Desktop Chrome'],
  firefox: devices['Desktop Firefox'],
  webkit: devices['Desktop Safari'],
  'mobile-chromium': devices['Pixel 5'],
}
if (!(browser in profiles)) throw new Error('Unsupported isolated browser profile')
if (!baseURL || new URL(baseURL).hostname !== '127.0.0.1'
  || new URL(baseURL).protocol !== 'http:') {
  throw new Error('Full-stack tests require the isolated loopback stack launcher')
}

export default defineConfig({
  testDir: './e2e-fullstack',
  outputDir: process.env.PATHLAB_E2E_OUTPUT_DIR,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  reporter: 'line',
  expect: { timeout: 10_000 },
  use: { baseURL, actionTimeout: 15_000, trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'off' },
  projects: [{ name: `fullstack-${browser}`, use: { ...profiles[browser as keyof typeof profiles] } }],
})
