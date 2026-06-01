/**
 * API 基础客户端
 * 包含 token 管理和核心请求方法
 */
import { getCsrfToken, fetchCsrfToken } from '../csrf'
import { API_CONFIG } from './config'

const CSRF_SKIP_ENDPOINTS = [
  '/api/v1/csrf-token',
  '/api/v1/public-key',
  '/api/v1/register'
]

const MAX_REFRESH_RETRIES = 2

function needsCsrfToken(url) {
  return !CSRF_SKIP_ENDPOINTS.some(endpoint => url.includes(endpoint))
}

export const apiUrl = import.meta.env.VITE_API_BASE || '/api/v1'

function getValidToken() {
  // 1. 优先从 window.userStore 获取
  if (window.userStore && typeof window.userStore.getAccessToken === 'function') {
    try {
      const token = window.userStore.getAccessToken()
      if (token && token.trim()) {
        console.debug('[Token] Found token in window.userStore')
        return token
      }
    } catch (_e) { /* window.userStore not available */ }
  }
  
  // 2. 尝试从 window.api 关联的 userStore 获取
  if (window.api && window.api._userStore && typeof window.api._userStore.getAccessToken === 'function') {
    try {
      const token = window.api._userStore.getAccessToken()
      if (token && token.trim()) {
        console.debug('[Token] Found token in window.api._userStore')
        return token
      }
    } catch (_e) { /* window.api._userStore not available */ }
  }
  
  // 3. Fallback: sessionStorage (tokenManager 备份)
  const sessionToken = sessionStorage.getItem('_token')
  if (sessionToken && sessionToken.trim()) {
    console.debug('[Token] Found token in sessionStorage')
    return sessionToken
  }
  
  // 4. Fallback: localStorage
  const localToken = localStorage.getItem('access_token')
  if (localToken && localToken.trim()) {
    console.debug('[Token] Found token in localStorage')
    return localToken
  }
  
  console.warn('[Token] No valid token found in any storage, window.userStore exists:', !!window.userStore)
  return null
}

export function createBaseClient(userStore = null) {
  if (userStore) {
    window.userStore = userStore
  }

  const clientState = {
    refreshRetryCount: 0
  }

  const client = {
    state: clientState,

    async request(url, options = {}, isRetry = false) {
      let token = getValidToken()
      const isRefreshRequest = url.endsWith('/refresh') || url.includes('/refresh')
      const effectiveUserStore = userStore || window.userStore || null

      // Token 过期前自动刷新
      if (token && !isRefreshRequest) {
        try {
          const payload = JSON.parse(atob(token.split('.')[1]))
          const exp = payload.exp
          const now = Math.floor(Date.now() / 1000)

          if (now > exp) {
            console.debug('[API] Token expired, attempting refresh...')
            if (effectiveUserStore && effectiveUserStore.refreshAccessToken) {
              const success = await effectiveUserStore.refreshAccessToken()
              if (success) {
                token = getValidToken()
                console.debug('[API] Token refresh succeeded')
              } else {
                client.state.refreshRetryCount = 0
                console.warn('[API] Token refresh failed, clearing user')
                if (effectiveUserStore.clearUser) effectiveUserStore.clearUser()
                throw new Error('Token refresh failed')
              }
            }
          }
        } catch (e) {
          if (e.message !== 'Token refresh failed') {
            console.warn('[API] Invalid token format, setting to null')
            token = null
          } else {
            throw e
          }
        }
      }

      if (!token && !isRefreshRequest) {
        console.warn(`[API] No valid token found for request: ${url}`)
      }

      const fullUrl = url.startsWith('http') || url.startsWith('/api/') ? url : `${apiUrl}${url}`

      const headers = {
        'Content-Type': 'application/json'
      }

      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      if (needsCsrfToken(fullUrl)) {
        const csrfToken = getCsrfToken()
        if (csrfToken) {
          headers['X-CSRF-Token'] = csrfToken
        }
      }

      const fetchOptions = {
        ...options,
        headers,
        credentials: 'include'
      }

      let response
      try {
        response = await fetch(fullUrl, fetchOptions)
      } catch (error) {
        throw new Error('Network request failed', { cause: error })
      }

      if ((response.status === 401 || response.status === 4001) && token && !isRetry) {
        client.state.refreshRetryCount++

        if (client.state.refreshRetryCount >= MAX_REFRESH_RETRIES) {
          client.state.refreshRetryCount = 0
          if (effectiveUserStore && effectiveUserStore.clearUser) effectiveUserStore.clearUser()
          throw new Error('Authentication failed')
        }

        try {
          if (effectiveUserStore && effectiveUserStore.refreshAccessToken) {
            const success = await effectiveUserStore.refreshAccessToken()
            if (success) {
              client.state.refreshRetryCount = 0
              return this.request(url, options, true)
            }
          }
        } catch (refreshError) {
          if (effectiveUserStore && effectiveUserStore.clearUser) effectiveUserStore.clearUser()
          throw new Error('Authentication failed', { cause: refreshError })
        }
      }

      return response
    },

    async post(url, data) {
      const response = await this.request(url, {
        method: 'POST',
        body: JSON.stringify(data)
      })
      return response
    },

    async stream(url, data, signal = null) {
      let token = getValidToken()
      const fullUrl = url.startsWith('http') ? url : `${apiUrl}${url}`
      const effectiveUserStore = userStore || window.userStore || null

      const headers = {
        'Content-Type': 'application/json'
      }

      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      // 添加 CSRF token（如果需要）
      if (needsCsrfToken(fullUrl)) {
        const csrfToken = getCsrfToken()
        if (csrfToken) {
          headers['X-CSRF-Token'] = csrfToken
        }
      }

      const fetchOptions = {
        method: 'POST',
        headers,
        body: JSON.stringify(data),
        credentials: 'include'
      }

      if (signal) {
        fetchOptions.signal = signal
      }

      let response = await fetch(fullUrl, fetchOptions)

      if ((response.status === 401 || response.status === 4001) && token) {
        if (client.state.refreshRetryCount >= MAX_REFRESH_RETRIES) {
          client.state.refreshRetryCount = 0
          if (effectiveUserStore && effectiveUserStore.clearUser) effectiveUserStore.clearUser()
          throw new Error('Token refresh retry limit exceeded')
        }

        client.state.refreshRetryCount++

        try {
          if (effectiveUserStore && effectiveUserStore.refreshAccessToken) {
            const success = await effectiveUserStore.refreshAccessToken()
            if (success) {
              token = getValidToken()
              headers['Authorization'] = `Bearer ${token}`
              client.state.refreshRetryCount = 0
              response = await fetch(fullUrl, fetchOptions)
            }
          }
        } catch (refreshError) {
          throw new Error('Stream token refresh failed', { cause: refreshError })
        }
      }

      return response
    },

    async get(url, params = {}) {
      const queryString = Object.keys(params)
        .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`)
        .join('&')
      const fullUrl = queryString ? `${url}?${queryString}` : url
      return this.request(fullUrl, { method: 'GET' })
    },

    async put(url, data) {
      const response = await this.request(url, {
        method: 'PUT',
        body: JSON.stringify(data)
      })
      return response
    },

    async delete(url, data = null) {
      const options = { method: 'DELETE' }
      if (data) {
        options.body = JSON.stringify(data)
      }
      return this.request(url, options)
    }
  }

  return client
}

export default { createBaseClient }
