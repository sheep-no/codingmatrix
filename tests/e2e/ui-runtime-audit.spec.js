import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

const viewports = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 }
}

const pages = [
  { name: 'home', path: '/', ready: 'main' },
  { name: 'agent', path: '/agent', ready: '[data-testid="agent-prompt-input"]' },
  { name: 'workflow', path: '/workflow', ready: '.workflow-page' },
  { name: 'ppt-generate', path: '/ppt-generate', ready: '.ppt-generate-page' },
  { name: 'image-generate', path: '/image-generate', ready: '.image-generate-page' },
  { name: 'settings', path: '/settings', ready: '.settings-page' },
  { name: 'capabilities', path: '/capabilities', ready: '.capability-page' },
  { name: 'docs', path: '/docs', ready: '.docs-page' },
  { name: 'chart-editor', path: '/chart-editor', ready: '.chart-editor-page' },
  { name: 'admin', path: '/admin', ready: '.admin-panel' },
  { name: 'admin-dashboard', path: '/admin/dashboard', ready: '.admin-dashboard' }
]

test.describe('页面运行时与布局审计', () => {
  test.setTimeout(240000)

  test('核心页面无脚本异常且移动端无横向溢出', async ({ page }) => {
    const runtimeErrors = []
    page.on('pageerror', error => runtimeErrors.push(error.message))
    page.on('console', message => {
      if (message.type() === 'error') runtimeErrors.push(message.text())
    })

    await apiLogin(page)

    for (const [viewportName, viewport] of Object.entries(viewports)) {
      await page.setViewportSize(viewport)

      for (const item of pages) {
        await page.goto(item.path)
        await expect(page.locator(item.ready).first()).toBeVisible({ timeout: 30000 })
        await page.waitForTimeout(800)

        const dimensions = await page.evaluate(() => ({
          viewportWidth: window.innerWidth,
          contentWidth: document.documentElement.scrollWidth
        }))
        expect(
          dimensions.contentWidth,
          `${item.path} 在 ${viewportName} 下横向溢出`
        ).toBeLessThanOrEqual(dimensions.viewportWidth)

        if (viewportName === 'mobile' && item.name === 'admin') {
          const bodyLayout = await page.locator('.admin-body').evaluate(element => ({
            direction: getComputedStyle(element).flexDirection,
            mainWidth: element.querySelector('.admin-main').getBoundingClientRect().width
          }))
          expect(bodyLayout.direction).toBe('column')
          expect(bodyLayout.mainWidth).toBeGreaterThanOrEqual(viewport.width - 2)
        }

        await page.screenshot({
          path: `test-results/ui-audit/${item.name}-${viewportName}.png`,
          fullPage: true
        })
      }
    }

    expect(runtimeErrors, `页面运行时错误:\n${runtimeErrors.join('\n')}`).toEqual([])
  })
})
