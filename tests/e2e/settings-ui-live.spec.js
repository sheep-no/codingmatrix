// @ts-check
/**
 * 设置界面浏览器实测
 * 覆盖：超管五 Tab 加载与交互、管理员仅三 Tab、表单校验、搜索过滤、模型选择器下拉
 * 不持久改角色/默认模型，不提交自定义供应商，不写入 API Key
 */
const { test, expect } = require('@playwright/test')

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:3000'
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000'
const SUPERADMIN_EMAIL = process.env.TEST_SUPERADMIN_EMAIL || 'mr_yang@example.com'
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_SUPERADMIN_PASSWORD || '12345678'

test.describe.configure({ mode: 'serial' })
test.setTimeout(90000)

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} email
 * @param {string} [fallbackPermission]
 * @param {string} [tab]
 */
async function apiLogin(page, email, fallbackPermission = 'superadmin', tab = 'providers') {
  const csrfResp = await page.request.get(`${API_BASE}/api/v1/csrf-token`)
  const csrfData = await csrfResp.json()
  const csrfToken = csrfData.csrf_token

  const loginResp = await page.request.post(`${API_BASE}/api/v1/login`, {
    data: { email, password: PASSWORD },
    headers: {
      'X-CSRF-Token': csrfToken,
      Cookie: `csrf_token=${csrfToken}`,
    },
  })
  const data = await loginResp.json()
  if (!loginResp.ok() || !data.access_token) {
    throw new Error(`Login failed for ${email}: ${data.message || data.detail || loginResp.status()}`)
  }

  const browserAuthState = {
    token: data.access_token,
    username: data.username || email,
    email,
    permission_level: data.permission_level || fallbackPermission,
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

  await page.goto(`${FRONTEND_URL}/settings?tab=${tab}`, { waitUntil: 'domcontentloaded' })
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
  await expect(page.locator('.settings-page')).toBeVisible({ timeout: 15000 })
  return browserAuthState
}

/** @param {import('@playwright/test').Page} page */
function collectApiFailures(page) {
  /** @type {string[]} */
  const failures = []
  page.on('response', (resp) => {
    const url = resp.url()
    if (!url.includes('/api/')) return
    const status = resp.status()
    if (status >= 500) {
      failures.push(`${status} ${resp.request().method()} ${url}`)
    }
  })
  return failures
}

test.describe('设置界面 - 超管实测', () => {
  test('五个 Tab 可见，自定义供应商表单可填写', async ({ page }) => {
    const failures = collectApiFailures(page)
    await apiLogin(page, SUPERADMIN_EMAIL, 'superadmin', 'providers')

    await expect(page.locator('#settings-tab-providers')).toBeVisible()
    await expect(page.locator('#settings-tab-apikey')).toBeVisible()
    await expect(page.locator('#settings-tab-agent')).toBeVisible()
    await expect(page.locator('#settings-tab-admin')).toBeVisible()
    await expect(page.locator('#settings-tab-unified')).toBeVisible()
    await expect(page.locator('#settings-tab-providers')).toHaveClass(/active/)

    const panel = page.locator('.dynamic-provider-manager')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.load-error')).toHaveCount(0)
    await expect(panel.locator('.section-title')).toHaveText('自定义供应商管理')
    await expect(panel.locator('.add-provider-form')).toBeVisible()

    const submit = panel.locator('.submit-btn')
    await expect(submit).toBeDisabled()

    const inputs = panel.locator('.add-provider-form .form-input')
    await inputs.nth(0).fill('E2E 探测供应商')
    await inputs.nth(1).fill('https://api.example.com/v1')
    await inputs.nth(2).fill('sk-e2e-not-submitted')
    await panel.locator('.form-select').selectOption('openai')
    await expect(submit).toBeEnabled()
    await expect(submit).toHaveText('添加供应商')

    const emptyOrList = panel.locator('.empty-state, .provider-list')
    await expect(emptyOrList).toBeVisible()

    expect(failures, failures.join('\n')).toEqual([])
  })

  test('API Key 管理 Tab 加载硅基流动与其他供应商表单', async ({ page }) => {
    const failures = collectApiFailures(page)
    await apiLogin(page, SUPERADMIN_EMAIL, 'superadmin', 'apikey')

    await expect(page.locator('#settings-tab-apikey')).toHaveClass(/active/)
    const panel = page.locator('.api-key-manager')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.load-error')).toHaveCount(0)
    await expect(panel.locator('.section-title')).toHaveText('API Key 管理')
    await expect(panel.locator('.provider-name', { hasText: '硅基流动' })).toBeVisible()
    await expect(panel.locator('.required-badge')).toHaveText('必填')

    const form = panel.locator('.add-key-form-expanded')
    await expect(form).toBeVisible()
    await expect(form.locator('.provider-select')).toBeVisible()
    const options = await form.locator('.provider-select option').allTextContents()
    expect(options.join(' ')).toContain('智谱 GLM')
    expect(options.join(' ')).toContain('OpenAI')
    expect(options.join(' ')).toContain('DeepSeek')

    await form.locator('.provider-select').selectOption('glm')
    await expect(form.locator('.submit-btn')).toBeDisabled()
    await form.locator('.key-input').fill('sk-placeholder-not-saved')
    await expect(form.locator('.submit-btn')).toBeEnabled()
    await form.locator('.key-input').fill('')
    await expect(form.locator('.submit-btn')).toBeDisabled()

    expect(failures, failures.join('\n')).toEqual([])
  })

  test('Agent 模型配置：五角色、选择器、降级链、错误映射、重新加载', async ({ page }) => {
    const failures = collectApiFailures(page)
    await apiLogin(page, SUPERADMIN_EMAIL, 'superadmin', 'agent')

    await expect(page.locator('#settings-tab-agent')).toHaveClass(/active/)
    const panel = page.locator('.agent-model-config')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.loading-state')).toHaveCount(0, { timeout: 20000 })
    await expect(panel.locator('.section-title').first()).toHaveText('Agent 模型配置')
    await expect(panel.locator('.section-desc').first()).toContainText('修改后立即生效')

    const rows = panel.locator('.config-table tbody tr')
    await expect(rows).toHaveCount(5)
    await expect(panel.locator('.role-badge.architect')).toHaveText('架构师')
    await expect(panel.locator('.role-badge.frontend')).toHaveText('前端工程师')
    await expect(panel.locator('.role-badge.backend')).toHaveText('后端工程师')
    await expect(panel.locator('.role-badge.reviewer')).toHaveText('审查员')
    await expect(panel.locator('.role-badge.fallback')).toHaveText('兜底模型')

    const selectors = panel.locator('.config-table .model-selector')
    await expect(selectors).toHaveCount(5)
    for (let i = 0; i < 5; i++) {
      await expect(selectors.nth(i).locator('.selected-model .model-name')).not.toHaveText('')
    }

    await selectors.first().locator('.selector-trigger').click()
    const dropdown = panel.locator('.config-table .dropdown-panel').first()
    await expect(dropdown).toBeVisible()
    await dropdown.locator('.search-input').fill('glm')
    const items = dropdown.locator('.model-item')
    const itemCount = await items.count()
    expect(itemCount, '搜索 glm 后应有可选模型').toBeGreaterThan(0)
    await dropdown.locator('.search-input').press('Escape')
    await expect(dropdown).toHaveCount(0)

    await expect(panel.locator('.section-title', { hasText: '降级链配置' })).toBeVisible()
    await expect(panel.locator('.chain-save-btn')).toHaveText('保存')
    await expect(panel.locator('.chain-add-btn')).toBeVisible()
    const chainItems = panel.locator('.chain-model-item')
    expect(await chainItems.count()).toBeGreaterThan(0)

    await expect(panel.locator('.section-title', { hasText: '错误类型模型映射' })).toBeVisible()
    expect(await panel.locator('.error-type-item').count()).toBeGreaterThan(0)

    await expect(panel.locator('.info-value').first()).toContainText('agent_model_config.yaml')

    const reloadResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/reload') && resp.request().method() === 'POST'
    )
    await panel.locator('.reload-btn').click()
    const reload = await reloadResp
    expect(reload.ok(), `重新加载 HTTP ${reload.status()}`).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '配置已重新加载' })).toBeVisible({ timeout: 10000 })

    expect(failures, failures.join('\n')).toEqual([])
  })

  test('系统模型管理：默认模型、健康卡片、搜索、上下文表', async ({ page }) => {
    const failures = collectApiFailures(page)
    await apiLogin(page, SUPERADMIN_EMAIL, 'superadmin', 'admin')

    await expect(page.locator('#settings-tab-admin')).toHaveClass(/active/)
    const panel = page.locator('.admin-model-manager')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.loading-state')).toHaveCount(0, { timeout: 20000 })
    await expect(panel.locator('.section-title').first()).toHaveText('系统模型管理')

    await expect(panel.locator('.current-default')).toBeVisible()
    await expect(panel.locator('.default-value .model-name')).not.toHaveText('-')

    await expect(panel.locator('.health-overview')).toBeVisible()
    expect(await panel.locator('.health-card').count()).toBeGreaterThan(0)

    const cards = panel.locator('.model-grid .model-card')
    await expect(cards.first()).toBeVisible()
    const totalBefore = await cards.count()
    expect(totalBefore).toBeGreaterThan(0)
    await expect(panel.locator('.default-badge').first()).toBeVisible()

    const search = panel.locator('.filter-bar .search-input').first()
    await search.fill('qwen')
    await expect(panel.locator('.filter-count')).toContainText('/')
    const filtered = await cards.count()
    expect(filtered).toBeGreaterThan(0)
    expect(filtered).toBeLessThanOrEqual(totalBefore)
    await search.fill('')

    await expect(panel.locator('.section-title', { hasText: '模型上下文窗口配置' })).toBeVisible()
    await expect(panel.locator('.context-table')).toBeVisible()
    expect(await panel.locator('.context-table tbody tr').count()).toBeGreaterThan(0)
    await expect(panel.locator('.ctx-actions .action-btn.edit').first()).toBeVisible()

    expect(failures, failures.join('\n')).toEqual([])
  })

  test('统一模型配置：添加表单、列表搜索过滤、Agent 角色下拉', async ({ page }) => {
    const failures = collectApiFailures(page)
    await apiLogin(page, SUPERADMIN_EMAIL, 'superadmin', 'unified')

    await expect(page.locator('#settings-tab-unified')).toHaveClass(/active/)
    const panel = page.locator('.unified-model-config')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.section-title').first()).toHaveText('模型配置')

    await expect(panel.locator('.quick-add')).toBeVisible()
    await expect(panel.locator('.add-btn')).toHaveText('添加模型')
    await panel.locator('.add-btn').click()
    await expect(page.locator('.el-message--warning').filter({ hasText: '请填写模型 ID' })).toBeVisible({ timeout: 8000 })

    const cards = panel.locator('.model-list .model-card')
    await expect(cards.first()).toBeVisible({ timeout: 15000 })
    const total = await cards.count()
    expect(total).toBeGreaterThan(0)
    await expect(panel.locator('.list-header .subsection-title')).toContainText(`已配置模型 (${total})`)

    await panel.locator('.filter-bar .search-input').fill('glm')
    const glmCount = await cards.count()
    expect(glmCount).toBeGreaterThan(0)
    expect(glmCount).toBeLessThanOrEqual(total)
    await panel.locator('.filter-bar .search-input').fill('')

    await panel.locator('.filter-select').selectOption('embedding')
    const embeddingCount = await cards.count()
    await panel.locator('.filter-select').selectOption('')
    expect(await cards.count()).toBe(total)

    const roles = panel.locator('.role-card')
    await expect(roles).toHaveCount(5)
    await expect(panel.locator('.role-badge.architect')).toBeVisible()
    await expect(roles.first().locator('.role-select option')).toHaveCount(await panel.locator('.role-select').first().locator('option').count())
    const firstRoleValue = await roles.first().locator('.role-select').inputValue()
    expect(firstRoleValue).toBeTruthy()

    expect(embeddingCount).toBeGreaterThanOrEqual(0)
    expect(failures, failures.join('\n')).toEqual([])
  })

  test('键盘方向键可切换设置 Tab', async ({ page }) => {
    await apiLogin(page, SUPERADMIN_EMAIL, 'superadmin', 'providers')
    const providers = page.locator('#settings-tab-providers')
    await expect(providers).toHaveClass(/active/)
    await providers.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#settings-tab-apikey')).toHaveClass(/active/)
    await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
    await page.keyboard.press('End')
    await expect(page.locator('#settings-tab-unified')).toHaveClass(/active/)
    await expect(page.locator('.unified-model-config')).toBeVisible({ timeout: 15000 })
    await page.keyboard.press('Home')
    await expect(page.locator('#settings-tab-providers')).toHaveClass(/active/)
  })
})

test.describe('设置界面 - 管理员 Tab 范围', () => {
  test('管理员仅显示三个基础 Tab', async ({ page }) => {
    await apiLogin(page, ADMIN_EMAIL, 'admin', 'providers')
    await expect(page.locator('#settings-tab-providers')).toBeVisible()
    await expect(page.locator('#settings-tab-apikey')).toBeVisible()
    await expect(page.locator('#settings-tab-agent')).toBeVisible()
    await expect(page.locator('#settings-tab-admin')).toHaveCount(0)
    await expect(page.locator('#settings-tab-unified')).toHaveCount(0)

    await page.locator('#settings-tab-agent').click()
    const panel = page.locator('.agent-model-config')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.loading-state')).toHaveCount(0, { timeout: 20000 })
    await expect(panel.locator('.section-desc').first()).toContainText('请联系超级管理员')
    await expect(panel.locator('.model-readonly').first()).toBeVisible()
    await expect(panel.locator('.config-table .model-selector')).toHaveCount(0)
    await expect(panel.locator('.fallback-chain')).toHaveCount(0)
    await expect(panel.locator('.error-type-grid')).toHaveCount(0)
    await expect(panel.locator('.reload-btn')).toHaveCount(0)
  })
})
