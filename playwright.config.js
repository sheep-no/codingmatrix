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
          // 2026-11 起 GH runner 底层 VM 时钟（bogo-microseconds 计数）在
          // EventTiming 采样间回退，触发 Blink window_performance.cc:1051 的
          // CHECK fatal（SIGABRT -> page crashed，见诊断轮 pw:browser 日志）。
          // 禁用 PerformanceEventTiming 绕开该断言；headful 同为软件渲染栈
          // 也崩，故保留 headless 默认即可
          args: [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-features=PerformanceEventTiming',
          ],
        },
      },
    },
  ],
})
