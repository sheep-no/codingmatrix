const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

/**
 * 多模态能力与 Agent 流程跟踪
 *
 * 说明：旧的 /api/v1/agent/process(/stream) 与 /agent/stats/models 端点已下线，
 * 多模态能力统一落在 /api/v1/vision/* 与能力中心页面。
 */

test.describe('多模态 Agent 性能和流程跟踪测试', () => {
  test.describe.configure({ project: 'chromium' })

  test.beforeEach(async ({ page }) => {
    await apiLogin(page)
  })

  test('视觉能力接口鉴权与参数校验', async ({ page }) => {
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    )
    const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

    const analyze = await page.request.post('/api/v1/vision/analyze', {
      headers,
      data: {},
    })
    // 空参数应被 422/400 拒绝，说明路由存在且已鉴权
    expect([400, 422]).toContain(analyze.status())

    const ocr = await page.request.post('/api/v1/vision/ocr', {
      headers,
      data: {},
    })
    expect([400, 422]).toContain(ocr.status())
  })

  test('能力中心视觉面板渲染上传与提示词控件', async ({ page }) => {
    await page.goto('/capabilities', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '能力中心' })).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.drop-zone input[type="file"]')).toBeVisible()
    await expect(page.getByPlaceholder('例如：描述图片中的布局、文字和颜色')).toBeVisible()
  })

  test('Agent 会话接口可用且返回数组', async ({ page }) => {
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    )
    const response = await page.request.get('/api/v1/agent/sessions', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(response.ok()).toBeTruthy()
    const sessions = await response.json()
    expect(Array.isArray(sessions) || Array.isArray(sessions.sessions)).toBeTruthy()
  })

  test('Agent 页面可跟踪请求并提供流程面板', async ({ page }) => {
    const apiCalls = []
    page.on('request', request => {
      if (request.url().includes('/api/v1/agent/')) {
        apiCalls.push({ method: request.method(), url: request.url() })
      }
    })

    await page.goto('/agent', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.agent-page')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.agent-workspace')).toBeVisible()
    await expect(page.locator('.agent-sidebar')).toContainText('会话历史')
    expect(apiCalls.length).toBeGreaterThan(0)
    expect(apiCalls.every(call => call.url.startsWith('http'))).toBeTruthy()
  })
})
