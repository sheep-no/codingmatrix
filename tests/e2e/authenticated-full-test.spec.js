import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'
import {
  doneEvent,
  fileEvent,
  mockModelContext,
  mockProjectStream,
  progressEvent,
  seedMockKeys,
} from './fixtures/agentMock.js'

const TEST_EMAIL = process.env.TEST_ADMIN_EMAIL || 'mr_yang@example.com'
const TEST_PASSWORD = process.env.TEST_ADMIN_PASSWORD || '12345678'

async function gotoAgent(page) {
  await page.goto('/agent', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('textbox', { name: '项目需求' })).toBeVisible({ timeout: 15000 })
}

test.describe('登录后完整功能测试', () => {
  test('1. 用户登录功能', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const loginButton = page.locator('.login-btn')
    await expect(loginButton).toBeVisible({ timeout: 15000 })
    await page.waitForFunction(() => Boolean(window.__appInitialization))
    await page.evaluate(() => window.__appInitialization?.catch?.(() => {}))
    const modal = page.locator('.login-modal')
    for (let attempt = 0; attempt < 3; attempt++) {
      await loginButton.click()
      if (await modal.waitFor({ state: 'visible', timeout: 2000 }).then(() => true).catch(() => false)) break
    }
    await expect(modal).toBeVisible()
    await modal.locator('input[type="email"]').fill(TEST_EMAIL)
    await modal.locator('input[type="password"]').fill(TEST_PASSWORD)
    await modal.locator('.btn-login').click()

    await expect.poll(() => page.evaluate(() => localStorage.getItem('access_token')), { timeout: 15000 })
      .toBeTruthy()
    const userStore = await page.evaluate(() => JSON.parse(localStorage.getItem('user-store') || '{}'))
    expect(userStore.isLoggedIn).toBe(true)
  })

  test('2. Agent 工作台 - 项目生成', async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)

    const calls = []
    await mockProjectStream(page, [
      progressEvent('analyzing', '分析需求', 20),
      fileEvent('src/App.vue', '<template><div>todo</div></template>'),
      fileEvent('app/main.py', 'print("todo")'),
      doneEvent('e2e-todo'),
    ], request => calls.push(request.postData()))

    await gotoAgent(page)
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    await prompt.fill('创建一个简单的待办事项应用')
    await page.getByRole('button', { name: '发送需求' }).click()

    await expect.poll(() => calls.length, { timeout: 15000 }).toBe(1)
    const body = JSON.parse(calls[0])
    expect(body.requirement).toContain('待办事项')
    expect(body.session_id).toBeTruthy()
    expect(body.incremental).toBe(false)

    await expect(page.locator('.topbar-status')).toHaveClass(/status-completed/, { timeout: 15000 })
    await expect(page.locator('.file-item')).toHaveCount(2)
    await expect(page.locator('.agent-workspace')).toContainText('src/App.vue')
  })

  test('3. 会话历史管理', async ({ page }) => {
    await apiLogin(page)
    await page.addInitScript(() => {
      localStorage.setItem('agent_project_sessions', JSON.stringify([{
        id: 'seed-session', prompt: '种子项目', timestamp: Date.now(), filesCount: 1,
        files: [], logs: [], thinking: [], steps: [], workflowStages: [],
        pendingDecisions: [], decisionHistory: [], currentPhase: '', currentStep: 0,
        totalSteps: 0, startTime: null, modelAssignments: {}, modelConfigVersion: '',
        modelContextRevision: null, currentModel: null, currentAgent: null,
        fallbackHistory: [], recoveryAttempts: [],
      }]))
    })
    await mockModelContext(page)
    await gotoAgent(page)

    const sessionItem = page.locator('.session-item').first()
    await expect(sessionItem).toBeVisible({ timeout: 15000 })
    await expect(sessionItem).toContainText('1 文件')

    await sessionItem.click()
    await expect(sessionItem).toHaveClass(/active/)
    await expect(page.getByRole('textbox', { name: '项目需求' })).toHaveValue('种子项目')
  })

  test('4. 已保存项目列表 API', async ({ page, request }) => {
    const login = await apiLogin(page)
    const token = login.token

    const response = await request.get('/api/v1/agent/saved', {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(Array.isArray(data.projects)).toBe(true)
    expect(data).toHaveProperty('total')
    expect(data).toHaveProperty('max_allowed')
  })

  test('5. 决策对话框功能', async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)
    await mockProjectStream(page, [
      {
        type: 'critical_decisions',
        data: {
          decisions: [{
            id: 'auth',
            question: '认证方式选择',
            context: '需要确定登录方案',
            options: [
              { label: 'JWT', description: '无状态令牌' },
              { label: 'Session', description: '服务端会话' },
            ],
            default: 'JWT',
          }],
        },
      },
      doneEvent('e2e-decisions'),
    ])
    const decisionCalls = []
    await page.route('**/api/v1/agent/session/*/decision', route => {
      decisionCalls.push(route.request().postData())
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' })
    })

    await gotoAgent(page)
    await page.getByRole('textbox', { name: '项目需求' }).fill('需要认证的电商系统')
    await page.getByRole('button', { name: '发送需求' }).click()

    const card = page.locator('.decision-card')
    await expect(card).toBeVisible({ timeout: 15000 })
    await expect(card).toContainText('认证方式选择')
    await expect(page.locator('.decision-btn')).toHaveCount(2)
    await expect(page.getByRole('button', { name: '默认值' })).toBeVisible()
    await expect(page.getByRole('button', { name: '确认', exact: true })).toBeVisible()

    await page.locator('.decision-btn').first().click()
    await expect(page.locator('.decision-btn').first()).toHaveClass(/active/)
    await page.getByRole('button', { name: '确认', exact: true }).click()

    await expect.poll(() => decisionCalls.length, { timeout: 10000 }).toBe(1)
    expect(JSON.parse(decisionCalls[0])).toEqual({ auth: 'JWT' })
    await expect(page.locator('.decision-card')).toHaveCount(0)
  })

  test('6. 会话操作 API', async ({ page, request }) => {
    const login = await apiLogin(page)
    const token = login.token
    const auth = { Authorization: `Bearer ${token}` }

    const decision = await request.post('/api/v1/agent/session/test_session_123/decision', {
      headers: auth,
      data: { auth: 'JWT' },
    })
    expect([200, 401, 404, 422]).toContain(decision.status())

    const action = await request.post('/api/v1/agent/session/test_session_123/action?action=cancel', {
      headers: auth,
    })
    expect([200, 401, 404]).toContain(action.status())

    const remove = await request.delete('/api/v1/agent/sessions/test_session_123', { headers: auth })
    expect([200, 401, 404]).toContain(remove.status())
  })

  test('7. 全局约束随生成请求下发', async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)

    const calls = []
    await mockProjectStream(page, [doneEvent('e2e-constraints')], request => calls.push(request.postData()))

    await gotoAgent(page)
    const requirement = '创建一个在线教育平台，必须使用 Redis 缓存，所有 service 使用 async/await'
    await page.getByRole('textbox', { name: '项目需求' }).fill(requirement)
    await page.getByRole('button', { name: '发送需求' }).click()

    await expect.poll(() => calls.length, { timeout: 15000 }).toBe(1)
    const body = JSON.parse(calls[0])
    expect(body.requirement).toBe(requirement)
    expect(body).toHaveProperty('enable_review')
    expect(body).toHaveProperty('enable_validation')
    expect(body).toHaveProperty('enable_memory')
    expect(body).toHaveProperty('cross_validation_fallback')
  })

  test('8. 文件生成与预览', async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)
    await mockProjectStream(page, [
      fileEvent('src/App.vue', '<template><div>preview</div></template>'),
      doneEvent('e2e-preview'),
    ])

    await gotoAgent(page)
    await page.getByRole('textbox', { name: '项目需求' }).fill('生成预览项目')
    await page.getByRole('button', { name: '发送需求' }).click()

    const fileItem = page.locator('.file-item').first()
    await expect(fileItem).toBeVisible({ timeout: 15000 })
    await fileItem.click()

    const panel = page.locator('.agent-file-panel')
    await expect(panel).toContainText('src/App.vue')
    await expect(panel.locator('.code-block')).toContainText('preview')
    await expect(panel.getByRole('button', { name: '复制' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '下载' })).toBeVisible()
  })

  test('9. 日志和进度显示', async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)
    await mockProjectStream(page, [
      progressEvent('analyzing', '分析需求', 30),
      { type: 'log', data: { message: 'E2E 日志消息' } },
      doneEvent('e2e-logs'),
    ])

    await gotoAgent(page)
    await page.getByRole('textbox', { name: '项目需求' }).fill('生成日志项目')
    await page.getByRole('button', { name: '发送需求' }).click()

    await expect(page.locator('.progress-value')).toHaveText('100%', { timeout: 15000 })
    const logsHeader = page.locator('.merged-section-header[aria-label="展开或收起消息日志"]')
    await expect(logsHeader).toBeVisible()
    await logsHeader.click()
    await expect(page.locator('.log-item-merged').filter({ hasText: 'E2E 日志消息' })).toBeVisible()
    await expect(page.locator('.log-item-merged.log-success').filter({ hasText: '项目生成完成' })).toBeVisible()
  })

  test('10. 资源加载与页面稳定性', async ({ page }) => {
    await apiLogin(page)
    const pageErrors = []
    page.on('pageerror', error => pageErrors.push(error.message))

    const startedAt = Date.now()
    await gotoAgent(page)
    expect(Date.now() - startedAt).toBeLessThan(10000)

    await expect(page.locator('.agent-topbar')).toBeVisible()
    await expect(page.locator('.empty-guide li')).toHaveCount(3)
    expect(pageErrors).toEqual([])
  })
})
