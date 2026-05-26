/**
 * 在线环境 Token 修复验证
 * 注意：由于跨域限制，需要在线域下直接登录
 */
import { test, expect } from '@playwright/test'

const ONLINE_URL = 'https://3000-9f66c22588b66963.monkeycode-ai.online'
const TEST_EMAIL = 'admin@example.com'
const TEST_PASSWORD = 'admin123'

test.describe('在线环境 Token 修复验证', () => {
  test('登录并验证 token 同步', async ({ page }) => {
    test.slow()

    // 收集控制台日志
    const consoleErrors = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
      console.log(`[CONSOLE] ${msg.type()}: ${msg.text().substring(0, 150)}`)
    })

    page.on('pageerror', error => {
      consoleErrors.push(error.message)
      console.error(`[PAGE ERROR] ${error.message}`)
    })

    // 直接导航到在线环境首页
    await page.goto(ONLINE_URL, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    // 获取 CSRF token
    const csrfResp = await page.request.get(`${ONLINE_URL}/api/v1/csrf-token`)
    const csrfData = await csrfResp.json()
    const csrfToken = csrfData.csrf_token

    // 登录
    const loginResp = await page.request.post(`${ONLINE_URL}/api/v1/login`, {
      data: { email: TEST_EMAIL, password: TEST_PASSWORD },
      headers: { 'X-CSRF-Token': csrfToken }
    })
    const data = await loginResp.json()

    expect(loginResp.ok()).toBeTruthy()
    expect(data.access_token).toBeTruthy()

    console.log('Login response:', JSON.stringify(data, null, 2))

    // 在在线域下设置存储
    await page.evaluate((obj) => {
      const expiry = Date.now() + 3600000
      sessionStorage.setItem('_token', obj.token)
      sessionStorage.setItem('_token_expiry', String(expiry))
      localStorage.setItem('access_token', obj.token)
      localStorage.setItem('username', obj.username)
      localStorage.setItem('email', obj.email)
      localStorage.setItem('permission_level', obj.permission_level)
      localStorage.setItem('user-store', JSON.stringify({
        isLoggedIn: true,
        username: obj.username,
        email: obj.email,
        permissionLevel: obj.permission_level
      }))
    }, {
      token: data.access_token,
      username: data.username || TEST_EMAIL,
      permission_level: data.permission_level || 'superadmin'
    })

    // 访问 /agent
    await page.goto(`${ONLINE_URL}/agent`, { waitUntil: 'domcontentloaded' })
    
    // 等待 Vue 组件渲染和 API 请求
    await page.waitForTimeout(5000)

    // 截图
    await page.screenshot({ path: 'test-results/online-logged-in.png', fullPage: true })
    
    // 检查 DOM
    const domCheck = await page.evaluate(() => {
      return {
        hasAgentPage: !!document.querySelector('.agent-page'),
        appHasContent: document.getElementById('app')?.innerHTML.length > 100,
        url: window.location.href,
      }
    })
    
    console.log('DOM Check:', JSON.stringify(domCheck, null, 2))

    // 检查 token 状态
    const tokenState = await page.evaluate(() => {
      const userStore = window.userStore
      return {
        localToken: localStorage.getItem('access_token'),
        sessionToken: sessionStorage.getItem('_token'),
        userStoreToken: userStore?.getAccessToken(),
        userStoreIsLoggedIn: userStore?.isLoggedIn,
        userStorePermissionLevel: userStore?.permissionLevel,
      }
    })

    console.log('Token State:', JSON.stringify(tokenState, null, 2))

    // 验证 token 同步
    expect(tokenState.userStoreToken).toBeTruthy()
    expect(tokenState.userStoreIsLoggedIn).toBeTruthy()
  })
})
