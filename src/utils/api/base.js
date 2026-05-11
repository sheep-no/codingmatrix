/**
 * API 基础客户端
 * 包含 token 管理和核心请求方法
 */
import { getCsrfToken, fetchCsrfToken } from '../csrf'
import { API_CONFIG } from './config'

const CSRF_SKIP_ENDPOINTS = [
  '/api/v1/csrf-token',
  '/api/v1/public-key',
  '/api/v1/register',
  '/api/v1/refresh'
]

const MAX_REFRESH_RETRIES = 2

function needsCsrfToken(url) {
  return !CSRF_SKIP_ENDPOINTS.some(endpoint => url.includes(endpoint))
}

export const apiUrl = import.meta.env.VITE_API_BASE || '/api/v1'

function getValidToken() {
  if (window.userStore && typeof window.userStore.getAccessToken === 'function') {
    const token = window.userStore.getAccessToken()
    if (token) return token
  }
  // Fallback to localStorage if store is not ready or token is missing in memory
  return localStorage.getItem('access_token')
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

      if (token && !isRefreshRequest) {
        try {
          const payload = JSON.parse(atob(token.split('.')[1]))
          const exp = payload.exp
          const now = Math.floor(Date.now() / 1000)

          if (now > exp) {
            if (userStore && userStore.refreshAccessToken) {
              const success = await userStore.refreshAccessToken()
              if (success) {
                token = getValidToken()
              } else {
                client.state.refreshRetryCount = 0
                if (userStore.clearUser) userStore.clearUser()
                throw new Error('Token refresh failed')
              }
            }
          }
        } catch (e) {
          if (e.message !== 'Token refresh failed') {
            token = null
          } else {
            throw e
          }
        }
      }

      const fullUrl = url.startsWith('http') ? url : `${apiUrl}${url}`

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
        throw new Error('Network request failed')
      }

      if ((response.status === 401 || response.status === 4001) && token && !isRetry) {
        client.state.refreshRetryCount++

        if (client.state.refreshRetryCount >= MAX_REFRESH_RETRIES) {
          client.state.refreshRetryCount = 0
          if (userStore && userStore.clearUser) userStore.clearUser()
          throw new Error('Authentication failed')
        }

        try {
          if (userStore && userStore.refreshAccessToken) {
            const success = await userStore.refreshAccessToken()
            if (success) {
              client.state.refreshRetryCount = 0
              return this.request(url, options, true)
            }
          }
        } catch (refreshError) {
          if (userStore && userStore.clearUser) userStore.clearUser()
          throw new Error('Authentication failed')
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

      const headers = {
        'Content-Type': 'application/json'
      }

      if (token) {
        headers['Authorization'] = `Bearer ${token}`
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
          if (userStore && userStore.clearUser) userStore.clearUser()
          throw new Error('Token refresh retry limit exceeded')
        }

        client.state.refreshRetryCount++

        try {
          if (userStore && userStore.refreshAccessToken) {
            const success = await userStore.refreshAccessToken()
            if (success) {
              token = getValidToken()
              headers['Authorization'] = `Bearer ${token}`
              client.state.refreshRetryCount = 0
              response = await fetch(fullUrl, fetchOptions)
            }
          }
        } catch (refreshError) {
          throw new Error('Stream token refresh failed')
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
    }
  }

  return client
}

export default { createBaseClient }
