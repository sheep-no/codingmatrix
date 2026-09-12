// @ts-check
/**
 * Agent 浏览器实测：智谱 GLM-4.7-Flash / GLM-4-Flash-250414 / GLM-Z1-Flash
 * 使用用户 TEST_API_KEY（供应商 glm），测完恢复原角色模型。
 */
const fs = require('fs')
const { test, expect } = require('@playwright/test')

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:3000'
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000'
const SUPERADMIN_EMAIL = process.env.TEST_SUPERADMIN_EMAIL || 'mr_yang@example.com'
const SUPERADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_SUPERADMIN_PASSWORD || '12345678'
const TEST_API_KEY = process.env.TEST_API_KEY

const GLM_MODELS = [
  {
    id: 'glm-4.7-flash',
    name: 'glm-4.7-flash',
    display_name: 'GLM-4.7-Flash',
    provider: 'zhipu',
    is_reasoning: false,
    speed: 2.0,
    tags: ['flash'],
  },
  {
    id: 'glm-4-flash-250414',
    name: 'glm-4-flash-250414',
    display_name: 'GLM-4-Flash-250414',
    provider: 'zhipu',
    is_reasoning: false,
    speed: 2.0,
    tags: ['flash'],
  },
  {
    id: 'glm-z1-flash',
    name: 'glm-z1-flash',
    display_name: 'GLM-Z1-Flash',
    provider: 'zhipu',
    is_reasoning: true,
    thinking_ratio: 0.5,
    speed: 1.5,
    tags: ['flash', 'reasoning'],
  },
]

const ROLE_MODELS = {
  architect: 'glm-4.7-flash',
  frontend: 'glm-4-flash-250414',
  backend: 'glm-4-flash-250414',
  reviewer: 'glm-z1-flash',
}

const REQUIREMENT = '写一个 Python 文件 hello.py，运行后打印 Hello World。只要这一个文件，不要数据库、不要前端、不要测试。'
const MODIFIED_REQUIREMENT = '写一个 Python 文件 hello.py，运行后打印 Hello CodingMatrix。只要这一个文件，不要数据库、不要前端、不要测试。'

function parseSseEvents(raw) {
  const events = []
  if (!raw) return events
  for (const block of String(raw).split(/\n\n+/)) {
    const dataLines = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .filter(Boolean)
    if (!dataLines.length) continue
    const payload = dataLines.join('\n')
    if (payload === '[DONE]') continue
    try {
      events.push(JSON.parse(payload))
    } catch {
      events.push({ type: 'unparsed', raw: payload.slice(0, 200) })
    }
  }
  return events
}

function summarizeSse(events) {
  /** @type {Record<string, number>} */
  const types = {}
  const filePaths = []
  const toolNames = []
  const thinkingStreamingKeys = new Set()
  let thinkingNonStream = 0
  const thinkingSnippets = []
  for (const event of events) {
    const type = event && event.type ? String(event.type) : 'unknown'
    types[type] = (types[type] || 0) + 1
    if (type === 'file' && event.path) filePaths.push(String(event.path))
    if (type === 'react_tool_call' && event.tool) toolNames.push(String(event.tool))
    if (type === 'thinking') {
      const msg = String(event.message || event.content || '')
      if (msg) thinkingSnippets.push(msg.slice(0, 120))
      if (event.streaming) {
        thinkingStreamingKeys.add(`${event.agent || ''}|${event.phase || ''}`)
      } else {
        thinkingNonStream += 1
      }
    }
  }
  return {
    types,
    filePaths: [...new Set(filePaths)],
    toolNames,
    expectedThinkingCards: thinkingStreamingKeys.size + thinkingNonStream,
    thinkingSnippets,
  }
}

test.describe.configure({ mode: 'serial' })

test.describe('Agent 智谱 GLM Flash 实测', () => {
  test.skip(!TEST_API_KEY, '需要 TEST_API_KEY')

  test.setTimeout(20 * 60 * 1000)

  /** @type {string | null} */
  let accessToken = null
  /** @type {string | null} */
  let csrfToken = null
  /** @type {Record<string, string> | null} */
  let originalRoles = null

  /** @param {import('@playwright/test').Page} page */
  async function superadminLogin(page) {
    const csrfResp = await page.request.get(`${API_BASE}/api/v1/csrf-token`)
    const csrfData = await csrfResp.json()
    csrfToken = csrfData.csrf_token

    const loginResp = await page.request.post(`${API_BASE}/api/v1/login`, {
      data: { email: SUPERADMIN_EMAIL, password: SUPERADMIN_PASSWORD },
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
  }

  /** @param {import('@playwright/test').Page} page */
  function authHeaders(page) {
    return {
      Authorization: `Bearer ${accessToken}`,
      'X-CSRF-Token': csrfToken,
      Cookie: `csrf_token=${csrfToken}`,
    }
  }

  /** @param {import('@playwright/test').Page} page */
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

  /** @param {import('@playwright/test').Page} page */
  async function ensureGlmModels(page) {
    const providers = await apiJson(page, 'GET', '/api/v2/model-config/providers')
    expect(providers.ok).toBeTruthy()
    const hasZhipu = (providers.body.providers || []).some((p) => p.id === 'zhipu')
    if (!hasZhipu) {
      const added = await apiJson(page, 'POST', '/api/v2/model-config/providers', {
        id: 'zhipu',
        name: 'Zhipu GLM',
        api_key: '',
        base_url: 'https://open.bigmodel.cn/api/paas/v4',
      })
      expect(added.ok || added.status === 400).toBeTruthy()
    }

    const models = await apiJson(page, 'GET', '/api/v2/model-config/models')
    expect(models.ok).toBeTruthy()
    const existing = new Set((models.body.models || []).map((m) => m.id))
    for (const model of GLM_MODELS) {
      if (existing.has(model.id)) continue
      const added = await apiJson(page, 'POST', '/api/v2/model-config/models', {
        ...model,
        model_type: 'chat',
        context_length: 128000,
        max_output: 8192,
        temperature: 0.7,
        timeout: 180,
      })
      expect(added.ok || added.status === 400).toBeTruthy()
    }

    await apiJson(page, 'POST', '/api/v2/model-config/reload')
  }

  /** @param {import('@playwright/test').Page} page */
  async function restoreRoles(page) {
    if (!originalRoles || !accessToken) return
    for (const [role, modelId] of Object.entries(originalRoles)) {
      await apiJson(page, 'PUT', '/api/v2/model-config/agent/role', {
        role,
        model_id: modelId,
      })
    }
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

  /** @param {import('@playwright/test').Page} page */
  async function addGlmKey(page) {
    await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
    await clearExistingGlmKeys(page)
    await page.locator('.provider-select').selectOption('glm')
    await page.locator('.add-key-form-expanded .key-input').fill(TEST_API_KEY)
    await page.locator('.add-key-form-expanded .remark-input').fill('E2E GLM Agent')
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
    await expect(glmCards(page).first()).toBeVisible({ timeout: 15000 })
  }

  /** @param {import('@playwright/test').Page} page */
  async function testGlmKey(page) {
    const card = glmCards(page).filter({ hasText: 'E2E GLM Agent' }).first()
    await expect(card).toBeVisible({ timeout: 10000 })
    const testRespPromise = page.waitForResponse((resp) =>
      resp.url().includes('/api/v1/agent/apikey/test') &&
      resp.request().method() === 'POST'
    )
    await card.locator('.test-btn').click()
    const testResp = await testRespPromise
    expect(testResp.ok(), `测试 Key HTTP ${testResp.status()}`).toBeTruthy()
    const body = await testResp.json()
    expect(body.success, `连接测试失败: ${body.message || JSON.stringify(body)}`).toBeTruthy()
  }

  /**
   * @param {import('@playwright/test').Page} page
   * @param {string} roleLabel
   * @param {string} modelId
   */
  async function selectRoleModel(page, roleLabel, modelId) {
    const row = page.locator('.config-table tbody tr').filter({
      has: page.locator('.role-badge', { hasText: roleLabel }),
    })
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('.selector-trigger').click()
    const dropdown = row.locator('.dropdown-panel')
    await expect(dropdown).toBeVisible({ timeout: 5000 })
    await dropdown.locator('.search-input').fill(modelId)
    const item = dropdown.locator('.model-item').filter({
      has: page.locator('.model-id', { hasText: modelId }),
    })
    await expect(item.first()).toBeVisible({ timeout: 5000 })
    const respPromise = page.waitForResponse((resp) =>
      resp.url().includes('/api/v2/model-config/agent/role') &&
      resp.request().method() === 'PUT'
    )
    await item.first().click()
    const resp = await respPromise
    expect(resp.ok(), `选择 ${roleLabel} -> ${modelId} HTTP ${resp.status()}`).toBeTruthy()
  }

  /** @param {import('@playwright/test').Page} page */
  async function selectGlmRoleModels(page) {
    await page.locator('#settings-tab-agent').click()
    await expect(page.locator('.agent-model-config')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.config-table')).toBeVisible({ timeout: 15000 })
    await selectRoleModel(page, '架构师', ROLE_MODELS.architect)
    await selectRoleModel(page, '前端工程师', ROLE_MODELS.frontend)
    await selectRoleModel(page, '后端工程师', ROLE_MODELS.backend)
    await selectRoleModel(page, '审查员', ROLE_MODELS.reviewer)
  }

  /** @param {import('@playwright/test').Page} page */
  async function waitForStopButton(page, timeout = 20000) {
    await expect(page.getByRole('button', { name: '停止生成' }).first()).toBeVisible({ timeout })
  }

  /** @param {import('@playwright/test').Page} page */
  async function waitForSendButton(page, timeout = 20000) {
    await expect(page.getByRole('button', { name: '发送需求' }).first()).toBeVisible({ timeout })
  }

  /** @param {import('@playwright/test').Page} page */
  async function waitForThinkingOrHint(page, timeout = 45000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
      const visible = await page.locator('.activity-thinking').first().isVisible().catch(() => false)
      if (visible) return true
      await page.waitForTimeout(400)
    }
    return false
  }

  /** @param {import('@playwright/test').Page} page */
  async function clickStopGeneration(page) {
    await page.getByRole('button', { name: '停止生成' }).first().click()
    const box = page.locator('.el-message-box')
    const appeared = await box.isVisible({ timeout: 2500 }).catch(() => false)
    if (!appeared) return { dialog: false }
    const directEnd = box.getByRole('button', { name: '直接结束' })
    if (await directEnd.isVisible().catch(() => false)) {
      await directEnd.click()
      return { dialog: true, action: '直接结束' }
    }
    const cancel = box.locator('button').filter({ hasText: /直接结束|取消|Cancel/ }).first()
    await cancel.click()
    return { dialog: true, action: 'cancel' }
  }

  /**
   * @param {import('@playwright/test').Page} page
   * @param {string} sessionId
   */
  async function cancelSessionUntilSettled(page, sessionId, timeoutMs = 25000, treat404AsSettled = false) {
    if (!sessionId) return { ok: false, lastStatus: null }
    const deadline = Date.now() + timeoutMs
    let lastStatus = null
    while (Date.now() < deadline) {
      const resp = await apiJson(page, 'POST', `/api/v1/agent/session/${sessionId}/action?action=cancel`)
      lastStatus = resp.status
      if (resp.ok) return { ok: true, lastStatus }
      if (treat404AsSettled && resp.status === 404) return { ok: true, lastStatus }
      await page.waitForTimeout(500)
    }
    return { ok: false, lastStatus }
  }

  /**
   * @param {import('@playwright/test').Page} page
   * @param {string[]} ids
   */
  async function cancelAllTracked(page, ids, timeoutMs = 25000, treat404AsSettled = false) {
    const unique = [...new Set((ids || []).filter(Boolean))]
    const results = []
    for (const id of unique) {
      results.push({ id, ...(await cancelSessionUntilSettled(page, id, timeoutMs, treat404AsSettled)) })
    }
    return results
  }

  /** @param {import('@playwright/test').Page} page */
  async function dismissConcurrentDialog(page) {
    const box = page.locator('.el-message-box')
    if (!(await box.isVisible().catch(() => false))) return false
    const stopOldest = box.getByRole('button', { name: '停止最早的项目' })
    if (await stopOldest.isVisible().catch(() => false)) {
      await stopOldest.click()
      await page.waitForTimeout(800)
      return true
    }
    return false
  }

  /**
   * @param {import('@playwright/test').Page} page
   * @param {number} timeoutMs
   */
  async function waitUntilIdle(page, timeoutMs, requireFiles = false) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      await dismissConcurrentDialog(page)
      const decisionPanel = page.locator('.decisions-panel')
      if (await decisionPanel.isVisible().catch(() => false)) {
        const defaults = decisionPanel.locator('.btn-decision-secondary')
        const n = await defaults.count()
        for (let i = 0; i < n; i++) {
          await defaults.nth(i).click()
        }
        await decisionPanel.locator('.btn-decision-primary').first().click()
        await page.waitForTimeout(800)
        continue
      }
      const stopVisible = await page.getByRole('button', { name: '停止生成' }).first().isVisible().catch(() => false)
      const sendVisible = await page.getByRole('button', { name: '发送需求' }).first().isVisible().catch(() => false)
      if (sendVisible && !stopVisible) {
        if (!requireFiles) return true
        const snap = await collectUiSnapshot(page)
        if (
          snap.fileCards.length ||
          snap.sidebarFiles.length ||
          /hello\.py/i.test(snap.pageSnippet)
        ) return true
      }
      await page.waitForTimeout(2000)
    }
    return false
  }

  /** @param {import('@playwright/test').Page} page */
  async function collectUiSnapshot(page) {
    return page.evaluate(() => {
      const activityCards = [...document.querySelectorAll('.activity-card')].map((el) => ({
        kind: [...el.classList].find((cls) => cls.startsWith('activity-') && cls !== 'activity-card') || '',
        text: (el.innerText || '').slice(0, 240),
      }))
      return {
        activityCount: (document.querySelector('.activity-count')?.textContent || '').trim(),
        activityCards,
        thinkingCards: [...document.querySelectorAll('.activity-thinking .activity-text')].map(
          (el) => (el.textContent || '').trim()
        ),
        fileCards: [...document.querySelectorAll('.activity-file .file-path')].map(
          (el) => (el.textContent || '').trim()
        ),
        sidebarFiles: [...document.querySelectorAll('.file-item .file-name')].map(
          (el) => (el.textContent || '').trim()
        ),
        prompt: (document.querySelector('[data-testid="agent-prompt-input"]')?.value || '').slice(0, 200),
        pageSnippet: (document.querySelector('.agent-page')?.innerText || '').slice(0, 4000),
      }
    })
  }

  test('用智谱三模型跑通一次 Agent 生成', async ({ page }) => {
    await superadminLogin(page)
    await ensureGlmModels(page)
    const current = await apiJson(page, 'GET', '/api/v2/model-config/agent')
    expect(current.ok).toBeTruthy()
    originalRoles = { ...(current.body.roles || {}) }
    await addGlmKey(page)
    await testGlmKey(page)
    await selectGlmRoleModels(page)

    let streamPayload = null
    page.on('request', (req) => {
      if (req.url().includes('/agent/orchestrate/stream') && req.method() === 'POST') {
        try {
          streamPayload = req.postDataJSON()
        } catch {
          streamPayload = { raw: req.postData() }
        }
      }
    })

    /** @type {Promise<string> | null} */
    let streamBodyPromise = null
    page.on('response', (resp) => {
      if (resp.url().includes('/agent/orchestrate/stream') && resp.request().method() === 'POST') {
        streamBodyPromise = resp.text().catch((err) => `SSE_READ_ERROR:${err}`)
      }
    })

    await page.goto(`${FRONTEND_URL}/agent`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.agent-page')).toBeVisible({ timeout: 15000 })
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    await expect(prompt).toBeVisible({ timeout: 10000 })
    await prompt.fill(REQUIREMENT)
    const sendBtn = page.getByRole('button', { name: '发送需求' })
    await expect(sendBtn).toBeEnabled({ timeout: 5000 })
    await sendBtn.click()

    await expect(page.getByRole('button', { name: '停止生成' })).toBeVisible({ timeout: 20000 })
    expect(streamPayload && streamPayload.api_key_token).toBeTruthy()

    const deadline = Date.now() + 18 * 60 * 1000
    while (Date.now() < deadline) {
      const decisionPanel = page.locator('.decisions-panel')
      if (await decisionPanel.isVisible().catch(() => false)) {
        const defaults = decisionPanel.locator('.btn-decision-secondary')
        const n = await defaults.count()
        for (let i = 0; i < n; i++) {
          await defaults.nth(i).click()
        }
        await decisionPanel.locator('.btn-decision-primary').first().click()
        await page.waitForTimeout(800)
        continue
      }
      const stopVisible = await page.getByRole('button', { name: '停止生成' }).isVisible().catch(() => false)
      const sendVisible = await page.getByRole('button', { name: '发送需求' }).isVisible().catch(() => false)
      if (sendVisible && !stopVisible) break
      await page.waitForTimeout(2000)
    }
    await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible({ timeout: 15000 })

    const streamRaw = streamBodyPromise ? await streamBodyPromise : ''
    const sseEvents = parseSseEvents(streamRaw)
    const sseSummary = summarizeSse(sseEvents)

    const fileCount = await page.locator('.file-item, [data-testid="generated-file"]').count()
    const pageText = await page.locator('.agent-page').innerText()
    const hasHello = /hello\.py/i.test(pageText)
    expect(fileCount > 0 || hasHello).toBeTruthy()

    const ui = await page.evaluate(() => {
      const activityCards = [...document.querySelectorAll('.activity-card')].map((el) => ({
        kind: [...el.classList].find((cls) => cls.startsWith('activity-') && cls !== 'activity-card') || '',
        text: (el.innerText || '').slice(0, 400),
      }))
      const thinkingCards = [...document.querySelectorAll('.activity-thinking .activity-text')].map(
        (el) => (el.textContent || '').trim()
      )
      const toolCards = [...document.querySelectorAll('.activity-tool')].map((el) => ({
        name: (el.querySelector('.tool-name')?.textContent || '').trim(),
        text: (el.innerText || '').slice(0, 240),
      }))
      const fileCards = [...document.querySelectorAll('.activity-file .file-path')].map(
        (el) => (el.textContent || '').trim()
      )
      const sidebarFiles = [...document.querySelectorAll('.file-item .file-name')].map(
        (el) => (el.textContent || '').trim()
      )
      const activityCount = (document.querySelector('.activity-count')?.textContent || '').trim()
      return {
        activityCount,
        activityCards,
        thinkingCards,
        toolCards,
        fileCards,
        sidebarFiles,
      }
    })

    const report = {
      sseEventTotal: sseEvents.length,
      sseTypes: sseSummary.types,
      sseFilePaths: sseSummary.filePaths,
      sseToolNames: sseSummary.toolNames,
      expectedThinkingCards: sseSummary.expectedThinkingCards,
      thinkingSnippets: sseSummary.thinkingSnippets.slice(0, 8),
      ui,
      hasHello,
      sidebarFileCount: fileCount,
    }
    fs.writeFileSync('/tmp/glm-e2e-sse-ui-report.json', JSON.stringify(report, null, 2))

    expect(sseEvents.length, `未捕获到 SSE 事件，body=${String(streamRaw).slice(0, 180)}`).toBeGreaterThan(0)

    if (sseSummary.types.thinking) {
      expect(
        ui.thinkingCards.length,
        `后端 thinking=${sseSummary.types.thinking}，前端思考卡片=${ui.thinkingCards.length}`
      ).toBeGreaterThan(0)
      const joinedThinking = ui.thinkingCards.join('\n')
      expect(joinedThinking.trim().length, '思考卡片没有正文').toBeGreaterThan(0)
    }

    if (sseSummary.filePaths.length) {
      expect(
        ui.fileCards.length + ui.sidebarFiles.length,
        `后端 file 路径=${sseSummary.filePaths.join(',')}，前端文件卡片/侧栏为空`
      ).toBeGreaterThan(0)
      for (const filePath of sseSummary.filePaths) {
        const name = filePath.split('/').pop() || filePath
        const shown =
          ui.fileCards.some((text) => text.includes(filePath) || text.includes(name)) ||
          ui.sidebarFiles.some((text) => text.includes(name)) ||
          pageText.includes(filePath) ||
          pageText.includes(name)
        expect(shown, `后端文件 ${filePath} 未出现在前端`).toBeTruthy()
      }
    }

    if (sseSummary.toolNames.length) {
      expect(
        ui.toolCards.length,
        `后端 react_tool_call=${sseSummary.toolNames.join(',')}，前端工具卡片=${ui.toolCards.length}`
      ).toBeGreaterThan(0)
    }

    await page.goto(`${FRONTEND_URL}/settings?tab=apikey`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
    await clearExistingGlmKeys(page)
    await restoreRoles(page)
  })

  test('中途停止、改需求、刷新后再生成', async ({ page }) => {
    await superadminLogin(page)
    await ensureGlmModels(page)
    const current = await apiJson(page, 'GET', '/api/v2/model-config/agent')
    expect(current.ok).toBeTruthy()
    originalRoles = { ...(current.body.roles || {}) }
    await addGlmKey(page)
    await testGlmKey(page)
    await selectGlmRoleModels(page)

    /** @type {string[]} */
    const streamSessionIds = []
    page.on('request', (req) => {
      if (req.url().includes('/agent/orchestrate/stream') && req.method() === 'POST') {
        try {
          const payload = req.postDataJSON()
          if (payload && payload.session_id) streamSessionIds.push(String(payload.session_id))
        } catch { /* ignore */ }
      }
    })

    await page.goto(`${FRONTEND_URL}/agent`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.agent-page')).toBeVisible({ timeout: 15000 })
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    await expect(prompt).toBeVisible({ timeout: 10000 })
    await prompt.fill(REQUIREMENT)
    await page.getByRole('button', { name: '发送需求' }).click()

    const report = { streamSessionIds }
    try {
      await waitForStopButton(page)
      await page.waitForTimeout(8000)
      const startedBeforeStop = await waitForThinkingOrHint(page, 40000)
      report.startedBeforeStop = startedBeforeStop
      expect(startedBeforeStop, '停止前应出现思考卡片').toBeTruthy()

      const stopResult = await clickStopGeneration(page)
      const cancelAfterStop = await cancelAllTracked(page, streamSessionIds, 15000)
      report.stopResult = stopResult
      report.cancelAfterStop = cancelAfterStop
      await waitForSendButton(page, 30000)
      await page.waitForTimeout(1500)
      const afterStop = await collectUiSnapshot(page)
      report.afterStop = {
        prompt: afterStop.prompt,
        activityCount: afterStop.activityCount,
        thinking: afterStop.thinkingCards.length,
      }
      expect(
        afterStop.prompt.includes('Hello World') || afterStop.prompt.includes('hello.py'),
        '停止后需求输入框应仍保留原需求'
      ).toBeTruthy()

      await prompt.fill(MODIFIED_REQUIREMENT)
      const retryBtn = page.getByRole('button', { name: '重新生成' })
      if (await retryBtn.isVisible().catch(() => false)) {
        await retryBtn.click()
      } else {
        await page.getByRole('button', { name: '发送需求' }).click()
      }

      await waitForStopButton(page)
      await page.waitForTimeout(6000)
      const startedBeforeRefresh = await waitForThinkingOrHint(page, 40000)
      const beforeRefresh = await collectUiSnapshot(page)
      report.startedBeforeRefresh = startedBeforeRefresh
      report.beforeRefresh = {
        activityCount: beforeRefresh.activityCount,
        thinking: beforeRefresh.thinkingCards.length,
        cards: beforeRefresh.activityCards.length,
      }

      await page.reload({ waitUntil: 'domcontentloaded' })
      await expect(page.locator('.agent-page')).toBeVisible({ timeout: 15000 })
      await expect(prompt).toBeVisible({ timeout: 10000 })
      const afterRefresh = await collectUiSnapshot(page)
      const stillGenerating = await page.getByRole('button', { name: '停止生成' }).first().isVisible().catch(() => false)
      report.afterRefresh = {
        prompt: afterRefresh.prompt,
        stillGenerating,
        activityCount: afterRefresh.activityCount,
        thinking: afterRefresh.thinkingCards.length,
      }

      const cancelAfterRefresh = await cancelAllTracked(page, streamSessionIds, 8000, true)
      report.cancelAfterRefresh = cancelAfterRefresh
      await page.waitForTimeout(2000)
      if (await page.getByRole('button', { name: '停止生成' }).first().isVisible().catch(() => false)) {
        await clickStopGeneration(page)
        await waitForSendButton(page, 20000)
      }

      const currentPrompt = await prompt.inputValue()
      if (!currentPrompt.includes('CodingMatrix')) {
        await prompt.fill(MODIFIED_REQUIREMENT)
      }
      const retryAfterRefresh = page.getByRole('button', { name: '重新生成' })
      if (await retryAfterRefresh.isVisible().catch(() => false)) {
        await retryAfterRefresh.click()
      } else {
        const sendBtn = page.getByRole('button', { name: '发送需求' })
        await expect(sendBtn).toBeEnabled({ timeout: 5000 })
        await sendBtn.click()
      }
      await page.waitForTimeout(1500)
      await dismissConcurrentDialog(page)

      const generatingAfterRetry = await page.getByRole('button', { name: '停止生成' }).first().isVisible().catch(() => false)
      if (!generatingAfterRetry) {
        await cancelAllTracked(page, streamSessionIds, 8000, true)
        await page.waitForTimeout(2000)
        await prompt.fill(MODIFIED_REQUIREMENT)
        await page.getByRole('button', { name: '发送需求' }).click()
        await page.waitForTimeout(1500)
      }

      await waitForStopButton(page, 30000)
      await waitUntilIdle(page, 18 * 60 * 1000, true)
      await waitForSendButton(page, 15000)

      const finalUi = await collectUiSnapshot(page)
      const pageText = await page.locator('.agent-page').innerText()
      const hasHello = /hello\.py/i.test(pageText) ||
        finalUi.fileCards.some((text) => /hello\.py/i.test(text)) ||
        finalUi.sidebarFiles.some((text) => /hello\.py/i.test(text))
      report.finalUi = {
        prompt: finalUi.prompt,
        activityCount: finalUi.activityCount,
        thinking: finalUi.thinkingCards.length,
        fileCards: finalUi.fileCards,
        sidebarFiles: finalUi.sidebarFiles,
        hasHello,
      }
      expect(
        hasHello || finalUi.fileCards.length > 0 || finalUi.sidebarFiles.length > 0,
        '改需求并刷新后应生成 hello.py 或至少一个文件'
      ).toBeTruthy()
    } finally {
      report.streamSessionIds = streamSessionIds
      fs.writeFileSync('/tmp/glm-e2e-midway-report.json', JSON.stringify(report, null, 2))
      try {
        await cancelAllTracked(page, streamSessionIds, 5000, true)
        await page.goto(`${FRONTEND_URL}/settings?tab=apikey`, { waitUntil: 'domcontentloaded' })
        await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
        await clearExistingGlmKeys(page)
        await restoreRoles(page)
      } catch { /* cleanup best-effort */ }
    }
  })

  test.afterAll(async ({ browser }) => {
    if (!originalRoles || !accessToken) return
    const page = await browser.newPage()
    try {
      const csrfResp = await page.request.get(`${API_BASE}/api/v1/csrf-token`)
      const csrfData = await csrfResp.json()
      csrfToken = csrfData.csrf_token
      for (const [role, modelId] of Object.entries(originalRoles)) {
        await page.request.fetch(`${API_BASE}/api/v2/model-config/agent/role`, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${accessToken}`,
            'X-CSRF-Token': csrfToken,
            Cookie: `csrf_token=${csrfToken}`,
            'Content-Type': 'application/json',
          },
          data: JSON.stringify({ role, model_id: modelId }),
        })
      }
    } finally {
      await page.close()
    }
  })
})
