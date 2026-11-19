/**
 * 在线环境 Token 修复验证
 * 注意：由于跨域限制，需要在线域下直接登录
 */
import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

// 预览域名会随会话变化，默认回到当前运行的 baseURL
const ONLINE_URL = process.env.ONLINE_URL || process.env.BASE_URL || 'http://127.0.0.1:3000'

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

    // 用统一 fixture 登录，避免硬编码已失效的测试账号
    await apiLogin(page, ONLINE_URL)

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
