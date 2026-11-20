/**
 * Token 管理模块
 *
 * 注意：使用纯 JS 变量而非 Vue ref，避免 HMR 导致状态丢失
 */

// 纯 JS 变量（不会被 HMR 重置）
let accessToken = null
let tokenExpiry = null

// 每次本地登出递增；在途刷新携带旧世代结果时必须丢弃，否则会把
// 用户刚清掉的 token 写回存储，表现为"退出后又自动登录"。
let sessionEpoch = 0

// 进行中的刷新请求：并发调用共享同一次刷新，避免重复请求与竞态覆盖
let inFlightRefresh = null

// 单次刷新请求超时：网络或后端挂起时必须尽快失败，否则 inFlightRefresh
// 会永久占位，所有等待刷新的请求随之卡死，首屏遮罩也无法结束。
const REFRESH_TIMEOUT_MS = 6000

async function fetchWithTimeout(url, options = {}) {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
  let timer = null
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      if (controller) controller.abort()
      reject(new Error('Token refresh timeout'))
    }, REFRESH_TIMEOUT_MS)
  })

  try {
    return await Promise.race([
      fetch(url, controller ? { ...options, signal: controller.signal } : options),
      timeout
    ])
  } finally {
    if (timer) clearTimeout(timer)
  }
}

// 初始化时尝试从 sessionStorage 恢复
try {
  const savedToken = sessionStorage.getItem('_token')
  const savedExpiry = sessionStorage.getItem('_token_expiry')
  if (savedToken && savedExpiry) {
    const expiry = parseInt(savedExpiry, 10)
    if (Date.now() <= expiry) {
      accessToken = savedToken
      tokenExpiry = expiry
    } else {
      sessionStorage.removeItem('_token')
      sessionStorage.removeItem('_token_expiry')
    }
  }
} catch (_e) { /* sessionStorage not available */ }

export const useTokenManager = () => {
  /**
   * 保存 access token
   */
  function setToken(token, expiresIn) {
    accessToken = token
    if (expiresIn) {
      tokenExpiry = Date.now() + (expiresIn - 120) * 1000
    } else {
      tokenExpiry = Date.now() + 28 * 60 * 1000
    }

    // 保存到 sessionStorage（HMR 恢复用）
    try {
      if (token) {
        sessionStorage.setItem('_token', token)
        sessionStorage.setItem('_token_expiry', String(tokenExpiry || ''))
        localStorage.setItem('access_token', token)
        localStorage.setItem('_token_expiry', String(tokenExpiry || ''))
      } else {
        sessionStorage.removeItem('_token')
        sessionStorage.removeItem('_token_expiry')
        localStorage.removeItem('access_token')
        localStorage.removeItem('_token_expiry')
      }
    } catch (_e) { /* storage not available */ }
  }

  /**
   * 获取 access token
   */
  function getToken() {
    // 优先返回内存中的 token
    if (accessToken) return accessToken

    // HMR 热更新后内存可能丢失，尝试从 sessionStorage 恢复
    const sessionToken = sessionStorage.getItem('_token')
    if (sessionToken) {
      const savedExpiry = sessionStorage.getItem('_token_expiry')
      const expiry = savedExpiry ? parseInt(savedExpiry, 10) : 0
      if (Date.now() <= expiry) {
        accessToken = sessionToken
        tokenExpiry = expiry
        return accessToken
      }
      sessionStorage.removeItem('_token')
      sessionStorage.removeItem('_token_expiry')
    }

    // 最后尝试 localStorage
    const localToken = localStorage.getItem('access_token')
    if (localToken) {
      const savedExpiry = localStorage.getItem('_token_expiry')
      const expiry = savedExpiry ? parseInt(savedExpiry, 10) : 0
      if (Date.now() <= expiry) {
        accessToken = localToken
        tokenExpiry = expiry
        return accessToken
      }
    }

    return null
  }

  /**
   * 检查 token 是否有效
   */
  function isTokenValid() {
    if (!accessToken) return false
    if (!tokenExpiry) return false
    return Date.now() <= tokenExpiry
  }

  /**
   * 清除 token
   */
  function clearToken() {
    sessionEpoch += 1
    accessToken = null
    tokenExpiry = null
    try {
      sessionStorage.removeItem('_token')
      sessionStorage.removeItem('_token_expiry')
      localStorage.removeItem('access_token')
      localStorage.removeItem('_token_expiry')
    } catch (_e) { /* storage not available */ }
  }

  /**
   * 刷新 access token
   */
  async function performRefresh() {
    const epochAtStart = sessionEpoch
    try {
      // 首先获取 CSRF token
      let csrfToken = null
      try {
        const csrfResp = await fetchWithTimeout('/api/v1/csrf-token', { credentials: 'same-origin' })
        if (csrfResp.ok) {
          const csrfData = await csrfResp.json()
          csrfToken = csrfData.csrf_token
        }
      } catch (e) {
        // CSRF token 获取失败，继续尝试刷新
      }

      const headers = { 'Content-Type': 'application/json' }
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
      }

      const response = await fetchWithTimeout('/api/v1/refresh', {
        method: 'POST',
        credentials: 'same-origin',
        headers
      })

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          console.warn('[WARN] Refresh token invalid, please re-login')
          if (!isTokenValid()) {
            clearToken()
          }
          return false
        }
        throw new Error('Token refresh failed')
      }

      const data = await response.json()
      if (data.access_token) {
        if (epochAtStart !== sessionEpoch) {
          // 刷新期间用户已登出，丢弃晚到的 token
          return false
        }
        const parts = data.access_token.split('.')
        if (parts.length !== 3) {
          console.warn('[WARN] Invalid access_token format from refresh')
          return false
        }
        try {
          const payload = JSON.parse(atob(parts[1]))
          const expiresIn = Math.floor((payload.exp * 1000 - Date.now()) / 1000)
          setToken(data.access_token, expiresIn)
          return true
        } catch (e) {
          console.error('[ERR] Failed to parse refreshed access_token payload:', e)
          return false
        }
      }
      return false
    } catch (error) {
      console.error('[ERR] Token refresh failed:', error)
      clearToken()
      return false
    }
  }

  /**
   * 刷新 access token（并发调用共享同一次请求）
   */
  function refreshAccessToken() {
    if (!inFlightRefresh) {
      inFlightRefresh = performRefresh().finally(() => {
        inFlightRefresh = null
      })
    }
    return inFlightRefresh
  }

  return {
    setToken,
    getToken,
    isTokenValid,
    clearToken,
    refreshAccessToken
  }
}
