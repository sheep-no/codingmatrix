import { test, expect } from '@playwright/test'

const EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || '12345678'

async function loginOnFrontend(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  const login = await page.evaluate(async ({ email, password }) => {
    const csrfResp = await fetch('/api/v1/csrf-token', { credentials: 'include' })
    const csrfData = await csrfResp.json()
    const loginResp = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfData.csrf_token,
      },
      body: JSON.stringify({ email, password }),
    })
    const data = await loginResp.json().catch(() => ({}))
    if (!loginResp.ok || !data.access_token) {
      return { ok: false, status: loginResp.status, detail: data.detail || data.message || '' }
    }
    const expiry = Date.now() + 3600000
    sessionStorage.setItem('_token', data.access_token)
    sessionStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('username', data.username || email)
    localStorage.setItem('email', email)
    localStorage.setItem('permission_level', data.permission_level || 'superadmin')
    localStorage.setItem('user-store', JSON.stringify({
      isLoggedIn: true,
      username: data.username || email,
      email,
      permissionLevel: data.permission_level || 'superadmin',
    }))
    return { ok: true, status: loginResp.status }
  }, { email: EMAIL, password: PASSWORD })
  expect(login.ok, `login failed: ${JSON.stringify(login)}`).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
}

async function syncSiliconflowKeys(page) {
  const keySync = await page.evaluate(async () => {
    const token = sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    const resp = await fetch('/api/v1/agent/apikeys', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await resp.json().catch(() => [])
    const list = Array.isArray(data) ? data : []
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify(list))
    return { status: resp.status, count: list.length }
  })
  expect(keySync.status).toBe(200)
  expect(keySync.count, '需要至少一条已配置的硅基流动 Key').toBeGreaterThan(0)
}

async function openVirtualGirl(page) {
  await page.locator('#toolkit').click()
  const menu = page.locator('#toolkit-menu')
  await expect(menu).toBeVisible()
  await menu.getByText('虚拟姬', { exact: true }).click()
  const girlWindow = page.locator('.virtual-girl-window')
  await expect(girlWindow).toBeVisible({ timeout: 15000 })
  return girlWindow
}

test.describe('虚拟姬浏览器场景', () => {
  test.describe.configure({ mode: 'serial' })
  test.use({ viewport: { width: 1400, height: 900 } })

  test('空发送、切角色、关创建框、最小化、关窗后刷新保持关闭', async ({ page }) => {
    test.setTimeout(90000)
    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const girlWindow = await openVirtualGirl(page)
    await expect(girlWindow.locator('.chat-input')).toBeVisible()
    await expect(girlWindow.locator('.send-button')).toBeDisabled()

    await girlWindow.locator('.character-select').selectOption('lively')
    await expect(girlWindow.locator('.title-text')).toHaveText('元气少女')
    await expect(girlWindow.locator('.message.assistant .message-content').last()).toBeVisible()

    await girlWindow.locator('.add-character-btn').click()
    const form = girlWindow.locator('.character-form-overlay')
    await expect(form).toBeVisible()
    await form.click({ position: { x: 8, y: 8 } })
    await expect(form).toHaveCount(0)

    await girlWindow.locator('.add-character-btn').click()
    await expect(girlWindow.locator('.character-form-overlay')).toBeVisible()
    await girlWindow.locator('.form-cancel').click()
    await expect(girlWindow.locator('.character-form-overlay')).toHaveCount(0)

    await girlWindow.locator('.control-btn[title="最小化"]').click()
    await expect(girlWindow.locator('.window-content')).toHaveClass(/minimized-content/)
    await girlWindow.locator('.control-btn[title="最小化"]').click()
    await expect(girlWindow.locator('.chat-input')).toBeVisible()

    await girlWindow.locator('.close-btn').click()
    await expect(page.locator('.virtual-girl-window')).toHaveCount(0)

    const storedClosed = await page.evaluate(() => {
      const raw = localStorage.getItem('navigationState')
      return raw ? JSON.parse(raw).showVirtualGirl : null
    })
    expect(storedClosed).toBe(false)

    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.locator('.virtual-girl-window')).toHaveCount(0, { timeout: 10000 })
  })

  test('真实回答后刷新仍能看到对话，途中关窗可再打开', async ({ page }) => {
    test.setTimeout(240000)
    let delayNextTurn = false
    await page.route('**/api/v1/GirlAi/companion/turn', async (route) => {
      if (delayNextTurn) {
        await new Promise((resolve) => setTimeout(resolve, 8000))
      }
      await route.continue()
    })

    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const girlWindow = await openVirtualGirl(page)
    const prompt = `E2E虚拟姬刷新 ${Date.now()}，请用一句话确认收到`
    await girlWindow.locator('.chat-input').fill(prompt)
    await expect(girlWindow.locator('.send-button')).toBeEnabled()
    await girlWindow.locator('.send-button').click()
    await expect(girlWindow.locator('.message.user .message-content').filter({ hasText: prompt })).toBeVisible()
    await expect(girlWindow.locator('.typing')).toHaveCount(0, { timeout: 120000 })

    const reply = girlWindow.locator('.message.assistant .message-content').last()
    await expect(reply).toBeVisible()
    const replyText = (await reply.innerText()).trim()
    expect(replyText).toMatch(/\S/)
    expect(replyText.includes('网络错误')).toBe(false)

    await page.reload({ waitUntil: 'domcontentloaded' })
    const restored = page.locator('.virtual-girl-window')
    await expect(restored).toBeVisible({ timeout: 15000 })
    await expect(restored.locator('.message.user .message-content').filter({ hasText: prompt })).toBeVisible({ timeout: 20000 })

    delayNextTurn = true
    const midPrompt = `E2E途中关闭 ${Date.now()}`
    await restored.locator('.chat-input').fill(midPrompt)
    await restored.locator('.send-button').click()
    await expect(restored.locator('.message.user .message-content').filter({ hasText: midPrompt })).toBeVisible()
    await expect(restored.locator('.typing')).toBeVisible({ timeout: 5000 })
    await restored.locator('.close-btn').click()
    await expect(page.locator('.virtual-girl-window')).toHaveCount(0)

    const reopened = await openVirtualGirl(page)
    await expect(reopened.locator('.chat-input')).toBeVisible()
    await expect(reopened.locator('.chat-input')).toBeEnabled()
    await expect(reopened.locator('.typing')).toHaveCount(0)
    await expect(reopened.locator('.message.user .message-content').filter({ hasText: midPrompt })).toBeVisible({ timeout: 20000 })
  })
})
