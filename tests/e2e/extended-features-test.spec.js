import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'
import {
  doneEvent,
  fileEvent,
  mockModelContext,
  mockProjectStream,
  seedMockKeys,
} from './fixtures/agentMock.js'

async function openAgent(page) {
  await page.goto('/agent', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('textbox', { name: '项目需求' })).toBeVisible({ timeout: 15000 })
}

async function generateOnce(page, events = [fileEvent('src/App.vue', '<template><div>e2e</div></template>'), doneEvent('e2e-project')]) {
  await mockProjectStream(page, events)
  await openAgent(page)
  await page.getByRole('textbox', { name: '项目需求' }).fill('生成一个演示项目')
  await page.getByRole('button', { name: '发送需求' }).click()
  await expect(page.locator('.topbar-status')).toHaveClass(/status-completed/, { timeout: 15000 })
}

test.describe('扩展功能测试', () => {
  test.beforeEach(async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)
  })

  test('1. 需求输入与快捷提示', async ({ page }) => {
    await openAgent(page)
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    await expect(prompt).toHaveAttribute('placeholder', /描述你想要生成的项目/)

    const guideItems = page.locator('.empty-guide li')
    await expect(guideItems).toHaveCount(3)
    await expect(guideItems.nth(0)).toContainText('描述需求')
    await expect(guideItems.nth(1)).toContainText('跟进执行')
    await expect(guideItems.nth(2)).toContainText('查看产物')
  })

  test('2. 文件编辑与右键面板', async ({ page }) => {
    await generateOnce(page)
    const fileItem = page.locator('.file-item').first()
    await fileItem.click()

    const panel = page.locator('.agent-file-panel')
    await expect(panel).toContainText('src/App.vue')
    await expect(panel.locator('.code-block')).toContainText('e2e')
    await expect(panel.getByRole('button', { name: '保存' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '历史' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '复制' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '下载' })).toBeVisible()
    await expect(panel.getByRole('button', { name: '删除' })).toBeVisible()
  })

  test('3. 日志显示与清空', async ({ page }) => {
    await generateOnce(page, [
      { type: 'log', data: { message: '扩展功能日志' } },
      fileEvent('src/App.vue'),
      doneEvent('e2e-logs'),
    ])

    const header = page.locator('.merged-section-header[aria-label="展开或收起消息日志"]')
    await expect(header).toBeVisible()
    await header.click()
    await expect(page.locator('.log-item-merged').filter({ hasText: '扩展功能日志' })).toBeVisible()
    await expect(page.locator('.log-item-merged.log-info').first()).toBeVisible()
    await expect(page.locator('.log-item-merged.log-success').filter({ hasText: '项目生成完成' })).toBeVisible()

    await page.locator('.merged-clear-btn').click()
    await expect(page.locator('.log-item-merged')).toHaveCount(0)
  })

  test('4. 项目保存功能', async ({ page }) => {
    const saved = []
    await page.route('**/api/v1/agent/save', route => {
      saved.push(JSON.parse(route.request().postData()))
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"id":1}' })
    })
    await page.route('**/api/v1/github/config', route => route.fulfill({
      status: 200, contentType: 'application/json', body: '{"use_github":false}',
    }))

    await generateOnce(page)
    await page.getByRole('button', { name: '更多 Agent 操作' }).click()
    const saveButton = page.locator('.topbar-dropdown button', { hasText: '保存项目' })
    await expect(saveButton).toBeEnabled()
    await saveButton.click()

    await expect.poll(() => saved.length, { timeout: 10000 }).toBe(1)
    expect(saved[0].project_data).toContain('src/App.vue')
    await expect(page.locator('.el-message').filter({ hasText: '项目已保存到数据库' })).toBeVisible()
  })

  test('5. 项目导入弹窗', async ({ page }) => {
    await openAgent(page)
    await page.getByRole('button', { name: '导入项目' }).click()

    const modal = page.locator('.modal-content', { hasText: '导入项目' })
    await expect(modal).toBeVisible()
    await expect(modal.locator('.upload-zone')).toBeVisible()
    await expect(modal.locator('.upload-zone input[type="file"]')).toHaveAttribute('accept', '.zip')
    await expect(modal.locator('.upload-zone')).toContainText('拖拽 ZIP 文件到此处')

    await modal.getByRole('button', { name: '关闭导入项目窗口' }).click()
    await expect(modal).toHaveCount(0)
  })

  test('6. 会话删除确认', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('agent_project_sessions', JSON.stringify([{
        id: 'seed-delete', prompt: '待删除项目', timestamp: Date.now(), filesCount: 1,
        files: [], logs: [], thinking: [], steps: [], workflowStages: [],
        pendingDecisions: [], decisionHistory: [], currentPhase: '', currentStep: 0,
        totalSteps: 0, startTime: null, modelAssignments: {}, modelConfigVersion: '',
        modelContextRevision: null, currentModel: null, currentAgent: null,
        fallbackHistory: [], recoveryAttempts: [],
      }]))
    })
    await page.route('**/api/v1/agent/projects/*', route => route.fulfill({
      status: 200, contentType: 'application/json', body: '{"ok":true}',
    }))
    await openAgent(page)

    const sessionItem = page.locator('.session-item').first()
    await expect(sessionItem).toBeVisible({ timeout: 15000 })
    await sessionItem.getByRole('button', { name: '永久删除项目' }).click()

    const confirm = page.locator('.el-message-box')
    await expect(confirm).toBeVisible()
    await expect(confirm).toContainText('永久删除')
    await confirm.getByRole('button', { name: '取消' }).click()
    await expect(sessionItem).toBeVisible()
  })

  test('7. 决策面板交互', async ({ page }) => {
    const decisionCalls = []
    await page.route('**/api/v1/agent/session/*/decision', route => {
      decisionCalls.push(JSON.parse(route.request().postData()))
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' })
    })
    await generateOnce(page, [
      {
        type: 'critical_decisions',
        data: {
          decisions: [{
            id: 'storage',
            question: '数据存储方式',
            context: '选择持久化方案',
            options: [
              { label: 'SQLite', description: '本地文件' },
              { label: 'PostgreSQL', description: '服务端数据库' },
            ],
            default: 'SQLite',
          }],
        },
      },
      fileEvent('src/App.vue', '<template><div>decision</div></template>'),
      doneEvent('e2e-decision'),
    ])

    const card = page.locator('.decision-card')
    await expect(card).toBeVisible()
    await expect(page.locator('.decision-btn')).toHaveCount(2)
    await expect(card.getByRole('button', { name: '默认值' })).toBeVisible()

    await card.getByRole('button', { name: '默认值' }).click()
    await expect(page.locator('.decision-btn.active')).toContainText('SQLite')
    await card.getByRole('button', { name: '确认', exact: true }).click()

    await expect.poll(() => decisionCalls.length, { timeout: 10000 }).toBe(1)
    expect(decisionCalls[0]).toEqual({ storage: 'SQLite' })
    await expect(card).toHaveCount(0)
  })

  test('8. 响应式布局', async ({ page }) => {
    await openAgent(page)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await expect(page.locator('.agent-sidebar')).toBeInViewport()
    await expect(page.locator('.agent-file-panel')).toBeInViewport()
    await expect(page.locator('.agent-mobile-toolbar')).toBeHidden()

    await page.setViewportSize({ width: 375, height: 667 })
    await expect(page.locator('.agent-mobile-toolbar')).toBeVisible()
    await expect(page.locator('.agent-main')).toBeVisible()

    await page.getByRole('button', { name: '打开会话列表' }).click()
    await expect(page.locator('.agent-sidebar')).toHaveClass(/mobile-drawer-open/)
    await expect(page.locator('.agent-mobile-scrim')).toBeVisible()
    await page.getByRole('button', { name: '关闭面板' }).click()
    await expect(page.locator('.agent-sidebar')).not.toHaveClass(/mobile-drawer-open/)
  })

  test('9. 输入框键盘行为', async ({ page }) => {
    await page.route('**/api/v1/agent/orchestrate/stream', route => route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: [
        `data: ${JSON.stringify(fileEvent('src/App.vue', '<template><div>keyboard</div></template>'))}`,
        `data: ${JSON.stringify(doneEvent('e2e-keyboard'))}`,
        '',
      ].join('\n\n'),
    }))
    const streamRequest = page.waitForRequest(
      (req) => req.url().includes('/agent/orchestrate/stream') && req.method() === 'POST',
      { timeout: 10000 },
    )
    await openAgent(page)
    const prompt = page.getByRole('textbox', { name: '项目需求' })

    await prompt.focus()
    await prompt.type('键盘输入')
    await expect(prompt).toHaveValue('键盘输入')

    await prompt.press('Enter')
    await expect(prompt).toHaveValue('键盘输入\n')

    await prompt.press('Control+Enter')
    const request = await streamRequest
    expect(JSON.parse(request.postData()).requirement).toContain('键盘输入')
    await expect(page.locator('.file-item').first()).toBeVisible({ timeout: 10000 })
  })

  test('10. 设置面板分区', async ({ page }) => {
    await openAgent(page)
    await page.getByRole('button', { name: '打开 Agent 设置' }).click()

    const modal = page.locator('.modal-content', { hasText: '设置' })
    await expect(modal).toBeVisible()
    await expect(modal.locator('h4')).toContainText(['API Key 配置', 'AI 模型配置', 'GitHub 保存', 'MCP 工具扩展'])
    await modal.locator('.modal-close').click()
    await expect(modal).toHaveCount(0)
  })

  test('11. 复杂度分析调用真实端点', async ({ page }) => {
    await openAgent(page)
    await page.getByRole('textbox', { name: '项目需求' }).fill(
      '生成一个待办事项管理系统：FastAPI 后端 + Vue 3 前端 + SQLite 数据库，包含 JWT 认证、任务增删改查与优先级排序',
    )

    const analyzeResponse = page.waitForResponse(
      (resp) => resp.url().includes('/agent/analyze_complexity') && resp.request().method() === 'POST',
    )
    await page.getByRole('button', { name: '更多 Agent 操作' }).click()
    await page.locator('.topbar-dropdown button', { hasText: '复杂度分析' }).click()

    const response = await analyzeResponse
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data.level).toBeTruthy()
    expect(data.estimated_files).toBeGreaterThan(0)
    expect(data.model_assignment).toBeTruthy()

    await expect(page.locator('.el-message').filter({ hasText: `复杂度级别: ${data.level}` })).toBeVisible({
      timeout: 10000,
    })
  })
})

test.describe('下载功能专项测试', () => {
  test.beforeEach(async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)
  })

  test('1. 文件下载触发', async ({ page }) => {
    await generateOnce(page)
    await page.locator('.file-item').first().click()

    const downloadPromise = page.waitForEvent('download', { timeout: 10000 })
    await page.locator('.agent-file-panel').getByRole('button', { name: '下载' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('App.vue')
    await expect(page.locator('.el-message').filter({ hasText: '已保存' })).toBeVisible()
  })

  test('2. 下载端点鉴权', async ({ page }) => {
    await openAgent(page)
    const anonymous = await page.request.get('/api/v1/agent/generate/download/test_project')
    expect([401, 403, 404]).toContain(anonymous.status())
  })
})
