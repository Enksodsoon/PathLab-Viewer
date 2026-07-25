import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.CAPACITY_BASE_URL
if (!baseURL?.startsWith('https://')) {
  throw new Error('CAPACITY_BASE_URL must be an HTTPS origin')
}

export default defineConfig({
  testDir: './e2e-live',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 25 * 60_000,
  reporter: 'line',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    viewport: { width: 1440, height: 900 },
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'production-chromium', use: { browserName: 'chromium' } }],
})
