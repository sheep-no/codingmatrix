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

test.describe('虚拟姬验收', () => {
  test.use({ viewport: { width: 1400, height: 900 } })

  test('工具集打开窗口后完成一轮真实伙伴对话', async ({ page }) => {
    test.setTimeout(180000)
    const apiLog = []
    page.on('response', (response) => {
      const url = response.url()
      if (url.includes('/api/v1/GirlAi')) {
        apiLog.push({
          url,
          status: response.status(),
          method: response.request().method(),
        })
      }
    })

    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const girlWindow = await openVirtualGirl(page)
    await expect(girlWindow.locator('.title-text')).toHaveText('温柔学姐')
    await expect(girlWindow.locator('.companion-status')).toBeVisible()
    await expect(girlWindow.locator('.chat-input')).toBeVisible()

    const prompt = `E2E虚拟姬验收 ${Date.now()}，请用一句话确认收到`
    await girlWindow.locator('.chat-input').fill(prompt)
    await expect(girlWindow.locator('.send-button')).toBeEnabled()
    await girlWindow.locator('.send-button').click()
    await expect(girlWindow.locator('.message.user .message-content').filter({ hasText: prompt })).toBeVisible()
    await expect(girlWindow.locator('.typing')).toHaveCount(0, { timeout: 120000 })

    const reply = girlWindow.locator('.message.assistant .message-content').last()
    await expect(reply).toBeVisible()
    const replyText = (await reply.innerText()).trim()
    expect(replyText, `assistant reply missing: ${JSON.stringify(apiLog)}`).toMatch(/\S/)
    expect(replyText).not.toContain('网络错误')
    await expect(girlWindow.locator('.title-status')).toHaveText('在线')

    const turnOk = apiLog.some((item) => (
      item.method === 'POST' && item.url.includes('/GirlAi/companion/turn') && item.status === 200
    ))
    expect(turnOk, `companion turn missing: ${JSON.stringify(apiLog)}`).toBeTruthy()

    const stateOk = apiLog.some((item) => (
      item.method === 'GET' && item.url.includes('/GirlAi/companion/state') && item.status === 200
    ))
    expect(stateOk, `companion state missing: ${JSON.stringify(apiLog)}`).toBeTruthy()
  })
})
