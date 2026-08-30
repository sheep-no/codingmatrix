/**
 * 认证测试 Fixtures
 * 提供登录、登出等辅助函数
 */

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000'

export const TEST_EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
export const TEST_PASSWORD = process.env.TEST_ADMIN_PASSWORD
let cachedLoginData = null

/**
 * API 登录 - 使用 page.request API
 * @param {Page} page - Playwright page object
 * @param {string} frontendUrl - Optional frontend URL (defaults to localhost:3000)
 * @returns {Promise<{token: string, username: string}>}
 */
export async function apiLogin(page, frontendUrl) {
  console.log('[apiLogin] Starting login for', TEST_EMAIL);
  if (!TEST_PASSWORD) {
    throw new Error('请设置 TEST_ADMIN_PASSWORD 后再执行认证 E2E')
  }
  const FRONTEND_URL = frontendUrl || 'http://localhost:3000';
  try {
    let data = cachedLoginData
    if (!data) {
      const csrfResp = await page.request.get(`${BASE_URL}/api/v1/csrf-token`)
      const csrfData = await csrfResp.json()
      const csrfToken = csrfData.csrf_token

      const loginResp = await page.request.post(`${BASE_URL}/api/v1/login`, {
        data: { email: TEST_EMAIL, password: TEST_PASSWORD },
        headers: {
          'X-CSRF-Token': csrfToken,
          Cookie: `csrf_token=${csrfToken}`
        }
      })
      data = await loginResp.json()

      if (!loginResp.ok || !data.access_token) {
        throw new Error(`Login failed: ${data.message || data.detail || 'Unknown error'}`)
      }
      cachedLoginData = data
    }

    // Navigate to frontend to set storage in correct origin
    await page.goto(FRONTEND_URL);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(300);

    // Store in sessionStorage (where tokenManager stores it)
    await page.evaluate((obj) => {
      console.log('[sessionStorage] Setting token for tokenManager');
      const expiry = Date.now() + 3600000; // 1 hour from now
      sessionStorage.setItem('_token', obj.token)
      sessionStorage.setItem('_token_expiry', String(expiry))
      console.log('[sessionStorage] Token set, expiry:', new Date(expiry).toISOString())

      // Set localStorage for username/email/permission (what app expects)
      localStorage.setItem('username', obj.username)
      localStorage.setItem('email', obj.email)
      localStorage.setItem('permission_level', obj.permission_level)
      localStorage.setItem('access_token', obj.token)
      
      // Set Pinia persisted user-store state
      const userStoreState = {
        isLoggedIn: true,
        username: obj.username,
        email: obj.email,
        permissionLevel: obj.permission_level
      }
      localStorage.setItem('user-store', JSON.stringify(userStoreState))
      console.log('[sessionStorage] Done')
    }, {
      token: data.access_token,
      username: data.username || TEST_EMAIL,
      email: TEST_EMAIL,
      permission_level: data.permission_level || 'superadmin'
    })
    console.log('[apiLogin] Storage set, permission_level:', data.permission_level || 'user')
    
    // Wait for storage to persist
    await page.waitForTimeout(300)
    
    console.log('[apiLogin] Login complete, returning token')
    return {
      ok: true,
      token: data.access_token,
      username: data.username || TEST_EMAIL,
    }
  } catch (e) {
    console.log('[apiLogin] ERROR:', e.message)
    console.error(e)
    throw e
  }
}

/**
 * 登出 - 清除 localStorage
 * @param {Page} page - Playwright page object
 */
export async function logout(page) {
  const FRONTEND_URL = 'http://localhost:3000';

  // Navigate to frontend first
  await page.goto(FRONTEND_URL)
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(300)

  await page.evaluate(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('username')
    localStorage.removeItem('email')
    localStorage.removeItem('permission_level')
  })
  
  // Reload to apply changes
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(300)
}

/**
 * 等待页面加载完成
 * @param {Page} page
 */
export async function waitForPageReady(page) {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(500) // 额外等待 500ms 确保组件渲染
}
