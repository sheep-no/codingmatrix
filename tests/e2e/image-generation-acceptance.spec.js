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

async function openImagePage(page) {
  await page.locator('#toolkit').click()
  const menu = page.locator('#toolkit-menu')
  await expect(menu).toBeVisible()
  const popupPromise = page.waitForEvent('popup', { timeout: 8000 }).catch(() => null)
  await menu.getByText('AI 绘画', { exact: true }).click()
  const popup = await popupPromise
  if (popup) {
    await popup.waitForLoadState('domcontentloaded')
    return popup
  }
  await page.goto('/image-generate', { waitUntil: 'domcontentloaded' })
  return page
}

test.describe('AI 绘画验收', () => {
  test('工具集进入后完成一轮真实文生图', async ({ page }) => {
    test.setTimeout(240000)
    const apiLog = []
    const trackKolors = (target) => {
      target.on('response', (response) => {
        const url = response.url()
        if (url.includes('/api/v1/kolors/')) {
          apiLog.push({
            url,
            status: response.status(),
            method: response.request().method(),
          })
        }
      })
    }
    trackKolors(page)

    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const imagePage = await openImagePage(page)
    trackKolors(imagePage)
    await expect(imagePage).toHaveURL(/image-generate/)
    await expect(imagePage.locator('.image-generate-page')).toBeVisible()
    await expect(imagePage.getByRole('button', { name: '文生图' })).toBeVisible()

    const prompt = `E2E文生图验收 ${Date.now()}，一只坐在窗边的橘猫，柔和自然光，写实`
    await imagePage.locator('#image-prompt').fill(prompt)
    await imagePage.locator('#image-resolution').selectOption('512x512')
    await expect(imagePage.locator('.btn-generate')).toBeEnabled()
    await imagePage.locator('.btn-generate').click()

    await expect(imagePage.getByText('AI 正在创作中...')).toBeVisible({ timeout: 15000 })
    await expect(imagePage.locator('.generated-image')).toBeVisible({ timeout: 180000 })
    await expect(imagePage.locator('.error-message')).toHaveCount(0)

    const src = await imagePage.locator('.generated-image').first().getAttribute('src')
    expect(src, `generated image src missing: ${JSON.stringify(apiLog)}`).toMatch(/^(data:image\/|https?:\/\/|\/)/)
    await expect(imagePage.getByRole('button', { name: '下载图片' })).toBeVisible()

    const generated = apiLog.some((item) => (
      item.method === 'POST' && item.url.includes('/kolors/text-to-image') && item.status === 200
    ))
    expect(generated, `text-to-image missing: ${JSON.stringify(apiLog)}`).toBeTruthy()
  })
})
