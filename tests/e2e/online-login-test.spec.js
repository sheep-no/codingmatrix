/**
 * 在线预览环境完整测试
 * 包括登录和 token 验证
 */
import { test, expect } from '@playwright/test'
import { apiLogin, TEST_EMAIL, TEST_PASSWORD } from './fixtures/auth.js'

const ONLINE_URL = 'https://3000-9f66c22588b66963.monkeycode-ai.online'
const API_URL = 'http://localhost:8000'

test.describe('在线预览环境登录测试', () => {
  test('在线环境登录并验证 token', async ({ page }) => {
    test.slow()

    // 收集控制台日志
    const consoleMessages = []
    page.on('console', msg => {
      consoleMessages.push({ type: msg.type(), text: msg.text() })
    })

    // API 登录
    console.log('Performing API login...')
    await apiLogin(page, API_URL)
    await page.waitForTimeout(1000)

    // 验证 token 已存储
    const tokenInfo = await page.evaluate(() => {
      return {
        sessionToken: sessionStorage.getItem('_token'),
        localToken: localStorage.getItem('access_token'),
        userStore: localStorage.getItem('user-store'),
      }
    })

    console.log('Token info after login:', JSON.stringify(tokenInfo, null, 2))
    expect(tokenInfo.sessionToken).toBeTruthy()

    // 导航到 /agent
    console.log('Navigating to /agent...')
    await page.goto(`${ONLINE_URL}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    // 截图
    await page.screenshot({ path: 'test-results/online-agent-logged-in.png', fullPage: true })

    // 检查页面状态
    const pageState = await page.evaluate(() => {
      return {
        hasAgentPage: !!document.querySelector('.agent-page'),
        hasPageContent: !!document.querySelector('.page-content'),
        agentStyles: document.querySelector('.agent-page') ? 
          getComputedStyle(document.querySelector('.agent-page')) : null,
        windowUserStoreExists: !!window.userStore,
        userStoreToken: window.userStore?.getAccessToken(),
      }
    })

    console.log('Page state:', JSON.stringify(pageState, null, 2))

    // 验证页面已渲染
    expect(pageState.hasAgentPage).toBeTruthy()
    expect(pageState.agentStyles?.display).toBe('flex')
  })
})
