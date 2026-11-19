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

async function openAgent(page) {
  await page.goto('/agent', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('textbox', { name: '项目需求' })).toBeVisible({ timeout: 15000 })
}

test.describe('完整项目生成流程测试', () => {
  test.beforeEach(async ({ page }) => {
    await seedMockKeys(page)
    await apiLogin(page)
    await mockModelContext(page)
  })

  test('1. 简单项目生成完整流程', async ({ page }) => {
    const calls = []
    await mockProjectStream(page, [
      progressEvent('analyzing', '分析需求', 25),
      fileEvent('src/App.vue', '<template><div>todo</div></template>'),
      fileEvent('app/main.py', 'print("todo")'),
      doneEvent('e2e-todo'),
    ], request => calls.push(request.postData()))

    await openAgent(page)
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    await expect(prompt).toBeVisible()

    const testPrompt = '创建一个简单的待办事项应用，包含添加、删除和标记完成功能'
    await prompt.fill(testPrompt)
    await expect(prompt).toHaveValue(testPrompt)

    const sendButton = page.getByRole('button', { name: '发送需求' })
    await expect(sendButton).toBeEnabled()
    await sendButton.click()

    await expect.poll(() => calls.length, { timeout: 15000 }).toBe(1)
    const body = JSON.parse(calls[0])
    expect(body.requirement).toBe(testPrompt)
    expect(body.incremental).toBe(false)

    await expect(page.locator('.progress-track')).toHaveAttribute('aria-valuenow', '100', { timeout: 15000 })
    await expect(page.locator('.timeline-item')).toHaveCount(1)
    await expect(page.locator('.timeline-item .stage-status-tag')).toHaveText('完成')
    await expect(page.locator('.file-item')).toHaveCount(2)
    await expect(page.locator('.topbar-status')).toHaveClass(/status-completed/)

    const logsHeader = page.locator('.merged-section-header[aria-label="展开或收起消息日志"]')
    await expect(logsHeader).toBeVisible()
    await logsHeader.click()
    await expect(page.locator('.log-item-merged.log-success').filter({ hasText: '项目生成完成' })).toBeVisible()

    await page.locator('.file-item').first().click()
    const panel = page.locator('.agent-file-panel')
    await expect(panel.locator('.code-block')).toContainText('todo')
    await expect(panel).toContainText('行')

    await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible()
    await expect(page.getByRole('button', { name: '停止生成' })).toHaveCount(0)
  })

  test('2. 增量生成流程', async ({ page }) => {
    const calls = []
    await mockProjectStream(page, [
      fileEvent('src/App.vue', '<template><div>v1</div></template>'),
      doneEvent('e2e-project'),
    ], request => calls.push(request.postData()))

    await openAgent(page)
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    const sendButton = page.getByRole('button', { name: '发送需求' })

    await prompt.fill('第一个项目')
    await sendButton.click()
    await expect(page.locator('.file-item')).toHaveCount(1, { timeout: 15000 })
    await expect(page.locator('.topbar-status')).toHaveClass(/status-completed/)

    await prompt.fill('第二个项目，追加导出功能')
    await sendButton.click()
    await expect.poll(() => calls.length, { timeout: 15000 }).toBe(2)

    const second = JSON.parse(calls[1])
    expect(second.incremental).toBe(true)
    expect(second.project_path).toBe('e2e-project')
    expect(second.requirement).toContain('追加导出功能')
  })

  test('3. 空输入与超长输入处理', async ({ page }) => {
    await page.route('**/api/v1/agent/orchestrate/stream', route => route.abort())
    await openAgent(page)

    const prompt = page.getByRole('textbox', { name: '项目需求' })
    const sendButton = page.getByRole('button', { name: '发送需求' })

    await expect(sendButton).toBeDisabled()
    await prompt.fill('   ')
    await expect(sendButton).toBeDisabled()

    const longInput = '这是一个很长的项目描述。'.repeat(50)
    await prompt.fill(longInput)
    await expect(prompt).toHaveValue(longInput)
    await expect(sendButton).toBeEnabled()
  })

  test('4. 重新生成与清空状态', async ({ page }) => {
    let streamCount = 0
    await page.route('**/api/v1/agent/orchestrate/stream', route => {
      streamCount += 1
      const projectPath = `e2e-run-${streamCount}`
      return route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: [
          `data: ${JSON.stringify(fileEvent('src/App.vue', `<template>run${streamCount}</template>`))}`,
          '',
          `data: ${JSON.stringify(doneEvent(projectPath))}`,
          '',
        ].join('\n'),
      })
    })

    await openAgent(page)
    await page.getByRole('textbox', { name: '项目需求' }).fill('第一个项目')
    await page.getByRole('button', { name: '发送需求' }).click()
    await expect(page.locator('.file-item')).toHaveCount(1, { timeout: 15000 })
    await expect(page.locator('.topbar-status')).toHaveClass(/status-completed/)

    const regenerate = page.getByRole('button', { name: '重新生成' })
    await expect(regenerate).toBeVisible()
    await regenerate.click()
    await expect.poll(() => streamCount, { timeout: 15000 }).toBe(1)
    await page.getByRole('textbox', { name: '项目需求' }).fill('第二个项目')
    await page.getByRole('button', { name: '发送需求' }).click()
    await expect.poll(() => streamCount, { timeout: 15000 }).toBe(2)
    await expect(page.locator('.agent-workspace')).toContainText('run2', { timeout: 15000 })

    await page.locator('.action-btn', { hasText: '清空' }).click()
    await expect(page.locator('.file-item')).toHaveCount(0)
    await expect(page.locator('.empty-title').first()).toHaveText('从一个想法，开始构建')
    await expect(page.getByRole('textbox', { name: '项目需求' })).toHaveValue('')
  })

  test('5. 项目保存与已保存列表', async ({ page }) => {
    const saveBodies = []
    await page.route('**/api/v1/agent/save', route => {
      saveBodies.push(JSON.parse(route.request().postData()))
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"id":1,"name":"e2e-saved","message":"项目保存成功"}',
      })
    })
    await page.route('**/api/v1/github/config', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"use_github":false}',
    }))
    await mockProjectStream(page, [
      fileEvent('src/App.vue', '<template><div>saved</div></template>'),
      doneEvent('e2e-saved'),
    ])

    await openAgent(page)
    await page.getByRole('textbox', { name: '项目需求' }).fill('测试保存功能的项目')
    await page.getByRole('button', { name: '发送需求' }).click()
    await expect(page.locator('.file-item')).toHaveCount(1, { timeout: 15000 })

    await page.getByRole('button', { name: '更多 Agent 操作' }).click()
    const saveButton = page.locator('.topbar-dropdown button', { hasText: '保存项目' })
    await expect(saveButton).toBeEnabled()
    await saveButton.click()

    await expect.poll(() => saveBodies.length, { timeout: 10000 }).toBe(1)
    expect(saveBodies[0].name).toContain('项目_')
    const projectData = JSON.parse(saveBodies[0].project_data)
    expect(projectData).toEqual([{ path: 'src/App.vue', content: '<template><div>saved</div></template>', name: 'App.vue' }])
    await expect(page.locator('.el-message').filter({ hasText: '项目已保存到数据库' })).toBeVisible()
  })

  test('6. UI 交互完整性', async ({ page }) => {
    await mockProjectStream(page, [
      fileEvent('src/App.vue', '<template><div>ui</div></template>'),
      doneEvent('e2e-ui'),
    ])

    await openAgent(page)
    const prompt = page.getByRole('textbox', { name: '项目需求' })
    await prompt.focus()
    await expect(prompt).toBeFocused()
    await prompt.type('测试输入')
    await expect(prompt).toHaveValue(/测试输入/)

    await page.getByRole('button', { name: '发送需求' }).click()
    await expect(page.locator('.file-item')).toHaveCount(1, { timeout: 15000 })

    await page.locator('.file-item').first().click()
    await expect(page.locator('.file-item').first()).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.agent-file-panel .code-block')).toContainText('ui')

    await page.locator('.category-header').first().click()
    await expect(page.locator('.file-item')).toHaveCount(0)
    await page.locator('.category-header').first().click()
    await expect(page.locator('.file-item')).toHaveCount(1)
  })
})
