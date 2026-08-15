import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.CAPACITY_BASE_URL
if (!baseURL?.startsWith('https://')) throw new Error('CAPACITY_BASE_URL must be HTTPS')

export default defineConfig({
  testDir: './e2e-live', fullyParallel: false, workers: 1, retries: 0,
  reporter: 'line', timeout: 120_000,
  use: { baseURL, trace: 'off', screenshot: 'off', video: 'off' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 5'] } },
  ],
})
