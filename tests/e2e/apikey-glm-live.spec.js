// @ts-check
/**
 * API Key 管理浏览器实测（智谱 GLM）
 * 覆盖：登录 -> 设置 Tab -> 添加 -> 测试连接 -> 启停 -> 降级链 -> 清除
 */
const { test, expect } = require('@playwright/test')

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:3000'
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000'
const TEST_EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const TEST_PASSWORD = process.env.TEST_ADMIN_PASSWORD
const TEST_API_KEY = process.env.TEST_API_KEY

test.describe.configure({ mode: 'serial' })

test.describe('API Key 管理 - 智谱 GLM 实测', () => {
  test.skip(!TEST_PASSWORD, '需要 TEST_ADMIN_PASSWORD')
  test.skip(!TEST_API_KEY, '需要 TEST_API_KEY')

  /** @param {import('@playwright/test').Page} page */
  async function apiLogin(page) {
    const csrfResp = await page.request.get(`${API_BASE}/api/v1/csrf-token`)
    const csrfData = await csrfResp.json()
    const csrfToken = csrfData.csrf_token

    const loginResp = await page.request.post(`${API_BASE}/api/v1/login`, {
      data: { email: TEST_EMAIL, password: TEST_PASSWORD },
      headers: {
        'X-CSRF-Token': csrfToken,
        Cookie: `csrf_token=${csrfToken}`,
      },
    })
    const data = await loginResp.json()
    if (!loginResp.ok() || !data.access_token) {
      throw new Error(`Login failed: ${data.message || data.detail || loginResp.status()}`)
    }

    const browserAuthState = {
      token: data.access_token,
      username: data.username || TEST_EMAIL,
      email: TEST_EMAIL,
      permission_level: data.permission_level || 'admin',
    }

    await page.addInitScript((obj) => {
      const expiry = Date.now() + 3600000
      sessionStorage.setItem('_token', obj.token)
      sessionStorage.setItem('_token_expiry', String(expiry))
      localStorage.setItem('_token_expiry', String(expiry))
      localStorage.setItem('username', obj.username)
      localStorage.setItem('email', obj.email)
      localStorage.setItem('permission_level', obj.permission_level)
      localStorage.setItem('access_token', obj.token)
      localStorage.setItem('user-store', JSON.stringify({
        isLoggedIn: true,
        username: obj.username,
        email: obj.email,
        permissionLevel: obj.permission_level,
      }))
    }, browserAuthState)

    await page.goto(`${FRONTEND_URL}/settings?tab=apikey`, { waitUntil: 'domcontentloaded' })
    await page.evaluate((obj) => {
      const expiry = Date.now() + 3600000
      sessionStorage.setItem('_token', obj.token)
      sessionStorage.setItem('_token_expiry', String(expiry))
      localStorage.setItem('username', obj.username)
      localStorage.setItem('email', obj.email)
      localStorage.setItem('permission_level', obj.permission_level)
      localStorage.setItem('access_token', obj.token)
      localStorage.setItem('user-store', JSON.stringify({
        isLoggedIn: true,
        username: obj.username,
        email: obj.email,
        permissionLevel: obj.permission_level,
      }))
    }, browserAuthState)
    await page.reload({ waitUntil: 'domcontentloaded' })
    const csrfInit = await page.evaluate(async () => {
      const response = await fetch('/api/v1/csrf-token', { credentials: 'include' })
      return { ok: response.ok, status: response.status }
    })
    if (!csrfInit.ok && csrfInit.status !== 429) {
      throw new Error(`Frontend CSRF initialization failed: ${csrfInit.status}`)
    }
    await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.load-error')).toHaveCount(0, { timeout: 15000 })
  }

  /** @param {import('@playwright/test').Page} page */
  function glmCards(page) {
    return page.locator('.other-keys-section .key-card').filter({ hasText: '智谱 GLM' })
  }

  /** @param {import('@playwright/test').Page} page */
  async function clearExistingGlmKeys(page) {
    for (let i = 0; i < 8; i++) {
      const count = await glmCards(page).count()
      if (count === 0) return
      await glmCards(page).first().locator('.delete-btn').click()
      const confirm = page.locator('.el-message-box .el-button--primary')
      await expect(confirm).toBeVisible({ timeout: 5000 })
      await confirm.click()
      await expect(page.locator('.el-message--success').filter({ hasText: 'Key 已清除' })).toBeVisible({ timeout: 10000 })
      await page.waitForTimeout(400)
    }
  }

  test('打开设置页 API Key Tab 并添加智谱 GLM Key', async ({ page }) => {
    await apiLogin(page)
    await expect(page.locator('#settings-tab-apikey')).toHaveClass(/active/)
    await expect(page.locator('.section-title')).toHaveText('API Key 管理')
    await expect(page.locator('.provider-name', { hasText: '硅基流动' })).toBeVisible()

    await clearExistingGlmKeys(page)

    await page.locator('.provider-select').selectOption('glm')
    await page.locator('.add-key-form-expanded .key-input').fill(TEST_API_KEY)
    await page.locator('.add-key-form-expanded .remark-input').fill('E2E GLM')
    await page.locator('.add-key-form-expanded .ttl-select').selectOption('24h')

    const submitResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v1/agent/apikey') &&
      resp.request().method() === 'POST' &&
      !resp.url().includes('/test')
    )
    await page.locator('.add-key-form-expanded .submit-btn').click()
    const submit = await submitResp
    expect(submit.ok(), `提交 Key HTTP ${submit.status()}`).toBeTruthy()

    await expect(page.locator('.el-message--success').filter({ hasText: '智谱 GLM Key 已添加' })).toBeVisible({ timeout: 10000 })
    await expect(glmCards(page).first()).toBeVisible()
    await expect(glmCards(page).first().locator('.key-remark')).toContainText('E2E GLM')
  })

  test('测试智谱 GLM Key 连接', async ({ page }) => {
    await apiLogin(page)
    const card = glmCards(page).filter({ hasText: 'E2E GLM' }).first()
    await expect(card).toBeVisible({ timeout: 10000 })

    const testRespPromise = page.waitForResponse((resp) =>
      resp.url().includes('/api/v1/agent/apikey/test') &&
      resp.request().method() === 'POST'
    )
    await card.locator('.test-btn').click()
    const testResp = await testRespPromise
    expect(testResp.ok(), `测试 Key HTTP ${testResp.status()}`).toBeTruthy()
    const body = await testResp.json()

    const message = page.locator('.el-message').last()
    await expect(message).toBeVisible({ timeout: 15000 })
    const text = await message.innerText()
    expect(body.success, `健康检查失败: ${body.message || text}`).toBeTruthy()
    await expect(message).toContainText('测试成功')
    await expect(card.locator('.status-badge')).toContainText('已验证')
  })

  test('禁用后再启用智谱 GLM Key', async ({ page }) => {
    await apiLogin(page)
    const card = glmCards(page).filter({ hasText: 'E2E GLM' }).first()
    await expect(card).toBeVisible()

    const toggle = card.locator('.toggle-btn')
    await expect(toggle).toHaveText('禁用')
    const disableRespPromise = page.waitForResponse((resp) =>
      resp.url().includes('/enabled') && resp.request().method() === 'PUT'
    )
    await toggle.click()
    const disableResp = await disableRespPromise
    expect(disableResp.ok()).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: 'Key 已禁用' })).toBeVisible({ timeout: 8000 })
    await expect(toggle).toHaveText('启用')

    await toggle.click()
    await expect(page.locator('.el-message--success').filter({ hasText: 'Key 已启用' })).toBeVisible({ timeout: 8000 })
    await expect(toggle).toHaveText('禁用')
  })

  test('展开降级链并清除智谱 GLM Key', async ({ page }) => {
    await apiLogin(page)
    const card = glmCards(page).filter({ hasText: 'E2E GLM' }).first()
    await expect(card).toBeVisible()

    await card.locator('.config-btn', { hasText: '降级链' }).click()
    await expect(card.locator('.context-config-title', { hasText: '降级链配置' })).toBeVisible()
    await expect(card.locator('.fallback-preference-select .model-select')).toBeVisible()

    await card.locator('.delete-btn').click()
    await page.locator('.el-message-box .el-button--primary').click()
    await expect(page.locator('.el-message--success').filter({ hasText: 'Key 已清除' })).toBeVisible({ timeout: 10000 })
    await expect(glmCards(page).filter({ hasText: 'E2E GLM' })).toHaveCount(0)
  })
})
