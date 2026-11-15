const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

/**
 * 多模型能力入口 E2E 测试
 *
 * AI 云助手弹窗已下线，/aicloud 重定向到能力中心；
 * 多模型相关能力统一由 /capabilities 承载。
 */

test.describe('多模型能力入口', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page)
  })

  test('01 - /aicloud 重定向到能力中心', async ({ page }) => {
    await page.goto('/aicloud', { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/capabilities/)
    await expect(page.getByRole('heading', { name: '能力中心' })).toBeVisible({ timeout: 30000 })
  })

  test('02 - 工具集不再提供 AI 云助手入口', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.locator('#toolkit').click()
    const menu = page.locator('#toolkit-menu')
    await expect(menu).toBeVisible()
    await expect(menu.locator('.toolkit-item', { hasText: 'AI 云助手' })).toHaveCount(0)
    await expect(menu.locator('.toolkit-item', { hasText: '能力' })).toBeVisible()
  })

  test('03 - 能力中心标签页完整', async ({ page }) => {
    await page.goto('/capabilities', { waitUntil: 'domcontentloaded' })
    const expectedTabs = [
      '视觉工具',
      '知识库',
      '代码沙箱',
      'Skills/技能',
      'Agent Host/主机会话',
    ]
    for (const label of expectedTabs) {
      await expect(page.getByRole('tab', { name: new RegExp(label) })).toBeVisible()
    }
  })

  test('04 - 模型列表接口可用', async ({ page }) => {
    // page.request 不共享 localStorage，需显式带上登录 token
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    )
    const response = await page.request.get('/api/v1/aicloud/models', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(Array.isArray(data.models)).toBeTruthy()
    expect(data.models.length).toBeGreaterThan(0)
  })

  test('05 - 视觉工具上传控件可见', async ({ page }) => {
    await page.goto('/capabilities', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.drop-zone input[type="file"]')).toBeVisible()
    await expect(page.getByPlaceholder('例如：描述图片中的布局、文字和颜色')).toBeVisible()
  })

  test('06 - 切换到 Skills 面板按需加载', async ({ page }) => {
    let skillRequests = 0
    page.on('request', request => {
      if (request.url().includes('/api/v1/skills/list')) skillRequests += 1
    })

    await page.goto('/capabilities', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '能力中心' })).toBeVisible({ timeout: 30000 })
    expect(skillRequests).toBe(0)

    await page.getByRole('tab', { name: /Skills\/技能/ }).click()
    await expect(page.getByRole('heading', { name: 'Skills/技能' })).toBeVisible()
    expect(skillRequests).toBeGreaterThan(0)
  })
})
