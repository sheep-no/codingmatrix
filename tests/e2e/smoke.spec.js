// @ts-check
import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

/**
 * Playwright E2E 冒烟测试
 * 验证基础页面结构和可访问性。
 * 前后端服务是执行前提：服务不可用时直接失败，避免 catch-all skip 让门禁失效。
 */

test.describe('基础页面结构', () => {
  test('首页应该可以访问', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.main-layout')).toBeVisible()
  })

  test('页面应该有标题元素', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('domcontentloaded')
    await expect(page).toHaveTitle(/CodingMatrix/)
  })
})

test.describe('API 连接测试', () => {
  test('前端文档中心应该可以访问', async ({ page }) => {
    await apiLogin(page)
    await page.goto('/docs')
    await page.waitForLoadState('domcontentloaded')

    // 前端 /docs 是文档中心页面，Swagger UI 在后端 8000/docs
    await expect(page.locator('.docs-page')).toBeVisible()
    await expect(page.locator('.hero-heading')).toHaveText(/CodingMatrix/)
  })

  test('API 健康检查', async ({ request }) => {
    const response = await request.get('/api/v1/health')
    expect(response.ok()).toBeTruthy()
    expect(await response.json()).toMatchObject({
      status: 'healthy',
      timestamp: expect.any(String),
    })
  })
})

test.describe('认证流程', () => {
  test('登录入口应该可以打开登录弹窗', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.clear()
      sessionStorage.clear()
    })
    await page.reload()
    await page.waitForLoadState('domcontentloaded')

    await page.locator('.login-btn').click()
    const dialog = page.locator('.login-modal .login-form')
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('input[type="email"]')).toBeVisible()
    await expect(dialog.locator('input[type="password"]')).toBeVisible()
  })
})
