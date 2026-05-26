/**
 * 在线预览环境测试
 * 测试平台提供的在线预览 URL 是否正常工作
 */
import { test, expect } from '@playwright/test'
import { apiLogin, TEST_EMAIL, TEST_PASSWORD } from './fixtures/auth.js'

const ONLINE_URL = 'https://3000-9f66c22588b66963.monkeycode-ai.online'

test.describe('在线预览环境访问', () => {
  test('访问首页应该正常加载', async ({ page }) => {
    test.slow()

    const navigationStart = Date.now()
    await page.goto(ONLINE_URL)
    await page.waitForLoadState('domcontentloaded')
    const domLoaded = Date.now() - navigationStart

    await page.waitForLoadState('load')
    const loadComplete = Date.now() - navigationStart

    // 截图
    await page.screenshot({ path: 'test-results/online-preview-home.png', fullPage: true })

    console.log(`Online URL load: DOMContentLoaded=${domLoaded}ms, loadComplete=${loadComplete}ms`)

    // 检查页面标题
    const title = await page.title()
    expect(title).toBe('CodingMatrix')
  })

  test('访问 /agent 页面应该正常加载', async ({ page }) => {
    test.slow()

    await page.goto(`${ONLINE_URL}/agent`)
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // 截图
    await page.screenshot({ path: 'test-results/online-preview-agent.png', fullPage: true })

    // 检查 Agent 页面元素
    const hasAgentPage = await page.locator('.agent-page').count()
    expect(hasAgentPage).toBeGreaterThan(0)

    // 检查 CSS 样式是否正确应用
    const agentStyles = await page.evaluate(() => {
      const agentPage = document.querySelector('.agent-page')
      if (!agentPage) return null
      const styles = window.getComputedStyle(agentPage)
      return {
        display: styles.display,
        height: styles.height,
        backgroundColor: styles.backgroundColor,
      }
    })

    expect(agentStyles).not.toBeNull()
    expect(agentStyles.display).toBe('flex')
  })

  test('登录后 /agent 页面 token 应该正常工作', async ({ page }) => {
    test.slow()

    // 先进行 API 登录
    await apiLogin(page, ONLINE_URL)
    await page.waitForTimeout(1000)

    // 访问 agent 页面
    await page.goto(`${ONLINE_URL}/agent`)
    await page.waitForLoadState('load')
    await page.waitForTimeout(2000)

    // 截图
    await page.screenshot({ path: 'test-results/online-preview-agent-logged.png', fullPage: true })

    // 检查 token 是否正确传递
    const tokenInfo = await page.evaluate(() => {
      return {
        sessionToken: sessionStorage.getItem('_token'),
        localToken: localStorage.getItem('access_token'),
        userStoreToken: window.userStore?.getAccessToken(),
        isLoggedIn: window.userStore?.isLoggedIn,
      }
    })

    console.log('Token info after login on online URL:', JSON.stringify(tokenInfo, null, 2))

    expect(tokenInfo.isLoggedIn).toBeTruthy()
  })
})
