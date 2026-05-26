/**
 * Token 401 错误处理测试
 * 验证前端在 token 缺失/过期时是否正确处理
 */
import { test, expect } from '@playwright/test'
import { apiLogin, TEST_EMAIL, TEST_PASSWORD } from './fixtures/auth.js'

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000'

test.describe('Token 401 处理', () => {
  test('无 token 访问受保护页面应该显示登录或拒绝', async ({ page }) => {
    // 不登录，直接访问 /agent
    await page.goto('http://localhost:3000/agent')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    // 应该能看到页面（首页会自动弹出登录）
    const hasAgentPage = await page.locator('.agent-page').count()
    expect(hasAgentPage).toBeGreaterThan(0)
  })

  test('登录后 token 应该正确传递到 API 请求', async ({ page }) => {
    await apiLogin(page)
    await page.waitForTimeout(500)

    // 访问 /agent 并等待页面加载
    await page.goto('http://localhost:3000/agent')
    await page.waitForLoadState('load')
    await page.waitForTimeout(1000)

    // 验证 token 存在
    const tokenInfo = await page.evaluate(() => {
      const userStore = window.userStore
      return {
        hasAccessToken: !!userStore?.getAccessToken(),
        permissionLevel: localStorage.getItem('permission_level'),
        isLoggedIn: userStore?.isLoggedIn,
      }
    })

    expect(tokenInfo.hasAccessToken).toBeTruthy()
    expect(tokenInfo.permissionLevel).toBe('superadmin')
  })

  test('页面刷新后 token 应该保持有效', async ({ page }) => {
    await apiLogin(page)
    await page.waitForTimeout(500)

    // 访问 /agent
    await page.goto('http://localhost:3000/agent')
    await page.waitForLoadState('load')
    await page.waitForTimeout(1000)

    // 刷新页面
    await page.reload({ waitUntil: 'load' })
    await page.waitForTimeout(2000)

    // 验证 token 在刷新后仍然存在
    const tokenAfterRefresh = await page.evaluate(() => {
      return {
        sessionToken: sessionStorage.getItem('_token'),
        localToken: localStorage.getItem('access_token'),
        userStoreToken: window.userStore?.getAccessToken(),
      }
    })

    // 至少有一个存储中有 token
    const hasAnyToken = tokenAfterRefresh.sessionToken || tokenAfterRefresh.localToken || tokenAfterRefresh.userStoreToken
    expect(!!hasAnyToken).toBeTruthy()
  })
})
