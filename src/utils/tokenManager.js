/**
 * Token 管理模块
 *
 * 安全设计：
 * - Access Token 存储在内存中（Vue ref）
 * - Refresh Token 存储在 HttpOnly Cookie（后端设置）
 * - CSRF Token 存储在 Cookie（HttpOnly=false）
 * - 页面刷新后 Access Token 丢失，需通过 Refresh Token 重新获取
 */

import { ref } from 'vue'

// 内存中的 access token
const accessToken = ref(null)
const tokenExpiry = ref(null)

export const useTokenManager = () => {
  /**
   * 保存 access token（仅内存）
   */
  function setToken(token, expiresIn) {
    accessToken.value = token

    // 设置过期时间（提前 2 分钟）
    if (expiresIn) {
      tokenExpiry.value = Date.now() + (expiresIn - 120) * 1000
    } else {
      tokenExpiry.value = Date.now() + 28 * 60 * 1000
    }

    console.log('[OK] Token stored in memory')
  }

  /**
   * 获取 access token
   */
  function getToken() {
    if (tokenExpiry.value && Date.now() > tokenExpiry.value) {
      console.warn('[WARN] Token expired, needs refresh')
      clearToken()
      return null
    }

    return accessToken.value
  }

  /**
   * 检查 token 是否有效
   */
  function isTokenValid() {
    if (!accessToken.value) return false
    if (!tokenExpiry.value) return false
    return Date.now() <= tokenExpiry.value
  }

  /**
   * 清除 token
   */
  function clearToken() {
    accessToken.value = null
    tokenExpiry.value = null
    console.log('[DEL] Token cleared')
  }

  /**
   * 刷新 access token
   * 使用 HttpOnly Cookie 中的 refresh token
   */
  async function refreshAccessToken() {
    try {
      // 获取 CSRF token
      const csrfToken = getCsrfToken()

      const response = await fetch('/api/v1/refresh', {
        method: 'POST',
        credentials: 'same-origin', // 自动发送 HttpOnly Cookie
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken || ''
        }
      })

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          console.warn('[WARN] Refresh token invalid or expired, please re-login')
          clearToken()
          return false
        }
        throw new Error('Token 刷新失败')
      }

      const data = await response.json()

      // 保存新的 access token
      if (data.access_token) {
        const payload = JSON.parse(atob(data.access_token.split('.')[1]))
        const expiresIn = Math.floor((payload.exp * 1000 - Date.now()) / 1000)

        setToken(data.access_token, expiresIn)

        // 保存 CSRF Token（如果需要）
        if (data.csrf_token) {
          // CSRF token 已通过 Cookie 设置，这里可选保存到内存
          console.log('[OK] CSRF token updated')
        }

        console.log('[OK] Token refreshed')
        return true
      }

      return false
    } catch (error) {
      console.error('[ERR] Token refresh failed:', error)
      clearToken()
      return false
    }
  }

  /**
   * 获取 CSRF Token
   * 从 Cookie 中读取
   */
  function getCsrfToken() {
    const match = document.cookie.match(/csrf_token=([^;]+)/)
    return match ? match[1] : null
  }

  return {
    accessToken,
    setToken,
    getToken,
    isTokenValid,
    clearToken,
    refreshAccessToken,
    getCsrfToken
  }
}
