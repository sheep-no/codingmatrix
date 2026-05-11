/**
 * CSRF Token 管理
 *
 * 双重提交 Cookie 模式：
 * 1. Cookie 中存储 CSRF Token（HttpOnly=false）
 * 2. 请求时在 X-CSRF-Token Header 中携带相同 Token
 * 3. 后端验证 Cookie 和 Header 中的 Token 一致
 */

/**
 * 从 Cookie 中获取 CSRF Token
 */
export function getCsrfToken() {
  const match = document.cookie.match(/csrf_token=([^;]+)/)
  return match ? match[1] : null
}

/**
 * 清除 CSRF Token
 */
export function clearCsrfToken() {
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;'
}

/**
 * 检查 CSRF Token 是否有效
 */
export function isCsrfTokenValid() {
  return getCsrfToken() !== null
}

/**
 * 获取 CSRF Token（如果 Cookie 中没有，则从 API 获取）
 */
export async function fetchCsrfToken() {
  // 先尝试从 Cookie 读取
  const cachedToken = getCsrfToken()
  if (cachedToken) {
    return cachedToken
  }

  try {
    const response = await fetch('/api/v1/csrf-token', {
      method: 'GET',
      credentials: 'include'
    })

    if (!response.ok) {
      throw new Error('获取 CSRF Token 失败')
    }

    const data = await response.json()
    const csrfToken = data.csrf_token

    // Cookie 已自动设置，直接返回
    return csrfToken
  } catch (error) {
    console.error('获取 CSRF Token 失败:', error)
    return null
  }
}
