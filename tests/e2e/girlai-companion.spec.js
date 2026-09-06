import { test, expect } from '@playwright/test'

test.use({ baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000' })

const companionState = revision => ({
  conversation_id: 'e2e-conversation',
  state_revision: revision,
  emotion: { label: revision >= 7 ? 'focused' : 'neutral', intensity: 0.6, confidence: 0.9 },
  intent: { label: 'chat', confidence: 0.9 },
  response_style: 'standard',
  degraded_capabilities: ['voice_output']
})

async function seedAuthenticatedPage(page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('_token', 'e2e-token')
    sessionStorage.setItem('_token_expiry', String(Date.now() + 3600000))
    localStorage.setItem('access_token', 'e2e-token')
    localStorage.setItem('username', 'e2e-user')
    localStorage.setItem('email', 'e2e@example.com')
    localStorage.setItem('permission_level', 'normal')
    localStorage.setItem('user-store', JSON.stringify({
      isLoggedIn: true,
      username: 'e2e-user',
      email: 'e2e@example.com',
      permissionLevel: 'normal'
    }))
  })
}

async function mockCompanionApis(page, stateHandler) {
  await page.route('**/api/v1/**', async route => {
    await route.fulfill({ json: {} })
  })
  await page.route('**/api/v1/GirlAi/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname

    if (path.endsWith('/companion/state')) {
      await route.fulfill({ json: await stateHandler() })
      return
    }
    if (path.endsWith('/memories')) {
      await route.fulfill({ json: { memories: [] } })
      return
    }
    if (path.endsWith('/characters/custom/list')) {
      await route.fulfill({ json: { characters: [] } })
      return
    }
    if (path.endsWith('/history')) {
      await route.fulfill({ json: { messages: [], total: 0 } })
      return
    }
    await route.continue()
  })
}

async function openCompanion(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  const toolkit = page.getByRole('button', { name: /^工具集/ })
  await expect(toolkit).toBeVisible({ timeout: 30000 })
  await toolkit.click()
  const launcher = page.getByText('虚拟姬', { exact: true }).first()
  if (!(await launcher.isVisible({ timeout: 15000 }).catch(() => false))) {
    throw new Error(`伙伴入口未渲染，当前页面文本：${(await page.locator('body').innerText()).slice(0, 1000)}`)
  }
  await launcher.click()
  await expect(page.locator('.virtual-girl-window')).toBeVisible()
}

test.describe('GirlAI 伙伴交互', () => {
  test('页面重载后从伙伴状态接口恢复最新 revision 和降级状态', async ({ page }) => {
    let revision = 6
    await seedAuthenticatedPage(page)
    await mockCompanionApis(page, () => companionState(revision))

    await openCompanion(page)
    await expect(page.locator('.companion-emotion')).toHaveText('neutral')
    await expect(page.locator('.companion-degraded')).toHaveText('文字模式')

    revision = 7
    await openCompanion(page)
    await expect(page.locator('.companion-emotion')).toHaveText('focused')
  })

  test('旧 revision 响应不会覆盖当前伙伴状态', async ({ page }) => {
    let calls = 0
    await seedAuthenticatedPage(page)
    await mockCompanionApis(page, async () => {
      calls += 1
      return companionState(calls === 1 ? 7 : 6)
    })

    await openCompanion(page)
    await expect(page.locator('.companion-emotion')).toHaveText('focused')

    const stateResponse = await page.evaluate(async () => {
      const response = await fetch('/api/v1/GirlAi/companion/state')
      return response.json()
    })
    expect(stateResponse.state_revision).toBe(6)
    await expect(page.locator('.companion-emotion')).toHaveText('focused')
  })

  test('伙伴异步状态更新保持文字主链路可用', async ({ page }) => {
    await seedAuthenticatedPage(page)
    await mockCompanionApis(page, () => companionState(8))
    await page.route('**/api/v1/GirlAi/companion/turn', async route => {
      await route.fulfill({
        json: {
          ...companionState(9),
          assistant_text: '我在这里，先陪你聊聊。',
          memory_candidates: []
        }
      })
    })

    await openCompanion(page)
    const window = page.locator('.virtual-girl-window')
    const input = window.locator('.chat-input')
    await input.fill('今天有点累')
    await expect(window.locator('.send-button')).toBeEnabled()
    await window.locator('.send-button').click()
    await expect(window.locator('.message.assistant .message-content').last()).toHaveText('我在这里，先陪你聊聊。')
    await expect(window.locator('.companion-emotion')).toHaveText('focused')
  })
})
