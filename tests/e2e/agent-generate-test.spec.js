const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

// 本地种子 Key：仅用于通过前端“必须配置 Key”的守卫，
// 真正的模型调用由 page.route 拦截，避免消耗真实额度。
const MOCK_KEYS = [{
  token: 'e2e-mock-siliconflow-token',
  provider: 'siliconflow',
  remark: 'E2E Mock Key',
  status: 'verified',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
  ttl_seconds: 86400,
  enabled: true,
}]

const SSE_BODY = [
  'data: {"type":"progress","data":{"phase":"generation_start","step":"准备生成","percentage":5}}',
  '',
  'data: {"type":"done","data":{"project_path":"e2e-mock-project"}}',
  '',
].join('\n')

test('验证 agent 项目生成接口请求参数正确', async ({ page }) => {
  await page.addInitScript(keys => {
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify(keys))
  }, MOCK_KEYS)

  await apiLogin(page)

  const apiCalls = []
  page.on('request', request => {
    if (request.url().includes('/api/v1/agent/') && request.method() === 'POST') {
      apiCalls.push({
        url: request.url(),
        body: request.postData(),
        authorization: request.headers()['authorization'],
      })
    }
  })

  await page.route('**/api/v1/agent/orchestrate/stream', route => route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
    body: SSE_BODY,
  }))

  await page.goto('/agent', { waitUntil: 'domcontentloaded' })
  const prompt = page.getByRole('textbox', { name: '项目需求' })
  await expect(prompt).toBeVisible({ timeout: 15000 })
  await prompt.fill('创建一个简单的 Python 计算器')

  const sendButton = page.getByRole('button', { name: '发送需求' })
  await expect(sendButton).toBeEnabled()
  await sendButton.click()

  await expect.poll(() => apiCalls.length, { timeout: 15000 }).toBeGreaterThan(0)

  const generateCall = apiCalls.find(call => call.url.includes('/agent/orchestrate/stream'))
  expect(generateCall).toBeTruthy()
  expect(generateCall.authorization).toMatch(/^Bearer .+/)

  const body = JSON.parse(generateCall.body)
  expect(body.requirement).toContain('Python 计算器')
  expect(body.session_id).toBeTruthy()
  expect(body).toHaveProperty('enable_review')
  expect(body).toHaveProperty('enable_memory')
})
