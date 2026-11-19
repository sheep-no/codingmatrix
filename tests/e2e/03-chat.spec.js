/**
 * 聊天交互 E2E 测试
 * 覆盖: 发送消息、流式响应、停止生成、消息编辑、消息复制、会话管理
 *
 * 所有用例通过 page.route 回放后端 SSE，不依赖真实模型额度。
 */
import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

const CONVERSATION_ID = 88001
const REPLY_MARKDOWN = '这是 E2E 回放的回复。\n\n```js\nconst answer = 42\n```\n'

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

async function mockHistory(page, items = []) {
  await page.route('**/api/v1/history', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ items, total: items.length }),
  }))
}

const sendInput = page => page.getByRole('textbox', { name: '消息输入框' })
const sendButton = page => page.getByRole('button', { name: '发送消息' })

async function sendMessage(page, text) {
  const textarea = sendInput(page)
  await expect(textarea).toBeVisible()
  await textarea.fill(text)
  await sendButton(page).click()
}

function historyItem(id, title) {
  return {
    id,
    conversation_id: id,
    title,
    prompt: title,
    created_at: '2026-11-01T10:00:00Z',
  }
}

test.describe('聊天交互', () => {
  test.beforeEach(async ({ page }) => {
    await seedMockApiKey(page)
    await apiLogin(page)
  })

  test('发送消息 - 输入并点击发送', async ({ page }) => {
    const requests = await mockChatStream(page)
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const textarea = sendInput(page)
    await expect(textarea).toBeVisible()
    await expect(sendButton(page)).toBeDisabled()

    await sendMessage(page, 'Hello test message')

    await expect(page.locator('.message-user .user-text')).toContainText('Hello test message')
    await expect.poll(() => requests.length).toBe(1)
    expect(requests[0]).toMatchObject({ prompt: 'Hello test message', stream: true })
  })

  test('发送消息 - 键盘 Ctrl+Enter 发送', async ({ page }) => {
    const requests = await mockChatStream(page)
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const textarea = sendInput(page)
    await textarea.fill('Keyboard test')
    await textarea.press('Control+Enter')

    await expect(page.locator('.message-user .user-text')).toContainText('Keyboard test')
    await expect.poll(() => requests.length).toBe(1)
  })

  test('流式响应 - 接收 AI 回复', async ({ page }) => {
    await mockChatStream(page)
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Please respond to this test')

    const aiMessage = page.locator('.message-ai').first()
    await expect(aiMessage.locator('.card-content')).toContainText('这是 E2E 回放的回复', { timeout: 15000 })
    await expect(aiMessage).not.toHaveClass(/streaming/)
  })

  test('停止生成 - 停止按钮应可见并可点击', async ({ page }) => {
    // 挂起 SSE 响应，保持生成中状态直到用户点击停止
    let pendingRoute = null
    await page.route('**/api/v1/chat', route => {
      pendingRoute = route
    })
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Write a long response so I can stop it')

    const stopBtn = page.getByRole('button', { name: '停止输出' })
    await expect(stopBtn).toBeVisible({ timeout: 15000 })
    await expect.poll(() => pendingRoute !== null).toBe(true)
    await stopBtn.click()

    await expect(stopBtn).toHaveCount(0)
    await pendingRoute.abort().catch(() => {})
  })

  test('新建会话 - 清空当前对话', async ({ page }) => {
    await mockChatStream(page)
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Message in current session')
    await expect(page.locator('.message-ai .card-content')).toContainText('这是 E2E 回放的回复')

    await page.getByRole('button', { name: '新建会话' }).click()

    await expect(page.getByRole('region', { name: '对话待机画面' })).toBeVisible()
    await expect(page.locator('.message-user')).toHaveCount(0)
    await expect(page.locator('.message-ai')).toHaveCount(0)
  })

  test('历史会话 - 侧边栏应显示历史记录', async ({ page }) => {
    await mockChatStream(page)
    await mockHistory(page, [historyItem(70001, '历史会话样例')])
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const historyItemLocator = page.locator('#leftlist .history-item').first()
    await expect(historyItemLocator).toBeVisible({ timeout: 15000 })
    await expect(historyItemLocator).toContainText('历史会话样例')
    await expect(page.locator('#leftlist .empty-state')).toHaveCount(0)
  })

  test('历史会话切换 - 点击历史项应加载对话', async ({ page }) => {
    await mockChatStream(page)
    await mockHistory(page, [historyItem(70002, '待切换的会话')])
    await page.route('**/api/v1/history/70002', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        conversation_id: 70002,
        messages: [
          { role: 'user', content: '历史里的用户消息', created_at: '2026-11-01T10:00:00Z' },
          { role: 'assistant', content: '历史里的助手回复', created_at: '2026-11-01T10:00:05Z' },
        ],
      }),
    }))
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await page.locator('#leftlist .history-item').first().click()

    await expect(page.locator('.history-item.active')).toHaveCount(1)
  })

  test('消息编辑 - 编辑并重新发送', async ({ page }) => {
    const requests = await mockChatStream(page)
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, 'Original message')
    await expect(page.locator('.message-ai .card-content')).toContainText('这是 E2E 回放的回复')

    await page.locator('.message-user .message-action-btn').first().click()

    const editor = page.locator('.message-editor .editor-textarea')
    await expect(editor).toBeVisible()
    await expect(editor).toHaveValue('Original message')

    await editor.fill('Edited message')
    await page.locator('.message-editor .btn-save').click()
    await expect(editor).toHaveCount(0)

    await expect(page.locator('.message-user .user-text').last()).toContainText('Edited message')
    await expect.poll(() => requests.length).toBe(2)
    expect(requests[1]).toMatchObject({ prompt: 'Edited message' })
  })

  test('消息复制 - 点击复制按钮', async ({ page }) => {
    await mockChatStream(page)
    await mockHistory(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await sendMessage(page, '给我一段代码')

    const copyButton = page.locator('.message-ai .copy-button').first()
    await expect(copyButton).toBeVisible({ timeout: 15000 })
    await copyButton.click()
    await expect(copyButton).toContainText('已复制')
  })

  test('加载更多历史 - 分页加载', async ({ page }) => {
    await mockChatStream(page)
    const manyItems = Array.from({ length: 4 }, (_, i) => historyItem(71000 + i, `会话 ${i + 1}`))
    await mockHistory(page, manyItems)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await expect(page.locator('#leftlist .history-item')).toHaveCount(4)
    await expect(page.locator('#leftlist .history-item').first()).toContainText('会话 1')
  })

  test('删除会话 - 删除历史会话', async ({ page }) => {
    await mockChatStream(page)
    await mockHistory(page, [historyItem(72001, '待删除的会话')])
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const item = page.locator('#leftlist .history-item').first()
    await expect(item).toBeVisible({ timeout: 15000 })

    // 记录删除请求并清空列表，避免依赖后端真实删除
    let deletedId = null
    await page.route('**/code/history**', async route => {
      if (route.request().method() === 'DELETE') {
        deletedId = route.request().url()
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) })
    })

    await item.getByRole('button', { name: '删除会话' }).click()
    // 二次确认弹窗
    await page.getByRole('button', { name: '确定' }).click()
    await expect.poll(() => deletedId).toContain('72001')
    await expect(page.locator('#leftlist .history-item')).toHaveCount(0)
    await expect(page.locator('#leftlist .empty-state')).toContainText('暂无历史记录')
  })
})
