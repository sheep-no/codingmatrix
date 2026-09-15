// @ts-check
/**
 * 把半成品计算器 ZIP 导入 Agent：落地 project_path 后走 core 增量补完。
 */
const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')
const { test, expect } = require('@playwright/test')

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:3000'
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000'
const SUPERADMIN_EMAIL = process.env.TEST_SUPERADMIN_EMAIL || 'mr_yang@example.com'
const SUPERADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_SUPERADMIN_PASSWORD || '12345678'
const TEST_API_KEY = process.env.TEST_API_KEY
const FIXTURE_DIR = path.join(__dirname, 'fixtures', 'semi-calc')
const ZIP_PATH = '/tmp/semi_calc.zip'
const REPORT_PATH = '/tmp/semi-import-agent-report.json'

/** 每次开跑前用仓库内 fixture 重建 ZIP，避免依赖外部残留文件。 */
function ensureSemiCalcZip() {
  execFileSync(
    'python3',
    [
      '-c',
      'import shutil, sys; shutil.make_archive(sys.argv[1], "zip", sys.argv[2])',
      ZIP_PATH.replace(/\.zip$/, ''),
      FIXTURE_DIR,
    ],
    { stdio: 'inherit' },
  )
}

const GLM_MODELS = [
  { id: 'glm-4.7-flash', name: 'glm-4.7-flash', display_name: 'GLM-4.7-Flash', provider: 'zhipu', is_reasoning: false, speed: 2.0, tags: ['flash'] },
  { id: 'glm-4-flash-250414', name: 'glm-4-flash-250414', display_name: 'GLM-4-Flash-250414', provider: 'zhipu', is_reasoning: false, speed: 2.0, tags: ['flash'] },
  { id: 'glm-z1-flash', name: 'glm-z1-flash', display_name: 'GLM-Z1-Flash', provider: 'zhipu', is_reasoning: true, thinking_ratio: 0.5, speed: 1.5, tags: ['flash', 'reasoning'] },
]

const ROLE_MODELS = {
  architect: 'glm-4.7-flash',
  frontend: 'glm-4-flash-250414',
  backend: 'glm-4-flash-250414',
  reviewer: 'glm-z1-flash',
}

const REQUIREMENT = [
  '这是做到一半的命令行计算器，请在现有项目上补完，不要新建项目。',
  '1. main.py 里 print(add(1, 2) 少了右括号，跑不起来',
  '2. subtract 现在是 pass，要返回 a-b',
  '3. multiply 被 main 引用了但没有这个函数，请补上',
  '只要改现有 Python 文件，不要数据库、不要前端、不要测试。',
].join('\n')

function parseSseEvents(raw) {
  const events = []
  if (!raw) return events
  for (const block of String(raw).split(/\n\n+/)) {
    const dataLines = block.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).filter(Boolean)
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
  const thinkingSnippets = []
  let engine = null
  let mode = null
  for (const event of events) {
    const type = event && event.type ? String(event.type) : 'unknown'
    types[type] = (types[type] || 0) + 1
    if (type === 'file' && event.path) filePaths.push(String(event.path))
    if (event.engine) engine = event.engine
    if (event.mode) mode = event.mode
    if (type === 'thinking') {
      const msg = String(event.message || event.content || '')
      if (msg) thinkingSnippets.push(msg.slice(0, 160))
    }
  }
  return { types, filePaths: [...new Set(filePaths)], thinkingSnippets, engine, mode }
}

test.describe('半成品放入 Agent 观察反应', () => {
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
      headers: { 'X-CSRF-Token': csrfToken, Cookie: `csrf_token=${csrfToken}` },
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
  }

  /** @param {import('@playwright/test').Page} page */
  function authHeaders() {
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
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      data: data ? JSON.stringify(data) : undefined,
    })
    let body = null
    try { body = await resp.json() } catch { body = { raw: await resp.text() } }
    return { status: resp.status(), ok: resp.ok(), body }
  }

  /** @param {import('@playwright/test').Page} page */
  async function ensureGlmModels(page) {
    const providers = await apiJson(page, 'GET', '/api/v2/model-config/providers')
    expect(providers.ok).toBeTruthy()
    const hasZhipu = (providers.body.providers || []).some((p) => p.id === 'zhipu')
    if (!hasZhipu) {
      await apiJson(page, 'POST', '/api/v2/model-config/providers', {
        id: 'zhipu', name: 'Zhipu GLM', api_key: '', base_url: 'https://open.bigmodel.cn/api/paas/v4',
      })
    }
    const models = await apiJson(page, 'GET', '/api/v2/model-config/models')
    expect(models.ok).toBeTruthy()
    const existing = new Set((models.body.models || []).map((m) => m.id))
    for (const model of GLM_MODELS) {
      if (existing.has(model.id)) continue
      await apiJson(page, 'POST', '/api/v2/model-config/models', {
        ...model, model_type: 'chat', context_length: 128000, max_output: 8192, temperature: 0.7, timeout: 180,
      })
    }
    await apiJson(page, 'POST', '/api/v2/model-config/reload')
  }

  /** @param {import('@playwright/test').Page} page */
  async function restoreRoles(page) {
    if (!originalRoles || !accessToken) return
    for (const [role, modelId] of Object.entries(originalRoles)) {
      await apiJson(page, 'PUT', '/api/v2/model-config/agent/role', { role, model_id: modelId })
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
    await page.locator('.add-key-form-expanded .remark-input').fill('E2E GLM Semi')
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
      resp.url().includes('/api/v2/model-config/agent/role') && resp.request().method() === 'PUT'
    )
    await item.first().click()
    const resp = await respPromise
    expect(resp.ok(), `选择 ${roleLabel} -> ${modelId} HTTP ${resp.status()}`).toBeTruthy()
  }

  /** @param {import('@playwright/test').Page} page */
  async function selectGlmRoleModels(page) {
    await page.locator('#settings-tab-agent').click()
    await expect(page.locator('.agent-model-config')).toBeVisible({ timeout: 15000 })
    await selectRoleModel(page, '架构师', ROLE_MODELS.architect)
    await selectRoleModel(page, '前端工程师', ROLE_MODELS.frontend)
    await selectRoleModel(page, '后端工程师', ROLE_MODELS.backend)
    await selectRoleModel(page, '审查员', ROLE_MODELS.reviewer)
  }

  /** @param {import('@playwright/test').Page} page */
  async function readAgentState(page) {
    return page.evaluate(() => {
      const el = document.querySelector('.agent-page')
      const inst = el && el.__vueParentComponent
      const s = inst && inst.setupState
      if (!s) return { ok: false }
      const files = (s.files && s.files.generatedFiles) || []
      const placeholderRef = s.getPlaceholder
      const placeholder = placeholderRef && typeof placeholderRef === 'object' && 'value' in placeholderRef
        ? placeholderRef.value
        : String(placeholderRef || '')
      const rawPath = s.workspace && s.workspace.currentProjectPath
      const currentProjectPath = rawPath && typeof rawPath === 'object' && 'value' in rawPath ? rawPath.value : rawPath
      return {
        ok: true,
        fileCount: files.length,
        paths: files.map((f) => f.path),
        currentProjectPath,
        sessionId: s.session && s.session.currentSessionId,
        placeholder: String(placeholder || '').slice(0, 180),
      }
    })
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

  /** @param {import('@playwright/test').Page} page */
  async function waitUntilIdle(page, timeoutMs) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      await dismissConcurrentDialog(page)
      const decisionPanel = page.locator('.decisions-panel')
      if (await decisionPanel.isVisible().catch(() => false)) {
        const defaults = decisionPanel.locator('.btn-decision-secondary')
        const n = await defaults.count()
        for (let i = 0; i < n; i++) await defaults.nth(i).click()
        await decisionPanel.locator('.btn-decision-primary').first().click()
        await page.waitForTimeout(800)
        continue
      }
      const stopVisible = await page.getByRole('button', { name: '停止生成' }).first().isVisible().catch(() => false)
      const sendVisible = await page.getByRole('button', { name: '发送需求' }).first().isVisible().catch(() => false)
      if (sendVisible && !stopVisible) return true
      await page.waitForTimeout(2000)
    }
    return false
  }

  test('ZIP 导入半成品后落地并增量补完', async ({ page }) => {
    expect(fs.existsSync(FIXTURE_DIR), `缺少 fixture 目录 ${FIXTURE_DIR}`).toBeTruthy()
    ensureSemiCalcZip()
    expect(fs.existsSync(ZIP_PATH), `ZIP 生成失败 ${ZIP_PATH}`).toBeTruthy()
    await superadminLogin(page)
    await ensureGlmModels(page)
    const current = await apiJson(page, 'GET', '/api/v2/model-config/agent')
    expect(current.ok).toBeTruthy()
    originalRoles = { ...(current.body.roles || {}) }
    await addGlmKey(page)
    await selectGlmRoleModels(page)

    const report = {
      afterImport: null,
      zipWouldIncremental: null,
      importResult: null,
      streamPayload: null,
      sse: null,
      idle: false,
      afterGenerate: null,
      diskFiles: null,
      depGraph: null,
    }

    /** @type {any} */
    let streamPayload = null
    /** @type {any} */
    let importResult = null
    /** @type {Promise<string> | null} */
    let streamBodyPromise = null
    page.on('request', (req) => {
      if (req.url().includes('/agent/orchestrate/stream') && req.method() === 'POST') {
        try { streamPayload = req.postDataJSON() } catch { streamPayload = { raw: req.postData() } }
      }
    })
    page.on('response', (resp) => {
      if (resp.url().includes('/agent/orchestrate/stream') && resp.request().method() === 'POST') {
        streamBodyPromise = resp.text().catch((err) => `SSE_READ_ERROR:${err}`)
      }
      if (resp.url().includes('/agent/import-files') && resp.request().method() === 'POST') {
        resp.json().then((body) => { importResult = body }).catch(() => {})
      }
    })

    try {
      await page.goto(`${FRONTEND_URL}/agent`, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.agent-page')).toBeVisible({ timeout: 15000 })

      await page.getByRole('button', { name: '导入项目' }).click()
      await expect(page.locator('#upload-modal-title')).toBeVisible({ timeout: 8000 })
      await page.locator('input[type="file"][accept=".zip"]').setInputFiles(ZIP_PATH)
      await expect(page.locator('.el-message--success').filter({ hasText: '成功导入' })).toBeVisible({ timeout: 15000 })

      const afterImport = await readAgentState(page)
      const sidebarFiles = await page.locator('.file-item .file-name').allTextContents()
      const placeholder = await page.getByRole('textbox', { name: '项目需求' }).getAttribute('placeholder')
      const regenerateVisible = await page.getByRole('button', { name: '重新生成' }).isVisible().catch(() => false)
      report.afterImport = { ...afterImport, sidebarFiles, placeholder: String(placeholder || '').slice(0, 180), regenerateVisible }
      report.zipWouldIncremental = Boolean(afterImport.fileCount && afterImport.currentProjectPath)
      fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2))

      expect(afterImport.ok, '未能读取 Agent Vue 状态').toBeTruthy()
      expect(afterImport.fileCount, `导入后文件数=${afterImport.fileCount}`).toBeGreaterThan(0)
      expect(sidebarFiles.join(' ')).toMatch(/calc\.py|main\.py/)

      expect(afterImport.currentProjectPath, `导入后未设置 currentProjectPath: ${JSON.stringify(afterImport)}`).toBeTruthy()
      expect(String(afterImport.currentProjectPath)).toMatch(/^1\//)
      report.importResult = importResult
      expect(report.zipWouldIncremental, 'ZIP 导入后未进入增量条件').toBeTruthy()

      const prompt = page.getByRole('textbox', { name: '项目需求' })
      await prompt.fill(REQUIREMENT)
      await page.getByRole('button', { name: '发送需求' }).click()
      await expect(page.getByRole('button', { name: '停止生成' })).toBeVisible({ timeout: 20000 })
      report.streamPayload = {
        incremental: streamPayload && streamPayload.incremental,
        engine: streamPayload && streamPayload.engine,
        spec_first: streamPayload && streamPayload.spec_first,
        is_resume: streamPayload && streamPayload.is_resume,
        project_path: streamPayload && streamPayload.project_path,
        session_id: streamPayload && streamPayload.session_id,
      }
      fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2))
      expect(streamPayload && streamPayload.incremental, `请求未走增量: ${JSON.stringify(report.streamPayload)}`).toBeTruthy()
      expect(streamPayload && streamPayload.engine).toBe('core')
      expect(streamPayload && streamPayload.is_resume).toBe(false)
      expect(streamPayload && streamPayload.project_path).toBe(afterImport.currentProjectPath)

      report.idle = await waitUntilIdle(page, 16 * 60 * 1000)
      const streamRaw = streamBodyPromise ? await streamBodyPromise : ''
      const sseEvents = parseSseEvents(streamRaw)
      report.sse = { total: sseEvents.length, ...summarizeSse(sseEvents), rawHead: String(streamRaw).slice(0, 400) }
      report.afterGenerate = await readAgentState(page)
      const projectPath = afterImport.currentProjectPath
      const diskDir = `/workspace/projects/${projectPath}`
      report.diskFiles = fs.existsSync(diskDir)
        ? Object.fromEntries(fs.readdirSync(diskDir).filter((n) => fs.statSync(`${diskDir}/${n}`).isFile()).map((n) => [n, fs.readFileSync(`${diskDir}/${n}`, 'utf8').slice(0, 800)]))
        : null
      const depGraphPath = `${diskDir}/.dep_graph.json`
      report.depGraph = fs.existsSync(depGraphPath) ? JSON.parse(fs.readFileSync(depGraphPath, 'utf8')) : null
      fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2))

      expect(report.idle, '增量生成未在时限内结束').toBeTruthy()
      expect(report.sse.total, `未捕获 SSE: ${report.sse.rawHead}`).toBeGreaterThan(0)
      expect(report.diskFiles, `增量后磁盘目录不存在: ${diskDir}`).toBeTruthy()
      const calcSrc = (report.diskFiles && report.diskFiles['calc.py']) || ''
      const mainSrc = (report.diskFiles && report.diskFiles['main.py']) || ''
      expect(calcSrc, 'calc.py 未落盘').toMatch(/def subtract/)
      expect(calcSrc).toMatch(/return a\s*-\s*b/)
      expect(calcSrc).toMatch(/def multiply/)
      expect(mainSrc, 'main.py 未落盘').toBeTruthy()
      expect(mainSrc).toMatch(/from calc import/)
      expect(mainSrc).toMatch(/add\(1,\s*2\)/)
      const calcNode = report.depGraph && report.depGraph.nodes && report.depGraph.nodes['calc.py']
      expect(calcNode, '依赖图缺少 calc.py').toBeTruthy()
      expect(calcNode.type === 'utils' || Boolean(calcNode.description), `依赖图未补全: ${JSON.stringify(calcNode)}`).toBeTruthy()
    } finally {
      fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2))
      try {
        await page.goto(`${FRONTEND_URL}/settings?tab=apikey`, { waitUntil: 'domcontentloaded' })
        await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
        await clearExistingGlmKeys(page)
        await restoreRoles(page)
      } catch { /* cleanup best-effort */ }
    }
  })
})
