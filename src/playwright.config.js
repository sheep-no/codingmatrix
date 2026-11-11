// 从 src 目录运行时复用根配置，避免两份配置的浏览器参数与重试策略漂移。
// testDir 用绝对路径，确保从 src 解析后仍指向仓库根 tests/e2e（FRESCAN-25）。
import { fileURLToPath } from 'node:url'

import rootConfig from '../playwright.config.js'

export default {
  ...rootConfig,
  testDir: fileURLToPath(new URL('../tests/e2e', import.meta.url)),
}
