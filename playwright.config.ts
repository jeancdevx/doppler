import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 90_000,
  expect: {
    timeout: 15_000
  },
  fullyParallel: false,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/playwright-results.json' }]
  ],
  use: {
    baseURL: process.env.APP_ORIGIN || 'http://localhost:4321',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  }
})
