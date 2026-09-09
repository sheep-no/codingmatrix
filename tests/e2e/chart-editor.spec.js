import { expect, test } from '@playwright/test'
import { stat } from 'node:fs/promises'

const salesData = [
  { month: 'Jan', sales: 12 },
  { month: 'Feb', sales: 24 },
  { month: 'Mar', sales: 18 }
]

async function openEditor(page) {
  await page.route('**/api/v1/csrf-token', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ csrf_token: 'chart-editor-e2e-csrf' })
  }))
  await page.route('**/api/v1/refresh', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ access_token: 'chart-editor-e2e-token', expires_in: 3600 })
  }))
  await page.addInitScript(() => {
    const expiry = Date.now() + 3600000
    sessionStorage.setItem('_token', 'chart-editor-e2e-token')
    sessionStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('access_token', 'chart-editor-e2e-token')
    localStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('username', 'chart-editor-e2e')
    localStorage.setItem('permission_level', 'user')
  })
  await page.goto('/chart-editor')
  await expect(page.getByRole('heading', { name: '图表编辑器' })).toBeVisible({ timeout: 30000 })
}

async function uploadSalesData(page) {
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'sales.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(salesData))
  })
  await expect(page.locator('.data-item')).toContainText('3 行 · 2 字段')
}

test.describe('图表编辑器实测', () => {
  test.setTimeout(120000)

  test('完成导入、编辑、撤销重做、导出和草稿恢复', async ({ page }) => {
    await openEditor(page)
    await page.evaluate(() => localStorage.removeItem('chart-editor-draft-v1:chart-editor-e2e'))
    await page.reload()

    await uploadSalesData(page)
    await page.getByRole('button', { name: '添加图表' }).click()
    await expect(page.locator('.chart-preview-item')).toHaveCount(1)
    await expect(page.locator('.chart-container canvas')).toBeVisible()
    const canvasSize = await page.locator('.chart-container canvas').evaluate(canvas => ({
      width: canvas.width,
      height: canvas.height
    }))
    expect(canvasSize.width).toBeGreaterThan(0)
    expect(canvasSize.height).toBeGreaterThan(0)

    const titleInput = page.getByPlaceholder('图表标题')
    await titleInput.fill('第一版销售趋势')
    await page.waitForTimeout(300)
    await titleInput.fill('月度销售趋势')
    await page.waitForTimeout(300)
    await expect(page.locator('.chart-preview-title')).toHaveText('月度销售趋势')

    await page.keyboard.press('Control+z')
    await expect(page.locator('.chart-preview-title')).toHaveText('第一版销售趋势')
    await page.keyboard.press('Control+Shift+z')
    await expect(page.locator('.chart-preview-title')).toHaveText('月度销售趋势')

    await page.getByRole('button', { name: '删除图表' }).click()
    await expect(page.locator('.chart-preview-item')).toHaveCount(0)
    await page.getByRole('button', { name: '撤销' }).click()
    await expect(page.locator('.chart-preview-title')).toHaveText('月度销售趋势')
    await page.getByRole('button', { name: '重做' }).click()
    await expect(page.locator('.chart-preview-item')).toHaveCount(0)
    await page.getByRole('button', { name: '撤销' }).click()

    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出此图表' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('月度销售趋势.png')
    const downloadedFile = await download.path()
    expect((await stat(downloadedFile)).size).toBeGreaterThan(0)

    await page.getByRole('button', { name: '切换为深色' }).click()
    await expect(page.locator('.editor-content')).toHaveClass(/dark-theme/)
    await page.waitForTimeout(300)
    await page.reload()

    await expect(page.locator('.data-item')).toContainText('sales.json')
    await expect(page.locator('.chart-preview-title')).toHaveText('月度销售趋势')
    await expect(page.locator('.editor-content')).toHaveClass(/dark-theme/)
    const storedDraft = await page.evaluate(() => JSON.parse(localStorage.getItem('chart-editor-draft-v1:chart-editor-e2e')))
    expect(storedDraft.charts[0]).not.toHaveProperty('sourceData')
  })

  test('移动端保持可操作且没有横向溢出', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openEditor(page)
    await page.evaluate(() => localStorage.removeItem('chart-editor-draft-v1:chart-editor-e2e'))
    await page.reload()

    await uploadSalesData(page)
    await page.getByRole('button', { name: '添加图表' }).click()
    await expect(page.locator('.chart-container canvas')).toBeVisible()
    const dimensions = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      contentWidth: document.documentElement.scrollWidth
    }))
    expect(dimensions.contentWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
  })
})
