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
    await expect(popup.locator('.image-generate-page')).toBeVisible({ timeout: 15000 })
    return popup
  }
  await page.goto('/image-generate', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.image-generate-page')).toBeVisible({ timeout: 15000 })
  return page
}

test.describe('AI 绘画浏览器场景', () => {
  test.describe.configure({ mode: 'serial' })
  test.use({ viewport: { width: 1400, height: 900 } })

  test('空生成禁用、切模式、选风格、返回后再进仍保留描述', async ({ page }) => {
    test.setTimeout(90000)
    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const imagePage = await openImagePage(page)
    await expect(imagePage.getByRole('button', { name: '文生图' })).toBeVisible()
    await expect(imagePage.locator('.btn-generate')).toBeDisabled()

    const prompt = `E2E绘画场景 ${Date.now()}，一座海边灯塔`
    await imagePage.locator('#image-prompt').fill(prompt)
    await expect(imagePage.locator('.btn-generate')).toBeEnabled()

    await imagePage.getByRole('button', { name: '图生图' }).click()
    await expect(imagePage.locator('.btn-generate')).toBeDisabled()
    await expect(imagePage.getByText('点击或拖拽上传图片')).toBeVisible()

    await imagePage.getByRole('button', { name: '文生图' }).click()
    await expect(imagePage.locator('.btn-generate')).toBeEnabled()

    await imagePage.locator('.style-card', { hasText: '动漫' }).click()
    await expect(imagePage.locator('.style-card', { hasText: '动漫' })).toHaveAttribute('aria-pressed', 'true')

    await imagePage.locator('.back-btn').click()
    await expect(imagePage).toHaveURL(/\/(?:$|\?)/, { timeout: 10000 })

    await imagePage.goto('/image-generate', { waitUntil: 'domcontentloaded' })
    await expect(imagePage.locator('.image-generate-page')).toBeVisible()
    await expect(imagePage.locator('#image-prompt')).toHaveValue(prompt)
    await expect(imagePage.locator('.style-card', { hasText: '动漫' })).toHaveAttribute('aria-pressed', 'true')
    await expect(imagePage.locator('.btn-generate')).toBeEnabled()
    await expect(imagePage.locator('.loading-state')).toHaveCount(0)
  })

  test('真实生成后刷新仍能看到图，途中返回可再打开', async ({ page }) => {
    test.setTimeout(360000)
    let delayNextGenerate = false
    await page.route('**/api/v1/kolors/text-to-image', async (route) => {
      if (delayNextGenerate) {
        await new Promise((resolve) => setTimeout(resolve, 8000))
      }
      await route.continue()
    })

    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const imagePage = await openImagePage(page)
    imagePage.on('close', () => {})
    await imagePage.route('**/api/v1/kolors/text-to-image', async (route) => {
      if (delayNextGenerate) {
        await new Promise((resolve) => setTimeout(resolve, 8000))
      }
      await route.continue()
    })

    const prompt = `E2E绘画刷新 ${Date.now()}，一只坐在窗边的橘猫，柔和自然光，写实`
    await imagePage.locator('#image-prompt').fill(prompt)
    await imagePage.locator('#image-resolution').selectOption('512x512')
    await expect(imagePage.locator('.btn-generate')).toBeEnabled()
    await imagePage.locator('.btn-generate').click()

    await expect(imagePage.getByText('AI 正在创作中...')).toBeVisible({ timeout: 15000 })
    await expect(imagePage.locator('.generated-image')).toBeVisible({ timeout: 180000 })
    await expect(imagePage.locator('.error-message')).toHaveCount(0)
    const src = await imagePage.locator('.generated-image').first().getAttribute('src')
    expect(src).toMatch(/^(data:image\/|https?:\/\/|\/)/)

    await imagePage.reload({ waitUntil: 'domcontentloaded' })
    await expect(imagePage.locator('.image-generate-page')).toBeVisible()
    await expect(imagePage.locator('#image-prompt')).toHaveValue(prompt)
    await expect(imagePage.locator('.generated-image')).toBeVisible({ timeout: 20000 })
    await expect(imagePage.locator('.loading-state')).toHaveCount(0)

    delayNextGenerate = true
    const midPrompt = `E2E途中返回 ${Date.now()}，月光下的银色狐狸`
    await imagePage.locator('#image-prompt').fill(midPrompt)
    await imagePage.locator('.btn-generate').click()
    await expect(imagePage.getByText('AI 正在创作中...')).toBeVisible({ timeout: 15000 })
    await imagePage.locator('.back-btn').click()
    await expect(imagePage).toHaveURL(/\/(?:$|\?)/, { timeout: 10000 })

    await imagePage.goto('/image-generate', { waitUntil: 'domcontentloaded' })
    await expect(imagePage.locator('.image-generate-page')).toBeVisible()
    await expect(imagePage.locator('#image-prompt')).toHaveValue(midPrompt)
    await expect(imagePage.locator('#image-prompt')).toBeEnabled()
    await expect(imagePage.locator('.loading-state')).toHaveCount(0)
    await expect(imagePage.locator('.btn-generate')).toBeEnabled()
  })
})
