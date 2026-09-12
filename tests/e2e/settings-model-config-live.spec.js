// @ts-check
/**
 * 设置页模型配置实测（超管）
 * Agent 角色 / 降级链 / 错误映射、统一模型增删启停、系统上下文长度
 * afterAll 还原 YAML 角色与降级链，删除探测模型
 */
const { test, expect } = require('@playwright/test')

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:3000'
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000'
const SUPERADMIN_EMAIL = process.env.TEST_SUPERADMIN_EMAIL || 'mr_yang@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_SUPERADMIN_PASSWORD || '12345678'

const YAML_ROLES = {
  architect: 'qwen3-8b',
  frontend: 'deepseek-r1',
  backend: 'qwen3.5-4b',
  reviewer: 'glm-z1-9b',
  fallback: 'qwen3-8b',
}
const YAML_CHAIN = ['qwen3-8b', 'glm-z1-9b']

test.describe.configure({ mode: 'serial' })
test.setTimeout(120000)

let accessToken = ''
let csrfToken = ''
/** @type {Record<string, string> | null} */
let originalRoles = null
/** @type {string[] | null} */
let originalChain = null
let originalNameError = 'glm-z1-9b'
let probeModelId = ''
let probeCtxKey = ''

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} [tab]
 */
async function apiLogin(page, tab = 'agent') {
  const csrfResp = await page.request.get(`${API_BASE}/api/v1/csrf-token`)
  const csrfData = await csrfResp.json()
  csrfToken = csrfData.csrf_token

  const loginResp = await page.request.post(`${API_BASE}/api/v1/login`, {
    data: { email: SUPERADMIN_EMAIL, password: PASSWORD },
    headers: {
      'X-CSRF-Token': csrfToken,
      Cookie: `csrf_token=${csrfToken}`,
    },
  })
  const data = await loginResp.json()
  if (!loginResp.ok() || !data.access_token) {
    throw new Error(`Login failed: ${data.message || data.detail || loginResp.status()}`)
  }
  accessToken = data.access_token

  const browserAuthState = {
    token: data.access_token,
    username: data.username || SUPERADMIN_EMAIL,
    email: SUPERADMIN_EMAIL,
    permission_level: data.permission_level || 'superadmin',
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
}

/** @param {import('@playwright/test').Page} page */
function authHeaders(page) {
  return {
    Authorization: `Bearer ${accessToken}`,
    'X-CSRF-Token': csrfToken,
    Cookie: `csrf_token=${csrfToken}`,
  }
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} method
 * @param {string} path
 * @param {object} [data]
 */
async function apiJson(page, method, path, data) {
  const resp = await page.request.fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      ...authHeaders(page),
      'Content-Type': 'application/json',
    },
    data: data ? JSON.stringify(data) : undefined,
  })
  let body = null
  try {
    body = await resp.json()
  } catch {
    body = { raw: await resp.text() }
  }
  return { status: resp.status(), ok: resp.ok(), body }
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} selector
 * @param {string} query
 * @param {string} waitUrlPart
 */
async function pickModel(page, selector, query, waitUrlPart) {
  await selector.locator('.selector-trigger').click()
  const dropdown = selector.locator('.dropdown-panel')
  await expect(dropdown).toBeVisible()
  await dropdown.locator('.search-input').fill(query)
  const item = dropdown.locator('.model-item').filter({ hasText: query }).first()
  await expect(item).toBeVisible({ timeout: 8000 })
  const label = (await item.locator('.model-name').innerText()).trim()
  const respPromise = page.waitForResponse((resp) =>
    resp.url().includes(waitUrlPart) && resp.request().method() === 'PUT'
  )
  await item.click()
  const resp = await respPromise
  expect(resp.ok(), `${waitUrlPart} HTTP ${resp.status()}`).toBeTruthy()
  await expect(selector.locator('.dropdown-panel')).toHaveCount(0)
  return label
}

/** @param {import('@playwright/test').Page} page */
async function waitToastsGone(page) {
  await expect(page.locator('.el-message')).toHaveCount(0, { timeout: 10000 })
}

test.describe('设置界面 - 模型配置实测', () => {
  test.afterAll(async ({ browser }) => {
    if (!accessToken) return
    const page = await browser.newPage()
    const headers = {
      Authorization: `Bearer ${accessToken}`,
      'X-CSRF-Token': csrfToken,
      Cookie: `csrf_token=${csrfToken}`,
      'Content-Type': 'application/json',
    }
    const roles = originalRoles || YAML_ROLES
    for (const [role, modelId] of Object.entries(roles)) {
      await page.request.fetch(`${API_BASE}/api/v2/model-config/agent/role`, {
        method: 'PUT',
        headers,
        data: JSON.stringify({ role, model_id: modelId }),
      })
    }
    await page.request.fetch(`${API_BASE}/api/v2/model-config/agent/fallback`, {
      method: 'PUT',
      headers,
      data: JSON.stringify({ chain: originalChain || YAML_CHAIN }),
    })
    await page.request.fetch(`${API_BASE}/api/v2/models/agent-config/error-type-model`, {
      method: 'PUT',
      headers,
      data: JSON.stringify({ error_type: 'NameError', model_id: originalNameError }),
    })
    if (probeModelId) {
      await page.request.fetch(`${API_BASE}/api/v2/model-config/models/${probeModelId}`, {
        method: 'DELETE',
        headers,
      })
    }
    const listed = await page.request.fetch(`${API_BASE}/api/v2/model-config/models`, { headers })
    if (listed.ok()) {
      const body = await listed.json()
      for (const model of body.models || []) {
        if (String(model.id || '').startsWith('e2e-probe-')) {
          await page.request.fetch(`${API_BASE}/api/v2/model-config/models/${model.id}`, {
            method: 'DELETE',
            headers,
          })
        }
      }
    }
    if (probeCtxKey) {
      await page.request.fetch(`${API_BASE}/api/v2/models/context-length/${encodeURIComponent(probeCtxKey)}`, {
        method: 'DELETE',
        headers,
      })
    }
    await page.close()
  })

  test('Agent 模型配置：改角色、思考预算、降级链、错误映射并还原', async ({ page }) => {
    await apiLogin(page, 'agent')
    const panel = page.locator('.agent-model-config')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.loading-state')).toHaveCount(0, { timeout: 20000 })

    const snapshot = await apiJson(page, 'GET', '/api/v1/models/agent-config')
    expect(snapshot.ok, `读取 Agent 配置 HTTP ${snapshot.status}`).toBeTruthy()
    originalRoles = snapshot.body.roles || { ...YAML_ROLES }
    originalChain = snapshot.body.fallback_chain || [...YAML_CHAIN]
    originalNameError = snapshot.body.error_type_models?.NameError || 'glm-z1-9b'

    const architectRow = panel.locator('.config-table tbody tr').first()
    await expect(architectRow.locator('.role-badge')).toHaveText('架构师')
    const architectSelector = architectRow.locator('.model-selector')
    const originalArchitectName = (await architectSelector.locator('.model-name').innerText()).trim()
    const originalBudget = (await architectRow.locator('.thinking-budget-cell').innerText()).trim()

    await architectSelector.locator('.selector-trigger').click()
    const dropdown = architectSelector.locator('.dropdown-panel')
    await expect(dropdown).toBeVisible()
    await expect(dropdown.locator('.filter-tag', { hasText: '推理' })).toBeVisible()
    const beforeFilter = await dropdown.locator('.model-item').count()
    expect(beforeFilter).toBeGreaterThan(0)
    await dropdown.locator('.filter-tag', { hasText: '推理' }).click()
    const afterFilter = await dropdown.locator('.model-item').count()
    const emptyAfterFilter = await dropdown.locator('.empty-state').count()
    expect(
      afterFilter + emptyAfterFilter,
      '能力筛选后应仍有模型或空状态'
    ).toBeGreaterThan(0)
    await dropdown.locator('.filter-tag', { hasText: '推理' }).click()
    await expect(dropdown.locator('.model-item').first()).toBeVisible()
    await dropdown.locator('.search-input').press('Escape')

    const changedName = await pickModel(
      page,
      architectSelector,
      'deepseek-r1',
      '/api/v2/model-config/agent/role'
    )
    await expect(page.locator('.el-message--success').filter({ hasText: '已更新 架构师' })).toBeVisible({ timeout: 8000 })
    await expect(architectSelector.locator('.model-name')).toHaveText(changedName)
    await expect(architectRow.locator('.thinking-budget-cell')).toHaveText('50%')

    const restoredName = await pickModel(
      page,
      architectSelector,
      originalRoles.architect || 'qwen3-8b',
      '/api/v2/model-config/agent/role'
    )
    await expect(architectSelector.locator('.model-name')).toHaveText(restoredName)
    await expect(architectRow.locator('.thinking-budget-cell')).toHaveText(originalBudget)
    expect(restoredName).toBe(originalArchitectName)

    const chainItems = panel.locator('.chain-model-item')
    const chainBefore = await chainItems.count()
    expect(chainBefore).toBeGreaterThan(0)
    await panel.locator('.chain-add-btn').click()
    await expect(chainItems).toHaveCount(chainBefore + 1)
    const saveResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/agent/fallback') && resp.request().method() === 'PUT'
    )
    await panel.locator('.chain-save-btn').click()
    expect((await saveResp).ok()).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '降级链已保存' })).toBeVisible({ timeout: 8000 })

    await chainItems.last().locator('.chain-remove-btn').click()
    await expect(chainItems).toHaveCount(chainBefore)
    const restoreChainResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/agent/fallback') && resp.request().method() === 'PUT'
    )
    await panel.locator('.chain-save-btn').click()
    expect((await restoreChainResp).ok()).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '降级链已保存' }).last()).toBeVisible({ timeout: 8000 })

    const nameError = panel.locator('.error-type-item').filter({ hasText: 'NameError' })
    await expect(nameError).toBeVisible()
    await pickModel(page, nameError.locator('.model-selector'), 'deepseek-r1', '/api/v2/models/agent-config/error-type-model')
    await expect(page.locator('.el-message--success').filter({ hasText: 'NameError' })).toBeVisible({ timeout: 8000 })
    await pickModel(page, nameError.locator('.model-selector'), originalNameError, '/api/v2/models/agent-config/error-type-model')

    const after = await apiJson(page, 'GET', '/api/v1/models/agent-config')
    expect(after.body.roles.architect).toBe(originalRoles.architect)
    expect(after.body.fallback_chain).toEqual(originalChain)
    expect(after.body.error_type_models.NameError).toBe(originalNameError)
  })

  test('统一模型配置：添加、搜索、启停、删除探测模型，角色下拉可改回', async ({ page }) => {
    await apiLogin(page, 'unified')
    const panel = page.locator('.unified-model-config')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.model-list .model-card').first()).toBeVisible({ timeout: 15000 })

    probeModelId = `e2e-probe-${Date.now()}`
    const form = panel.locator('.quick-add')
    const idInputs = form.locator('.form-row').first().locator('.form-input')
    await idInputs.nth(0).fill(probeModelId)
    await idInputs.nth(1).fill(probeModelId)
    await idInputs.nth(2).fill('E2E Probe Model')
    await form.locator('.form-select').first().selectOption({ index: 0 })
    await form.locator('.form-select').nth(1).selectOption('chat')

    const addResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/models') && resp.request().method() === 'POST'
    )
    await form.locator('.add-btn').click()
    expect((await addResp).ok(), '添加探测模型应成功').toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '模型已添加' })).toBeVisible({ timeout: 8000 })

    await panel.locator('.filter-bar .search-input').fill(probeModelId)
    const card = panel.locator('.model-list .model-card').filter({ hasText: probeModelId })
    await expect(card).toHaveCount(1)
    await expect(card.locator('.model-name')).toHaveText('E2E Probe Model')
    await expect(card.locator('.toggle-btn')).toHaveText('禁用')

    const disableResp = page.waitForResponse((resp) =>
      resp.url().includes(`/api/v2/model-config/models/${probeModelId}/toggle`) && resp.request().method() === 'PUT'
    )
    await card.locator('.toggle-btn').click()
    expect((await disableResp).ok()).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '状态已切换' })).toBeVisible({ timeout: 8000 })
    await expect(card).toHaveClass(/disabled/)
    await expect(card.locator('.toggle-btn')).toHaveText('启用')

    await waitToastsGone(page)
    const deleteResp = page.waitForResponse((resp) =>
      resp.url().includes(`/api/v2/model-config/models/${probeModelId}`) && resp.request().method() === 'DELETE'
    )
    await card.locator('.delete-btn').evaluate((el) => el.click())
    const confirmBox = page.locator('.el-message-box')
    await expect(confirmBox).toBeVisible({ timeout: 8000 })
    await expect(confirmBox).toContainText('确定删除此模型')
    await confirmBox.locator('.el-button--primary').click()
    expect((await deleteResp).ok()).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '模型已删除' })).toBeVisible({ timeout: 8000 })
    await expect(card).toHaveCount(0)
    probeModelId = ''

    const fallbackCard = panel.locator('.role-card').filter({ hasText: '兜底' })
    const fallbackSelect = fallbackCard.locator('.role-select')
    const originalFallback = await fallbackSelect.inputValue()
    expect(originalFallback).toBeTruthy()
    const roleResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/agent/role') && resp.request().method() === 'PUT'
    )
    await fallbackSelect.selectOption('glm-4-9b')
    expect((await roleResp).ok()).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '兜底' })).toBeVisible({ timeout: 8000 })
    const restoreRoleResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/agent/role') && resp.request().method() === 'PUT'
    )
    await fallbackSelect.selectOption(originalFallback)
    expect((await restoreRoleResp).ok()).toBeTruthy()
    await expect(fallbackSelect).toHaveValue(originalFallback)
  })

  test('系统模型管理：编辑取消、添加并恢复探测上下文长度', async ({ page }) => {
    await apiLogin(page, 'admin')
    const panel = page.locator('.admin-model-manager')
    await expect(panel).toBeVisible({ timeout: 15000 })
    await expect(panel.locator('.loading-state')).toHaveCount(0, { timeout: 20000 })
    await expect(panel.locator('.context-table tbody tr').first()).toBeVisible()

    const firstRow = panel.locator('.context-table tbody tr').first()
    await firstRow.locator('.action-btn.edit').click()
    await expect(firstRow.locator('.ctx-input')).toBeVisible()
    await expect(firstRow.locator('.action-btn.save')).toBeVisible()
    await firstRow.locator('.action-btn.cancel').click()
    await expect(firstRow.locator('.ctx-input')).toHaveCount(0)
    await expect(firstRow.locator('.action-btn.edit')).toBeVisible()

    probeCtxKey = `E2E-PROBE-CTX-${Date.now()}`
    await panel.locator('.add-context .add-input').first().fill(probeCtxKey)
    await panel.locator('.add-context .add-input').nth(1).fill('12345')
    const addResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/models/context-length') && resp.request().method() === 'PUT'
    )
    await panel.locator('.add-context .action-btn.edit').click()
    expect((await addResp).ok(), `添加上下文 HTTP ${(await addResp).status()}`).toBeTruthy()
    await expect(page.locator('.el-message--success').filter({ hasText: '添加成功' })).toBeVisible({ timeout: 8000 })

    await panel.locator('.context-section .search-input').fill(probeCtxKey)
    const probeRow = panel.locator('.context-table tbody tr').filter({ hasText: probeCtxKey })
    await expect(probeRow).toHaveCount(1)
    await expect(probeRow.locator('.source-tag')).toHaveText('自定义')
    await expect(probeRow.locator('.ctx-value')).toContainText('12')

    const delResp = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/models/context-length/') && resp.request().method() === 'DELETE'
    )
    await probeRow.locator('.action-btn.delete').click()
    expect((await delResp).ok()).toBeTruthy()
    await expect(probeRow).toHaveCount(0)
    probeCtxKey = ''
  })
})
