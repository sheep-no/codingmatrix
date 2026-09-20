// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useTokenManager } from './tokenManager'

// 生成结构合法的 JWT，payload.exp 为未来时间
function makeAccessToken(expiresInSeconds = 3600) {
  const payload = { exp: Math.floor(Date.now() / 1000) + expiresInSeconds }
  const encoded = btoa(JSON.stringify(payload))
  return `header.${encoded}.signature`
}

describe('tokenManager.refreshAccessToken 并发去重', () => {
  let fetchMock

  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    fetchMock = vi.fn(async (url) => {
      const target = String(url)
      if (target.includes('/csrf-token')) {
        return { ok: true, json: async () => ({ csrf_token: 'csrf' }) }
      }
      if (target.includes('/refresh')) {
        // 延迟返回，制造并发窗口
        await new Promise((resolve) => setTimeout(resolve, 10))
        return { ok: true, json: async () => ({ access_token: makeAccessToken() }) }
      }
      throw new Error(`unexpected fetch: ${target}`)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function refreshCallCount() {
    return fetchMock.mock.calls.filter(([url]) => String(url).includes('/refresh')).length
  }

  it('并发调用只发出一次刷新请求', async () => {
    const tokenManager = useTokenManager()

    const results = await Promise.all([
      tokenManager.refreshAccessToken(),
      tokenManager.refreshAccessToken(),
      tokenManager.refreshAccessToken(),
    ])

    expect(refreshCallCount()).toBe(1)
    expect(results).toEqual([true, true, true])
  })

  it('刷新结束后可再次发起刷新', async () => {
    const tokenManager = useTokenManager()

    expect(await tokenManager.refreshAccessToken()).toBe(true)
    expect(await tokenManager.refreshAccessToken()).toBe(true)
    expect(refreshCallCount()).toBe(2)
  })
})
