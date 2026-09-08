import { test, expect } from '@playwright/test'

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test(`结构预览和质量报告同时可见 ${viewport.width}`, async ({ page }) => {
    const runtimeErrors = []
    page.on('pageerror', error => runtimeErrors.push(error.message))
    await page.setViewportSize(viewport)
    await page.addInitScript(() => localStorage.setItem('access_token', 'mock-preview-token'))
    await page.route('**/api/v1/**', route => {
      const path = new URL(route.request().url()).pathname
      let body = {}
      if (path.endsWith('/quality-report')) {
        body = {
          overall_score: 88, quality_mode: 'refined', outline_version: 1, outline_id: 'outline-test',
          degraded_stage: 'vision_review_unavailable',
          issues: [{ slide_id: 'slide-1', issue_type: 'text_overflow', message: '需要复核' }],
        }
      } else if (path.endsWith('/slides')) {
        body = { slides: [{ title: '内容块页面', content_blocks: [{ content: '本页结构内容完整显示' }] }] }
      } else if (path.endsWith('/outlines/outline-test')) {
        body = { id: 'outline-test', version: 1, slides: [{
          id: 'slide-1', position: 0, title: '内容块页面', key_message: '核心结论',
          content_blocks: [{ type: 'text', content: '本页结构内容完整显示', metadata: {} }],
        }] }
      } else if (path.includes('/pptx/preview/') || path.endsWith('/pdf')) {
        return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Unavailable"}' })
      }
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    })
    await page.goto('/ppt-preview/mock-deck')
    await expect(page.getByText('生成质量 88')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('本页结构内容完整显示')).toBeVisible()
    await expect(page.getByText(/结构预览：用于核对内容/)).toBeVisible()
    await expect(page.getByText(/重新导出整份 PPTX/)).toBeVisible()
    await page.locator('.slide-title-input').fill('定向修改标题')
    await expect(page.getByRole('button', { name: '保存修改并导出整份新文件' })).toBeVisible()
    await expect(page.locator('.quality-report-warning')).toContainText('视觉复审未完成')
    await expect(page.getByRole('button', { name: '检查模型设置' })).toBeVisible()
    await expect(page.getByText('暂无幻灯片数据')).toHaveCount(0)
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    expect(fits).toBe(true)
    expect(runtimeErrors).toEqual([])
  })

  test(`自动模板选择与规范结果 ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'mock-preview-token')
      localStorage.setItem('codingmatrix_apikeys', JSON.stringify([{ provider: 'siliconflow', enabled: true, token: 'mock-model-token' }]))
    })
    let submittedTemplate
    await page.route('**/api/v1/**', route => {
      const url = new URL(route.request().url())
      let body = {}
      if (url.pathname.endsWith('/templates')) {
        body = url.searchParams.has('topic') ? { scenario: 'business', templates: ['business_report'] } : {
          templates: [{ id: 'business_report', name_zh: '商务报告', description: '季度经营复盘', scenarios: ['business'], primary_color: '#123456' }],
        }
      } else if (url.pathname.endsWith('/outlines')) {
        submittedTemplate = route.request().postDataJSON().template_id
        body = { id: 'outline-test', template_id: 'business_report', scenario: 'business', slides: [{
          id: 'slide-1', title: '经营概况', key_message: '持续增长', content_blocks: [{ content: '季度经营数据' }],
        }] }
      }
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    })
    await page.goto('/ppt-generate')
    await expect(page.getByText('季度经营复盘')).toBeVisible({ timeout: 15000 })
    await page.locator('.template-auto').click()
    await page.locator('.form-group textarea').first().fill('季度经营汇报')
    await page.getByRole('button', { name: '一键生成 PPT' }).click()
    await expect(page.locator('.template-result')).toContainText('自动选择结果：商务报告')
    await expect(page.locator('.template-result')).toContainText('模板 ID：business_report')
    await expect(page.locator('.template-result')).toContainText('推荐模板：商务报告')
    expect(submittedTemplate).toBe('auto')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
}
