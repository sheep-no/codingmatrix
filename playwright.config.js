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
          // 2026-11 起 GH runner 底层 VM 的 kvm-clock 与 TSC 混用，viz（GPU
          // 进程）与 renderer 的 TimeTicks 采样偶发偏移，触发 Blink
          // window_performance.cc 的 EventTiming 帧聚合 CHECK fatal
          // （SIGABRT -> page crashed，见 pw:browser 日志；hpet 切换无效，
          // feature flag 无关——CHECK 不受 runtime feature 控制）。
          // 禁 GPU 合成让 render 时间戳回到 renderer 进程内采样
          args: [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu-compositing',
          ],
        },
      },
    },
  ],
})
