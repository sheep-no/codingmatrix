const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

const MOCK_KEYS = [{
  token: 'e2e-mock-siliconflow-token',
  provider: 'siliconflow',
  remark: 'E2E Mock Key',
  status: 'verified',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
  ttl_seconds: 604800,
  enabled: true,
}]

test.describe('Agent 多模型功能测试', () => {
  test.setTimeout(60000)

  test('1. 登录后 Agent 页面可用', async ({ page }) => {
    await page.addInitScript(keys => {
      localStorage.setItem('codingmatrix_apikeys', JSON.stringify(keys))
    }, MOCK_KEYS)
    await apiLogin(page)

    await page.goto('/agent', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('[data-testid="agent-prompt-input"]')).toBeVisible({ timeout: 15000 })
    await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible()
    await expect(page.locator('.agent-workspace')).toBeVisible()
    await expect(page.locator('.agent-file-panel')).toBeVisible()
  })

  test('2. 供应商列表接口返回数组', async ({ page }) => {
    await apiLogin(page)
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    )
    const response = await page.request.get('/api/v1/providers', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(response.ok()).toBeTruthy()
    const providers = await response.json()
    expect(Array.isArray(providers)).toBeTruthy()
  })

  test('3. Agent 模型配置返回角色与降级链', async ({ page }) => {
    await apiLogin(page)
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    )
    const response = await page.request.get('/api/v1/models/agent-config', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(response.ok()).toBeTruthy()

    const config = await response.json()
    const modelIds = Object.keys(config.models)
    for (const role of ['architect', 'frontend', 'backend', 'reviewer', 'fallback']) {
      expect(config.roles).toHaveProperty(role)
      // 角色必须指向 config.models 中真实存在的模型
      expect(modelIds).toContain(config.roles[role])
    }
    expect(Array.isArray(config.fallback_chain)).toBeTruthy()
    expect(config.fallback_chain.length).toBeGreaterThan(0)
    for (const modelId of config.fallback_chain) {
      expect(modelIds).toContain(modelId)
    }
    expect(modelIds).toContain(config.error_type_models.NameError)
  })

  test('4. 模型列表包含 Agent 主力模型', async ({ page }) => {
    await apiLogin(page)
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    )
    const response = await page.request.get('/api/v1/models/', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(response.ok()).toBeTruthy()

    const data = await response.json()
    const ids = data.models.map(model => model.id)
    for (const id of ['deepseek-r1', 'qwen3-8b', 'glm-z1-9b']) {
      expect(ids).toContain(id)
    }
    expect(data.models.length).toBeGreaterThan(0)
  })
})
