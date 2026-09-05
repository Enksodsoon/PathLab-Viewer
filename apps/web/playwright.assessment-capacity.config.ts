import { defineConfig, devices } from '@playwright/test'

if (!process.env.ASSESSMENT_CAPACITY_BASE_URL) throw new Error('ASSESSMENT_CAPACITY_BASE_URL required')

export default defineConfig({
  testDir: './e2e',
  testMatch: 'assessment-capacity-canary.spec.ts',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  timeout: 120_000,
  use: {
    baseURL: process.env.ASSESSMENT_CAPACITY_BASE_URL,
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  projects: [{ name: 'chromium' }],
})
