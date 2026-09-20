// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const appVue = readFileSync(
  fileURLToPath(new URL('../App.vue', import.meta.url)),
  'utf8',
)

describe('App.vue 应用壳背景声明', () => {
  it('.app-container 只声明一条 background，并使用变量 fallback', () => {
    const block = appVue.match(/\.app-container\s*\{([\s\S]*?)\}/)
    expect(block).not.toBeNull()

    const declarations = block[1]
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('background:'))

    expect(declarations).toEqual(['background: var(--gradient-bg, var(--bg-secondary));'])
  })
})
