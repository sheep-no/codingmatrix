import { expect, test } from '@playwright/test'

const viewports = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 390, height: 844 }
}

async function expectNoHorizontalOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    contentWidth: document.documentElement.scrollWidth
  }))
  expect(dimensions.contentWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
}

test.describe('首页响应式工作台', () => {
  test('覆盖桌面、平板和移动端导航与输入区', async ({ page }) => {
    await page.setViewportSize(viewports.desktop)
    await page.goto('/')
    await expect(page.getByRole('main')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('#leftlist')).toBeVisible()
    await expect(page.getByRole('button', { name: '打开主导航' })).toBeHidden()

    await page.setViewportSize(viewports.tablet)
    const menuButton = page.getByRole('button', { name: '打开主导航' })
    await expect(menuButton).toBeVisible()
    await menuButton.click()
    await expect(page.locator('#leftlist')).toHaveClass(/mobile-home-drawer-open/)
    await expect(page.getByRole('button', { name: '关闭主导航' })).toBeVisible()
    await page.getByRole('button', { name: '关闭主导航' }).click()
    await expect(menuButton).toBeFocused()

    await page.setViewportSize(viewports.mobile)
    await expect(page.getByRole('main')).toBeVisible()
    await expect(page.getByRole('region', { name: '消息输入区域' })).toBeVisible()
    const inputFontSize = await page.getByRole('textbox', { name: '消息输入框' }).evaluate(element => parseFloat(getComputedStyle(element).fontSize))
    expect(inputFontSize).toBeGreaterThanOrEqual(16)
    await expectNoHorizontalOverflow(page)
  })
})
