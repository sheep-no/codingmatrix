/**
 * API 认证模块
 */
import { encryptLoginData } from '../encryption'
import { getCsrfToken } from '../csrf'
import { apiUrl } from './base'

export function createAuthClient(client) {
  return {
    async login(credentials) {
      try {
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
      } catch (error) {
        throw error
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
      try {
        const response = await client.post('/logout', {})
        return response.ok
      } catch (error) {
        return false
      }
    }
  }
}

export default { createAuthClient }
