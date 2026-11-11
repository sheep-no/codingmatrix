// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('../../', import.meta.url))

describe('Playwright 配置单一来源（FRESCAN-25）', () => {
  it('src 配置复用根配置，testDir 仍指向仓库根 tests/e2e', () => {
    const srcSource = readFileSync(`${root}src/playwright.config.js`, 'utf8')
    expect(srcSource).toContain("from '../playwright.config.js'")
    expect(srcSource).toContain("new URL('../tests/e2e', import.meta.url)")
    expect(srcSource).not.toContain('defineConfig({')
  })

  it('浏览器启动参数只在根配置定义', () => {
    const rootSource = readFileSync(`${root}playwright.config.js`, 'utf8')
    const srcSource = readFileSync(`${root}src/playwright.config.js`, 'utf8')
    expect(rootSource).toContain('--disable-gpu-compositing')
    expect(srcSource).not.toContain('launchOptions')
  })

  it('两处 package.json 使用同一 Playwright 版本', () => {
    const rootPkg = JSON.parse(readFileSync(`${root}package.json`, 'utf8'))
    const srcPkg = JSON.parse(readFileSync(`${root}src/package.json`, 'utf8'))
    expect(srcPkg.devDependencies['@playwright/test']).toBe(rootPkg.devDependencies['@playwright/test'])
  })
})
