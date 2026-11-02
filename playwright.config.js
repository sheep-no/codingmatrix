const { defineConfig } = require('@playwright/test')
const fs = require('fs')

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  // CI 用 xvfb 跑 headful：chrome-headless-shell 在 2026-10 底更新的
  // GH runner 系统栈上渲染进程随机崩溃（page crashed，跨 1234/1248
  // 两个 chromium 版本、22.04/latest 双镜像均复现，本地同版本全绿）；
  // headful 走真实渲染栈绕开 headless shell 的兼容性问题
  headless: process.env.CI ? false : true,
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
