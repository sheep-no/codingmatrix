// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('../../', import.meta.url))
const workflow = readFileSync(`${root}.github/workflows/frontend-ci.yml`, 'utf8')

describe('前端 CI 门禁契约（FRESCAN-66）', () => {
  it('CI 在构建前执行单元测试', () => {
    const tests = workflow.indexOf('npm run test:run')
    const build = workflow.indexOf('npm run build')
    expect(tests).toBeGreaterThan(-1)
    expect(build).toBeGreaterThan(tests)
  })

  it('Nginx 与容器配置变更也触发前端门禁', () => {
    expect(workflow).toContain("'configs/nginx*.conf'")
    expect(workflow).toContain("'Dockerfile'")
  })

  it('lint 使用只检查模式，避免 CI 自动改写工作区', () => {
    expect(workflow).toContain('npm run lint:check')
    expect(workflow).not.toContain('npm run lint\n')
  })
})
