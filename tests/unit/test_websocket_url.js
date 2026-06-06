/**
 * WebSocket URL 替换逻辑单测
 *
 * 验证 P0-6 修复：connect() 的 {token} 占位符替换正确工作
 *
 * 使用 Node 内置 test runner (node --test) 避免引入 vitest 配置
 */

const { test } = require('node:test')
const assert = require('node:assert')

// 直接复制要被测的纯函数（不导入 src/ 因为它是 ESM + 浏览器依赖）
function buildWebSocketUrl(url, token) {
  let fullUrl = url
  if (token) {
    fullUrl = fullUrl.replace(/\{token\}/g, encodeURIComponent(token))
  } else {
    fullUrl = fullUrl.replace(/\?token=\{token\}(&|$)/, (m, tail) => tail === '&' ? '?' : '')
    fullUrl = fullUrl.replace(/&token=\{token\}(?=&|$)/, '')
  }
  return fullUrl
}

test('P0-6: default URL with token', () => {
  const url = 'ws://localhost:8000/api/v2/Controller/sys-status?token={token}'
  const result = buildWebSocketUrl(url, 'abc123')
  assert.strictEqual(result, 'ws://localhost:8000/api/v2/Controller/sys-status?token=abc123')
})

test('P0-6: {token} replaced when token provided', () => {
  const url = 'ws://host/api?token={token}&foo=bar'
  const result = buildWebSocketUrl(url, 'xyz')
  assert.strictEqual(result, 'ws://host/api?token=xyz&foo=bar')
})

test('P0-6: {token} placeholder stripped when no token', () => {
  const url = 'ws://host/api?token={token}&foo=bar'
  const result = buildWebSocketUrl(url, null)
  assert.strictEqual(result, 'ws://host/api?foo=bar')
})

test('P0-6: token with special chars URL-encoded', () => {
  const url = 'ws://host/api?token={token}'
  const result = buildWebSocketUrl(url, 'a/b+c=')
  assert.strictEqual(result, 'ws://host/api?token=a%2Fb%2Bc%3D')
})

test('P0-6: empty token treated as no token', () => {
  const url = 'ws://host/api?token={token}'
  const result = buildWebSocketUrl(url, '')
  // empty string is falsy, so placeholder gets stripped
  assert.strictEqual(result, 'ws://host/api')
})

test('P0-6: legacy /ws URL was wrong (regression test)', () => {
  // 这个 URL 在 P0-6 之前是默认，会被后端 403 拒绝
  // 现在 DEFAULT_WS_URL 已改为 v2 sys-status，这个 case 只是记录历史
  const legacy = 'ws://localhost:8000/ws'
  const result = buildWebSocketUrl(legacy, 'token')
  assert.strictEqual(result, 'ws://localhost:8000/ws', 'legacy URL should not get token appended (no placeholder)')
})

test('P0-6: real task_queue endpoint with user_id in path', () => {
  // 这个端点不能用 {token} placeholder（要的是 path param）
  // 调用方必须传完整 URL
  const url = 'ws://host/api/v1/tasks/ws/123'
  const result = buildWebSocketUrl(url, 'token')
  assert.strictEqual(result, 'ws://host/api/v1/tasks/ws/123')
})
