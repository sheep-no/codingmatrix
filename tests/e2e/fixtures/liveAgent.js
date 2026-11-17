/**
 * Agent live 用例的真实凭证同步。
 *
 * 这些用例会走真实模型调用，必须把服务端已配置的 Key 元数据同步到
 * localStorage；伪造的 token 在 Redis 中不存在，后端会直接报
 * UserAPIKeyNotFoundError。
 */

async function syncRealApiKeys(page) {
  const result = await page.evaluate(async () => {
    // 路由守卫依赖 token 有效期键，缺失时会被判为未登录并重定向回首页。
    const token = sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    if (token && !localStorage.getItem('_token_expiry')) {
      const expiry = String(Date.now() + 30 * 60 * 1000)
      sessionStorage.setItem('_token', token)
      sessionStorage.setItem('_token_expiry', expiry)
      localStorage.setItem('_token_expiry', expiry)
    }
    const resp = await fetch('/api/v1/agent/apikeys', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await resp.json().catch(() => [])
    const list = Array.isArray(data) ? data : []
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify(list))
    return { status: resp.status, count: list.length }
  })
  if (result.status !== 200) {
    throw new Error(`同步 API Key 失败: HTTP ${result.status}`)
  }
  if (result.count === 0) {
    throw new Error('需要至少一条已配置的硅基流动 Key')
  }
  return result
}

module.exports = { syncRealApiKeys }
