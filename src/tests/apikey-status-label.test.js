import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  resolve(__dirname, '../components/settings/APIKeyManager.vue'),
  'utf8'
)

describe('API Key 状态文案', () => {
  it('没有 status 的密钥展示「未配置」，避免出现「未知」', () => {
    const fn = source.match(/function getStatusText\(status\) \{([\s\S]*?)\n\}/)
    expect(fn).not.toBeNull()
    expect(fn[1]).toContain("'未配置'")
    expect(fn[1]).not.toContain("'未知'")
  })
})
