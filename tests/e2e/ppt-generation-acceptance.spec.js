import { test, expect } from '@playwright/test'

const EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || '12345678'
const TOPIC = '人工智能简介：概念、应用与风险'

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

async function openPptPage(page) {
  await page.locator('#toolkit').click()
  const menu = page.locator('#toolkit-menu')
  await expect(menu).toBeVisible()
  const popupPromise = page.waitForEvent('popup', { timeout: 8000 }).catch(() => null)
  await menu.getByText('PPT 生成', { exact: true }).click()
  const popup = await popupPromise
  if (popup) {
    await popup.waitForLoadState('domcontentloaded')
    return popup
  }
  await page.goto('/ppt-generate', { waitUntil: 'domcontentloaded' })
  return page
}

test.describe('PPT 生成验收', () => {
  test('工具集进入后走完大纲批准并生成 PPTX', async ({ page }) => {
    test.setTimeout(360000)
    const apiLog = []
    page.on('response', (response) => {
      const url = response.url()
      if (url.includes('/api/v1/pptx/')) {
        apiLog.push({ url, status: response.status(), method: response.request().method() })
      }
    })

    await loginOnFrontend(page)
    await syncSiliconflowKeys(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const pptPage = await openPptPage(page)
    pptPage.on('response', (response) => {
      const url = response.url()
      if (url.includes('/api/v1/pptx/')) {
        apiLog.push({ url, status: response.status(), method: response.request().method() })
      }
    })
    await expect(pptPage).toHaveURL(/ppt-generate/)
    await expect(pptPage.locator('.ppt-generate-page')).toBeVisible()

    await pptPage.getByPlaceholder(/请输入 PPT 主题/).fill(TOPIC)
    await pptPage.locator('.option-label', { hasText: '最终总页数' }).locator('select').selectOption('5')
    await pptPage.locator('.option-label', { hasText: '自动配图' }).locator('input').uncheck()
    await pptPage.getByRole('button', { name: '一键生成 PPT' }).click()

    await expect(pptPage.getByText('第 2 步：审阅大纲')).toBeVisible({ timeout: 120000 })
    await expect(pptPage.locator('.outline-title-input').first()).toHaveValue(/.+/)
    const outlineCreated = apiLog.some((item) => item.method === 'POST' && item.url.includes('/pptx/outlines') && item.status === 201)
    expect(outlineCreated, `create outline missing: ${JSON.stringify(apiLog)}`).toBeTruthy()

    const firstTitle = pptPage.locator('.outline-title-input').first()
    if (!(await firstTitle.inputValue()).trim()) {
      await firstTitle.fill('概念与边界')
    }
    const firstMessage = pptPage.locator('.outline-message-input').first()
    if (!(await firstMessage.inputValue()).trim()) {
      await firstMessage.fill('先讲清楚人工智能能做什么')
    }
    const firstContent = pptPage.locator('.outline-content-input').first()
    if (!(await firstContent.inputValue()).trim()) {
      await firstContent.fill('覆盖定义、典型应用和主要风险。')
    }

    await pptPage.getByRole('button', { name: '批准大纲并继续' }).click()
    await expect(pptPage.getByText('第 3 步：选择质量模式')).toBeVisible({ timeout: 30000 })

    await pptPage.getByRole('button', { name: '开始生成 PPT' }).click()
    await expect(pptPage.getByText('生成成功!')).toBeVisible({ timeout: 240000 })
    await expect(pptPage.getByRole('button', { name: '下载 PPTX 文件' })).toBeVisible()
    await expect(pptPage.getByRole('main').getByRole('button', { name: '在线预览' })).toBeVisible()

    const generated = apiLog.some((item) => item.method === 'POST' && item.url.includes('/generate') && item.status === 200)
    expect(generated, `generate task missing: ${JSON.stringify(apiLog)}`).toBeTruthy()
  })
})
