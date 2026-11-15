const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

async function authGet(page, url) {
  const token = await page.evaluate(
    () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
  )
  const response = await page.request.get(url, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.ok()).toBeTruthy()
  return response.json()
}

test.describe('模型管理功能测试', () => {
  test.setTimeout(60000)

  test('1. Agent 模型配置包含降级链', async ({ page }) => {
    await apiLogin(page)
    const config = await authGet(page, '/api/v1/models/agent-config')
    const modelIds = Object.keys(config.models)

    expect(Array.isArray(config.fallback_chain)).toBeTruthy()
    expect(config.fallback_chain.length).toBeGreaterThan(0)
    for (const modelId of config.fallback_chain) {
      expect(modelIds).toContain(modelId)
    }
  })

  test('2. Agent 模型配置包含错误类型映射', async ({ page }) => {
    await apiLogin(page)
    const config = await authGet(page, '/api/v1/models/agent-config')
    const modelIds = Object.keys(config.models)

    const errorTypes = ['NameError', 'AttributeError', 'ImportError', 'SyntaxError']
    for (const errorType of errorTypes) {
      expect(config.error_type_models).toHaveProperty(errorType)
      expect(modelIds).toContain(config.error_type_models[errorType])
    }
  })

  test('3. 统一模型配置接口返回模型清单', async ({ page }) => {
    await apiLogin(page)
    const data = await authGet(page, '/api/v2/model-config/models')

    expect(data.success).toBe(true)
    expect(Array.isArray(data.models)).toBeTruthy()
    expect(data.models.length).toBeGreaterThan(0)

    const ids = data.models.map(model => model.id)
    for (const modelId of ['bge-m3', 'bge-reranker', 'bge-large-zh', 'sense-voice', 'hunyuan-mt']) {
      expect(ids).toContain(modelId)
    }

    for (const model of data.models) {
      expect(model).toHaveProperty('is_free')
      expect(model).toHaveProperty('max_context')
      expect(model).toHaveProperty('cost_per_1m_input')
    }
    const freeModels = data.models.filter(model => model.is_free)
    expect(freeModels.length).toBeGreaterThan(0)
    for (const model of freeModels) {
      expect(model.cost_per_1m_input).toBe(0)
    }
  })
})
