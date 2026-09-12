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
      return {
        ok: false,
        status: loginResp.status,
        detail: data.detail || data.message || '',
      }
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
    return { ok: true, status: loginResp.status, username: data.username }
  }, { email: EMAIL, password: PASSWORD })

  expect(login.ok, `login failed: ${JSON.stringify(login)}`).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(500)
  return login
}

test.describe('首页对话验收', () => {
  test('登录后 refresh/history 为 200，对话走 event-stream', async ({ page }) => {
    test.setTimeout(90000)
    const watched = []
    page.on('response', (response) => {
      const url = response.url()
      if (
        url.includes('/api/v1/refresh') ||
        url.includes('/api/v1/history') ||
        url.includes('/conversation/history') ||
        url.includes('/api/v1/chat')
      ) {
        watched.push({
          url,
          status: response.status(),
          type: response.headers()['content-type'] || '',
        })
      }
    })

    await loginOnFrontend(page)

    const historyStatus = await page.evaluate(async () => {
      const token = sessionStorage.getItem('_token') || localStorage.getItem('access_token')
      const resp = await fetch('/api/v1/history', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt_keyword: '', limit: 5, offset: 0 }),
      })
      return resp.status
    })
    expect(historyStatus).toBe(200)

    const refreshStatus = await page.evaluate(async () => {
      const csrfResp = await fetch('/api/v1/csrf-token', { credentials: 'include' })
      const csrfData = await csrfResp.json()
      const resp = await fetch('/api/v1/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfData.csrf_token,
        },
      })
      return resp.status
    })
    expect(refreshStatus).toBe(200)

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
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/$/)

    const textarea = page.locator('textarea.chat-input')
    await expect(textarea).toBeVisible({ timeout: 10000 })
    await textarea.fill('只用一个词回答：ping')

    const chatPromise = page.waitForResponse(
      (res) => res.url().includes('/api/v1/chat') && res.request().method() === 'POST',
      { timeout: 30000 }
    )
    await textarea.press('Control+Enter')
    const chatResponse = await chatPromise
    expect(chatResponse.status()).toBe(200)
    expect(chatResponse.headers()['content-type'] || '').toContain('text/event-stream')

    await expect(page.locator('.message-ai').first()).toBeVisible({ timeout: 45000 })

    const authFailures = watched.filter((item) => item.status === 401 || item.status === 403)
    expect(authFailures, JSON.stringify(authFailures)).toEqual([])
  })
})
