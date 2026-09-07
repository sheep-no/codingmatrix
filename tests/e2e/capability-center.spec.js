import { expect, test } from '@playwright/test'

async function openCapabilityCenter(page) {
  await page.route('**/api/v1/csrf-token', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ csrf_token: 'capability-center-e2e-csrf' })
  }))
  await page.route('**/api/v1/skills/list', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{ name: 'review', category: 'workflow' }])
  }))
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))
    localStorage.setItem('access_token', `header.${payload}.signature`)
    localStorage.setItem('permission_level', 'user')
  })
  await page.goto('/capabilities')
  await expect(page.getByRole('heading', { name: '能力中心' })).toBeVisible({ timeout: 30000 })
}

test.describe('能力中心', () => {
  test('按需加载面板并在移动端保持可操作', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    let skillRequests = 0
    page.on('request', request => {
      if (request.url().includes('/api/v1/skills/list')) skillRequests += 1
    })

    await openCapabilityCenter(page)
    expect(skillRequests).toBe(0)

    await page.getByRole('tab', { name: 'Skills' }).click()
    await expect(page.getByText('review · workflow')).toBeVisible()
    expect(skillRequests).toBe(1)

    await page.getByRole('tab', { name: '视觉工具' }).click()
    await page.getByRole('tab', { name: 'Skills' }).click()
    expect(skillRequests).toBe(1)

    const dimensions = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      contentWidth: document.documentElement.scrollWidth
    }))
    expect(dimensions.contentWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
  })
})
