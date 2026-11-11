// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('../../', import.meta.url))

const files = [
  'src/components/NginxConfig.vue',
  'src/components/UserManagement.vue',
  'src/components/settings/DynamicProviderManager.vue',
  'src/components/VirtualGirl.vue',
  'src/views/ChartEditorPage.vue'
]

const labelRe = /<label([^>]*)>([\s\S]*?)<\/label>/g

function labels(source) {
  return [...source.matchAll(labelRe)].map(([, attrs, body]) => ({ attrs, body }))
}

function controlIds(source) {
  return new Set([...source.matchAll(/<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"/g)].map(match => match[1]))
}

describe('表单 label 与控件关联（FRESCAN-67）', () => {
  for (const file of files) {
    it(`${file} 每个 label 都通过 for 关联或包裹控件`, () => {
      const source = readFileSync(`${root}${file}`, 'utf8')
      const ids = controlIds(source)

      for (const label of labels(source)) {
        const forMatch = label.attrs.match(/\bfor="([^"]+)"/)
        if (forMatch) {
          expect(ids.has(forMatch[1]), `${file} 中 for="${forMatch[1]}" 缺少对应控件 id`).toBe(true)
          continue
        }
        expect(
          /<(?:input|select|textarea)\b/.test(label.body),
          `${file} 中存在既无 for 也未包裹控件的 label：${label.body.trim().slice(0, 40)}`
        ).toBe(true)
      }
    })
  }
})
