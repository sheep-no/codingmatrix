/**
 * 在线预览环境 /agent 页面白屏问题诊断
 */
import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

// 预览域名会随会话变化，默认回到当前运行的 baseURL
const ONLINE_URL = process.env.ONLINE_URL || process.env.BASE_URL || 'http://127.0.0.1:3000'

test.describe('在线预览环境 /agent 白屏诊断', () => {
  test('诊断 /agent 页面渲染问题', async ({ page }) => {
    test.slow()

    // 收集控制台日志
    const consoleMessages = []
    const errors = []

    page.on('console', msg => {
      consoleMessages.push({ type: msg.type(), text: msg.text() })
      console.log(`[CONSOLE] ${msg.type()}: ${msg.text()}`)
    })

    page.on('pageerror', error => {
      errors.push(error.message)
      console.error(`[PAGE ERROR]: ${error.message}`)
    })

    // 登录后才能进入受保护的 /agent 页面，否则会被守卫重定向
    await apiLogin(page, ONLINE_URL)

    // 访问 /agent 页面
    console.log(`Navigating to ${ONLINE_URL}/agent`)
    await page.goto(`${ONLINE_URL}/agent`, { 
      waitUntil: 'domcontentloaded',
      timeout: 30000 
    })

    await page.waitForTimeout(5000)

    // 截图
    await page.screenshot({ path: 'test-results/agent-diagnosis.png', fullPage: true })

    // 检查 DOM 状态
    const domInfo = await page.evaluate(() => {
      return {
        appExists: !!document.getElementById('app'),
        appInnerHTML: document.getElementById('app')?.innerHTML.substring(0, 200),
        bodyExists: !!document.body,
        hasAgentPageClass: !!document.querySelector('.agent-page'),
        hasRouterView: !!document.querySelector('[data-v-router]'),
        documentTitle: document.title,
        htmlClasses: document.documentElement.className,
      }
    })

    console.log('DOM Info:', JSON.stringify(domInfo, null, 2))

    // 检查是否有任何 Vue 错误
    const vueErrors = errors.filter(e => e.includes('Vue') || e.includes('vue'))
    console.log('Vue Errors:', vueErrors)

    // 检查路由状态
    const routeInfo = await page.evaluate(() => {
      return {
        currentPath: window.location.pathname,
        currentHash: window.location.hash,
        hasVueRouter: !!window.$route,
      }
    })

    console.log('Route Info:', JSON.stringify(routeInfo, null, 2))

    // 期望：至少应该有一些 DOM 元素
    expect(domInfo.appExists).toBeTruthy()
    expect(domInfo.hasAgentPageClass).toBeTruthy()
  })
})
