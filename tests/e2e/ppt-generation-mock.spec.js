import { test, expect } from '@playwright/test'

const outline = {
  id: 'outline-e2e',
  version: 2,
  status: 'draft',
  scenario: 'business',
  template_id: 'modern',
  slides: [
    {
      id: 'slide-1',
      position: 0,
      slide_type: 'key_points',
      narrative_role: 'opportunity_map',
      title: '市场机会',
      key_message: '增长窗口正在打开',
      content_blocks: [{ type: 'text', content: '验证客户需求并锁定首批场景', metadata: {} }],
    },
  ],
}

function json(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('PPT 三步生成流程（mock）', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'e2e-token')
      localStorage.setItem('codingmatrix_apikeys', JSON.stringify([
        { token: 'e2e-provider-token', provider: 'siliconflow', enabled: true },
      ]))

      class MockWebSocket {
        constructor() {
          this.readyState = 1
          setTimeout(() => this.onmessage?.({ data: JSON.stringify({
            type: 'progress', progress: 0.6, step: 'rendering', message: '正在渲染页面',
          }) }), 20)
          setTimeout(() => this.onmessage?.({ data: JSON.stringify({
            type: 'completed', result: {
              ppt_id: 'ppt-e2e',
              slides: [{ title: '市场机会', content: '增长窗口正在打开' }],
            },
          }) }), 50)
        }
        close() {
          this.readyState = 3
          this.onclose?.({ code: 1000 })
        }
      }
      window.WebSocket = MockWebSocket
    })

    await page.route('**/api/v1/pptx/**', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname

      if (path === '/api/v1/pptx/templates') {
        return json(route, { templates: [{ id: 'modern', name: '现代商务', primary_color: '#2563eb' }] })
      }
      if (path === '/api/v1/pptx/history') {
        return json(route, { records: [], total: 0 })
      }
      if (path === '/api/v1/pptx/outlines' && request.method() === 'POST') {
        return json(route, outline)
      }
      if (path === '/api/v1/pptx/outlines/outline-e2e' && request.method() === 'PATCH') {
        return json(route, { ...outline, version: 3 })
      }
      if (path === '/api/v1/pptx/outlines/outline-e2e/approve') {
        return json(route, { ...outline, version: 3, status: 'approved' })
      }
      if (path === '/api/v1/pptx/outlines/outline-e2e/generate') {
        return json(route, { task_id: 'task-e2e', status: 'queued' })
      }
      if (path === '/api/v1/pptx/ppt-e2e/quality-report') {
        return json(route, {
          overall_score: 92,
          quality_mode: 'standard',
          outline_version: 3,
          slide_scores: { 'slide-1': 92 },
          issues: [{ slide_id: 'slide-1', issue_type: 'text_overflow', severity: 'medium', message: '页面内容接近容量上限', fix_action: 'reduce_text_or_switch_layout' }],
          reflow_attempts: { 'slide-1': 1 },
          manual_review_slides: ['slide-1'],
        })
      }
      if (path === '/api/v1/pptx/ppt-e2e/slides') {
        return json(route, { slides: [{ title: '市场机会', content: '增长窗口正在打开' }] })
      }
      if (path === '/api/v1/pptx/download/ppt-e2e') {
        return route.fulfill({ status: 200, contentType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', body: 'pptx-mock' })
      }
      return json(route, {})
    })
  })

  test('从草稿编辑、批准、生成到质量报告和下载', async ({ page }) => {
    await page.goto('/ppt-generate')
    await page.getByPlaceholder(/请输入 PPT 主题/).fill('2026 年人工智能市场机会')
    await page.getByRole('button', { name: '一键生成 PPT' }).click()

    await expect(page.getByText('第 2 步：审阅大纲')).toBeVisible()
    await expect(page.locator('.outline-title-input')).toHaveValue('市场机会')
    await page.locator('.outline-message-input').fill('增长窗口正在打开，应该立即验证')
    await page.getByRole('button', { name: '批准大纲并继续' }).click()

    await expect(page.getByText('第 3 步：选择质量模式')).toBeVisible()
    await page.getByRole('button', { name: '开始生成 PPT' }).click()
    await expect(page.getByText('正在渲染页面')).toBeVisible()
    await expect(page.getByText('生成成功!')).toBeVisible()

    await page.getByRole('button', { name: '在线预览' }).click()
    await expect(page).toHaveURL(/ppt-preview\/ppt-e2e/)
    await expect(page.getByText('生成质量 92')).toBeVisible()
    await expect(page.getByText('需人工复核：slide-1')).toBeVisible()
    await expect(page.getByText('修复动作：缩减文本或切换布局')).toBeVisible()

    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '下载 PPTX' }).click()
    await expect((await download).suggestedFilename()).toBe('ppt-ppt-e2e.pptx')
  })
})
