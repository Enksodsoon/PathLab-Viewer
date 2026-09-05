import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PATHLAB_E2E_BASE_URL
if (!baseURL || new URL(baseURL).hostname !== '127.0.0.1'
  || new URL(baseURL).protocol !== 'http:') {
  throw new Error('Full-stack tests require the isolated loopback stack launcher')
}

export default defineConfig({
  testDir: './e2e-fullstack',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  reporter: 'line',
  expect: { timeout: 10_000 },
  use: { baseURL, actionTimeout: 15_000, trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'fullstack-chromium', use: { ...devices['Desktop Chrome'] } }],
})
