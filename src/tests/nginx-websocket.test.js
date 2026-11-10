// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('../../', import.meta.url))
const nginxConfig = readFileSync(`${root}configs/nginx.conf`, 'utf8')

function locationBlock(path) {
  const start = nginxConfig.indexOf(`location ${path} {`)
  expect(start).toBeGreaterThanOrEqual(0)
  const end = nginxConfig.indexOf('\n        }', start)
  expect(end).toBeGreaterThan(start)
  return nginxConfig.slice(start, end)
}

describe('Nginx API 代理契约', () => {
  it('/api/ 允许 WebSocket 协议升级，PPT 进度不再被握手拒绝', () => {
    const apiBlock = locationBlock('/api/')
    expect(apiBlock).toContain('proxy_http_version 1.1;')
    expect(apiBlock).toContain('proxy_set_header Upgrade $http_upgrade;')
    expect(apiBlock).toContain('proxy_set_header Connection $connection_upgrade;')
    expect(apiBlock).toContain('proxy_read_timeout 86400;')
  })

  it('Upgrade 仅在客户端请求时启用，普通 API 请求不会强制升级', () => {
    expect(nginxConfig).toContain('map $http_upgrade $connection_upgrade {')
    expect(nginxConfig).toContain('default upgrade;')
    expect(nginxConfig).toContain("''      close;")
  })
})
