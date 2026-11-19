const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

const REPLY_MARKDOWN = '这是来自 E2E 的模拟回复。\n\n```js\nconst answer = 42\n```\n'
const CONVERSATION_ID = 99001

/**
 * 首页对话用例全部用 page.route 回放后端 SSE，不依赖真实模型额度。
 * 断言以真实 DOM（.message-user / .message-ai / .history-item）为准。
 */
async function mockChatStream(page, { conversationId = CONVERSATION_ID, content = REPLY_MARKDOWN } = {}) {
  const requests = []
  await page.route('**/api/v1/chat', async route => {
    requests.push(JSON.parse(route.request().postData() || '{}'))
    const events = [
      { choices: [{ delta: { content } }] },
      { conversation_id: conversationId },
    ]
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''),
    })
  })
  return requests
}

async function seedMockApiKey(page) {
  await page.addInitScript(() => {
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify([{
      token: 'e2e-mock-siliconflow-token',
      provider: 'siliconflow',
      status: 'verified',
      enabled: true,
      expires_at: new Date(Date.now() + 3600000).toISOString(),
    }]))
  })
}

async function sendMessage(page, text) {
  const textarea = page.getByRole('textbox', { name: '消息输入框' })
  await expect(textarea).toBeVisible()
  await textarea.fill(text)
  await page.getByRole('button', { name: '发送消息' }).click()
}

test.describe('Chat E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await seedMockApiKey(page)
    await apiLogin(page)
    await page.route('**/api/v1/history', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0 }),
    }))
  })

  test('发送消息测试 - 输入并发送消息', async ({ page }) => {
    const requests = await mockChatStream(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Hello, this is a test message')

    await expect(page.locator('.message-user')).toHaveCount(1)
    await expect(page.locator('.message-user .user-text')).toContainText('Hello, this is a test message')
    await expect.poll(() => requests.length).toBe(1)
    expect(requests[0]).toMatchObject({ prompt: 'Hello, this is a test message', stream: true })
  })

  test('流式响应测试 - 应能接收流式响应', async ({ page }) => {
    await mockChatStream(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Test streaming response')

    const aiMessage = page.locator('.message-ai').first()
    await expect(aiMessage.locator('.card-content')).toContainText('这是来自 E2E 的模拟回复', { timeout: 15000 })
    await expect(aiMessage).not.toHaveClass(/streaming/)
  })

  test('新建会话测试 - 创建新聊天会话', async ({ page }) => {
    await mockChatStream(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Create a session')
    await expect(page.locator('.message-ai .card-content')).toContainText('这是来自 E2E 的模拟回复')

    await page.getByRole('button', { name: '新建会话' }).click()

    await expect(page.getByRole('region', { name: '对话待机画面' })).toBeVisible()
    await expect(page.locator('.message-user')).toHaveCount(0)
    await expect(page.locator('.message-ai')).toHaveCount(0)
  })

  test('历史记录加载测试 - 应加载历史会话列表', async ({ page }) => {
    await page.route('**/api/v1/history', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          id: 1,
          conversation_id: 70001,
          title: '历史会话样例',
          prompt: '历史会话样例',
          created_at: '2026-11-01T10:00:00Z',
        }],
        total: 1,
      }),
    }))

    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const historyItem = page.locator('#leftlist .history-item').first()
    await expect(historyItem).toBeVisible({ timeout: 15000 })
    await expect(historyItem).toContainText('历史会话样例')
  })

  test('消息编辑测试 - 编辑已发送的消息', async ({ page }) => {
    await mockChatStream(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Original message')
    await expect(page.locator('.message-ai .card-content')).toContainText('这是来自 E2E 的模拟回复')

    await page.locator('.message-user .message-action-btn').first().click()

    const editor = page.locator('.message-editor .editor-textarea')
    await expect(editor).toBeVisible()
    await expect(editor).toHaveValue('Original message')

    await editor.fill('Edited message')
    await page.locator('.message-editor .btn-save').click()
    await expect(editor).toHaveCount(0)
  })

  test('消息复制测试 - 复制 AI 响应内容', async ({ page }) => {
    await mockChatStream(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, '给我一段代码')

    const copyButton = page.locator('.message-ai .copy-button').first()
    await expect(copyButton).toBeVisible({ timeout: 15000 })
    await copyButton.click()
    await expect(copyButton).toContainText('已复制')
  })
})
