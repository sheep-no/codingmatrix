// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

import rootConfig from '../../playwright.config.js'
import srcConfig from '../playwright.config.js'

const root = fileURLToPath(new URL('../../', import.meta.url))

describe('Playwright 配置单一来源（FRESCAN-25）', () => {
  it('src 配置复用根配置，testDir 仍指向仓库根 tests/e2e', () => {
    expect(srcConfig.testDir).toBe(`${root}tests/e2e`)
    expect(srcConfig.retries).toBe(rootConfig.retries)
    expect(srcConfig.use).toEqual(rootConfig.use)
  })

  it('浏览器启动参数只在根配置定义', () => {
    const rootArgs = rootConfig.projects[0].use.launchOptions.args
    expect(srcConfig.projects[0].use.launchOptions.args).toEqual(rootArgs)

    const srcSource = readFileSync(`${root}src/playwright.config.js`, 'utf8')
    expect(srcSource).toContain("from '../playwright.config.js'")
    expect(srcSource).not.toContain('defineConfig({')
  })

  it('两处 package.json 使用同一 Playwright 版本', () => {
    const rootPkg = JSON.parse(readFileSync(`${root}package.json`, 'utf8'))
    const srcPkg = JSON.parse(readFileSync(`${root}src/package.json`, 'utf8'))
    expect(srcPkg.devDependencies['@playwright/test']).toBe(rootPkg.devDependencies['@playwright/test'])
  })
})
