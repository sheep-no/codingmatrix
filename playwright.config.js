const { defineConfig } = require('@playwright/test')
const fs = require('fs')

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        launchOptions: {
          executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || (
            fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined
          ),
          args: ['--no-sandbox', '--disable-dev-shm-usage'],
        },
      },
    },
  ],
})
