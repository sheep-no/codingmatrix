// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('../../', import.meta.url))
const read = (relativePath) => readFileSync(`${root}${relativePath}`, 'utf8')

describe('容器运行拓扑契约', () => {
  it('运行镜像只启动 API，不再内置 Nginx', () => {
    const dockerfile = read('Dockerfile')

    expect(dockerfile).not.toMatch(/apt-get install[^\n]*\bnginx\b/)
    expect(dockerfile).not.toContain('EXPOSE 80 8080')
    expect(dockerfile).not.toMatch(/CMD[^\n]*\bnginx\b/)
    expect(dockerfile).toContain('uvicorn app.main:app')
  })

  it('两套 Compose 都由独立 Nginx 服务代理 api:8080', () => {
    for (const composeFile of ['docker-compose.yml', 'docker-compose.prod.yml']) {
      const compose = read(composeFile)

      expect(compose).toContain('image: nginx:alpine')
      expect(compose).toContain('configs/nginx-upstream-compose.conf')
      expect(compose).not.toContain('configs/nginx-upstream-local.conf')
    }

    const upstream = read('configs/nginx-upstream-compose.conf')
    expect(upstream).toContain('server api:8080;')
  })
})
