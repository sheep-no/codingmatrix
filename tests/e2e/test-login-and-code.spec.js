// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 模拟用户登录并测试 Code API
 */
test.describe('用户登录并测试 Code API', () => {
  
  test('1. 登录并访问完整功能', async ({ page }) => {
    // 访问首页
    await page.goto('/')
    await page.waitForTimeout(3000)
    
    // 截图查看登录状态
    await page.screenshot({ path: 'test-results/login-01-initial.png', fullPage: true })
    
    // 检查是否有登录按钮或弹窗
    const loginButton = page.locator('button:has-text("登录"), button:has-text("Login"), [class*="login"]').first()
    const hasLoginButton = await loginButton.count() > 0
    console.log('找到登录按钮:', hasLoginButton)
    
    // 检查页面内容
    const pageText = await page.locator('body').innerText()
    console.log('页面包含登录:', pageText.includes('登录'))
    console.log('页面包含 API Key:', pageText.includes('API Key'))
    
    // 尝试通过 API 登录获取 token
    const loginResult = await page.evaluate(async () => {
      try {
        // 先获取 CSRF token
        const csrfResponse = await fetch('/api/v1/csrf-token')
        const csrfData = await csrfResponse.json()
        
        // 登录
        const loginResponse = await fetch('/api/v1/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfData.csrf_token
          },
          credentials: 'include',
          body: JSON.stringify({
            email: 'admin@example.com',
            password: 'admin123'
          })
        })
        
        const loginData = await loginResponse.json()
        return {
          success: loginResponse.ok,
          hasToken: !!loginData.access_token,
          token: loginData.access_token
        }
      } catch (e) {
        return { error: e.message }
      }
    })
    
    console.log('登录结果:', JSON.stringify(loginResult))
    
    // 如果登录成功，保存 token 到 localStorage
    if (loginResult.success && loginResult.token) {
      await page.evaluate((token) => {
        localStorage.setItem('access_token', token)
        // 同时保存到 user store
        const userStore = JSON.stringify({
          access_token: token,
          permission_level: 'superadmin',
          username: 'admin'
        })
        localStorage.setItem('user', userStore)
      }, loginResult.token)
      
      // 刷新页面使 token 生效
      await page.reload()
      await page.waitForTimeout(3000)
      await page.screenshot({ path: 'test-results/login-02-after-login.png', fullPage: true })
      
      // 检查登录后的页面
      const loggedInText = await page.locator('body').innerText()
      console.log('登录后页面包含设置:', loggedInText.includes('设置'))
      console.log('登录后页面包含 API Key:', loggedInText.includes('API Key'))
      
      // 导航到设置页面
      await page.goto('/settings')
      await page.waitForTimeout(2000)
      await page.screenshot({ path: 'test-results/login-03-settings.png', fullPage: true })
      
      // 检查设置页面的 Tab
      const settingsText = await page.locator('body').innerText()
      console.log('设置页面包含 API Key 管理:', settingsText.includes('API Key 管理'))
      console.log('设置页面包含 Agent 模型配置:', settingsText.includes('Agent 模型配置'))
      
      // 点击 API Key 管理 Tab
      const apiKeyTab = page.locator('button:has-text("API Key 管理"), [class*="tab"]:has-text("API Key")').first()
      if (await apiKeyTab.count() > 0) {
        await apiKeyTab.click()
        await page.waitForTimeout(1000)
        await page.screenshot({ path: 'test-results/login-04-apikey-tab.png', fullPage: true })
        
        const apikeyText = await page.locator('body').innerText()
        console.log('API Key 页面包含硅基流动:', apikeyText.includes('硅基流动'))
        console.log('API Key 页面包含必填:', apikeyText.includes('必填'))
      }
      
      // 测试 Chat API
      const codeResult = await page.evaluate(async (token) => {
        try {
          const response = await fetch('/api/v1/chat', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
              prompt: '你好，请用一句话介绍 Python',
              model: 'Qwen/Qwen2.5-7B-Instruct',
              stream: false
            })
          })
          
          const data = await response.json()
          return {
            status: response.status,
            hasResponse: !!data.response,
            response: data.response?.substring(0, 100)
          }
        } catch (e) {
          return { error: e.message }
        }
      }, loginResult.token)
      
      console.log('Code API 测试结果:', JSON.stringify(codeResult))
    }
  })
})
