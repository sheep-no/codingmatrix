import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

/**
 * Agent 接口 Token 传递诊断
 *
 * 验证登录后 Agent 相关请求携带 Authorization 且不返回 401。
 * 真实生成依赖外部模型，这里只触发页面初始化请求。
 */
test('Agent 接口 Token 传递诊断', async ({ page }) => {
  const agentRequests = []

  page.on('response', response => {
    const url = response.url()
    if (!url.includes('/api/v1/agent')) return
    agentRequests.push({
      url,
      status: response.status(),
      method: response.request().method(),
      authorization: response.request().headers()['authorization'],
    })
  })

  await apiLogin(page)
  await page.goto('/agent', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.agent-page')).toBeVisible({ timeout: 30000 })
  await page.waitForTimeout(2000)

  expect(agentRequests.length).toBeGreaterThan(0)
  for (const request of agentRequests) {
    expect(request.status, `${request.method} ${request.url}`).not.toBe(401)
  }
  expect(agentRequests.some(request => Boolean(request.authorization))).toBeTruthy()
})
