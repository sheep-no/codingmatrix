/**
 * 在线环境深度诊断
 * 检查白屏的真正原因
 */
import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

const ONLINE_URL = 'https://3000-9f66c22588b66963.monkeycode-ai.online'
const API_URL = 'http://localhost:8000'

test.describe('在线环境白屏深度诊断', () => {
  test('检查 Vue 应用状态和错误', async ({ page }) => {
    test.slow()

    // 监听所有页面事件
    page.on('console', msg => {
      console.log(`[CONSOLE] ${msg.type()}: ${msg.text().substring(0, 200)}`)
    })

    page.on('pageerror', error => {
      console.error(`[PAGE ERROR] ${error.message}`)
      console.error(`Stack: ${error.stack}`)
    })

    page.on('requestfailed', request => {
      console.log(`[REQUEST FAILED] ${request.url()} - ${request.failure()?.errorText}`)
    })

    // 登录
    await apiLogin(page)  // apiLogin 使用默认的 localhost:3000 作为 frontend
    await page.waitForTimeout(1000)

    // 导航到 /agent
    const response = await page.goto(`${ONLINE_URL}/agent`, { 
      waitUntil: 'domcontentloaded',
      timeout: 30000 
    })

    console.log(`Navigation response status: ${response?.status()}`)

    await page.waitForTimeout(5000)

    // 检查当前 URL（是否被重定向）
    const currentUrl = page.url()
    console.log(`Current URL after navigation: ${currentUrl}`)

    // 检查页面内容
    const pageContent = await page.evaluate(() => {
      const app = document.getElementById('app')
      return {
        appOuterHTML: app?.outerHTML.substring(0, 500),
        appChildNodes: app?.childNodes.length,
        hasContent: !!app?.innerHTML.trim(),
        bodyInnerHTML: document.body.innerHTML.substring(0, 500),
      }
    })

    console.log('Page Content:', JSON.stringify(pageContent, null, 2))

    // 截图
    await page.screenshot({ path: 'test-results/online-deep-diagnosis.png', fullPage: true })

    expect(pageContent.hasContent).toBeTruthy()
  })
})
