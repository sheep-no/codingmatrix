/**
 * API 认证模块
 */
import { encryptLoginData } from '../encryption'
import { getCsrfToken } from '../csrf'
import { apiUrl, getValidToken } from './base'

export function createAuthClient(client) {
  return {
    async login(credentials) {
      const fullUrl = `${apiUrl}/login`

      await fetch('/api/v1/csrf-token', { credentials: 'include' })
      const csrfToken = getCsrfToken()

      const headers = {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken || ''
      }

      const encryptedData = await encryptLoginData({
        email: credentials.email,
        password: credentials.password
      })

      let requestBody
      if (encryptedData) {
        requestBody = encryptedData
      } else {
        requestBody = {
          email: credentials.email,
          password: credentials.password
        }
      }

      const response = await fetch(fullUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
        credentials: 'include'
      })

      if (response.ok) {
        const data = await response.json()
        return data
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Login failed')
      }
    },

    async register(userData) {
      const response = await client.post('/register', userData)
      if (response.ok) {
        return await response.json()
      } else {
        const error = await response.json()
        throw new Error(error.detail || 'Registration failed')
      }
    },

    async refreshToken() {
      try {
        const response = await fetch(`${apiUrl}/refresh`, {
          method: 'POST',
          credentials: 'include'
        })

        if (response.ok) {
          return await response.json()
        }
        return null
      } catch (error) {
        return null
      }
    },

    async logout() {
      // 登出必须使用当前 token 立即吊销，不能走客户端的自动刷新：
      // 登出期间刷新返回的新 token 会被作废，refresh Cookie 反而残留。
      const token = getValidToken()
      const headers = { 'Content-Type': 'application/json' }
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
      const csrfToken = getCsrfToken()
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
      }

      try {
        const response = await fetch(`${apiUrl}/logout`, {
          method: 'POST',
          headers,
          body: '{}',
          credentials: 'include',
          keepalive: true
        })
        return response.ok
      } catch (error) {
        return false
      }
    }
  }
}

export default { createAuthClient }
