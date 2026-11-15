const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

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
  'data: {"type":"progress","data":{"phase":"generation_start","step":"准备生成","percentage":10}}',
  '',
  'data: {"type":"file","path":"calculator.py","content":"print(1)","line_count":1,"file_size":9}',
  '',
  'data: {"type":"done","data":{"project_path":"e2e-calculator"}}',
  '',
].join('\n')

test('Agent 项目生成 - 验证请求参数和响应', async ({ page }) => {
  await page.addInitScript(keys => {
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify(keys))
  }, MOCK_KEYS)

  await apiLogin(page)

  const generateCalls = []
  page.on('request', request => {
    if (request.url().includes('/agent/orchestrate/stream') && request.method() === 'POST') {
      generateCalls.push({
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
  await prompt.fill('创建一个简单的 Python Flask Hello World 项目')

  await page.getByRole('button', { name: '发送需求' }).click()

  await expect.poll(() => generateCalls.length, { timeout: 15000 }).toBeGreaterThan(0)

  const call = generateCalls[0]
  expect(call.authorization).toMatch(/^Bearer .+/)

  const body = JSON.parse(call.body)
  expect(body.requirement).toContain('Flask Hello World')
  expect(body.session_id).toBeTruthy()
  // 默认设置开启代码审查与记忆增强，请求必须如实传递
  expect(body.enable_review).toBe(true)
  expect(body.enable_memory).toBe(true)

  // 生成结束后工作区执行过程应出现 SSE 推送的文件
  await expect(page.locator('.agent-workspace')).toContainText('calculator.py', { timeout: 15000 })
})
