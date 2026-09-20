// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

import viteConfig from '../vite.config.js'

// 仓库根目录：src/tests/ -> src/ -> 仓库根
const root = fileURLToPath(new URL('../../', import.meta.url))
const read = (relativePath) => readFileSync(`${root}${relativePath}`, 'utf8')

describe('前端构建产物路径契约', () => {
  it('Vite 输出目录相对 src 为 dist（即仓库 src/dist）', () => {
    expect(viteConfig.build.outDir).toBe('dist')
  })

  it('部署链路全部引用 src/dist', () => {
    expect(read('configs/nginx.conf')).toContain('root /workspace/src/dist;')
    expect(read('scripts/start.sh')).toContain('$PROJECT_DIR/src/dist')
    expect(read('docker-compose.yml')).toContain('./src/dist:/workspace/src/dist:ro')
    expect(read('docker-compose.prod.yml')).toContain('./src/dist:/workspace/src/dist:ro')
    expect(read('.github/workflows/frontend-ci.yml')).toContain('path: src/dist/')
  })

  it('后端静态目录与前端产物一致', () => {
    expect(read('app/main.py')).toContain('DIST_PATH = rf"{BASE_DIR_PATH}/src/dist"')
  })

  it('Dockerfile 产物复制与 nginx 软链指向同一目录', () => {
    const dockerfile = read('Dockerfile')
    expect(dockerfile).toContain('COPY --from=frontend-builder /app/src/dist ./src/dist')
    expect(dockerfile).toContain('ln -sfn /app/src/dist /workspace/src/dist')
  })

  it('性能预算脚本读取同一产物目录', () => {
    expect(read('src/scripts/check-performance-budget.js')).toContain(
      "resolve(scriptDirectory, '../dist')",
    )
  })
})
