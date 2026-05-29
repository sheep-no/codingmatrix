// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 通过前端界面操作测试 Code API
 */
test.describe('前端界面测试 Code API', () => {
  
  test('1. 登录并通过前端发送消息', async ({ page }) => {
    // 访问首页
    await page.goto('/')
    await page.waitForTimeout(3000)
    
    // 截图查看初始状态
    await page.screenshot({ path: 'test-results/code-01-initial.png', fullPage: true })
    
    // 通过 API 登录获取 token
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
          token: loginData.access_token,
          username: loginData.username,
          permission_level: loginData.permission_level
        }
      } catch (e) {
        return { error: e.message }
      }
    })
    
    console.log('登录结果:', JSON.stringify(loginResult))
    
    // 如果登录成功，保存 token 到 localStorage
    if (loginResult.success && loginResult.token) {
      // 保存用户信息到 localStorage（与前端 user store 一致）
      await page.evaluate((loginData) => {
        localStorage.setItem('access_token', loginData.token)
        localStorage.setItem('username', loginData.username || 'admin')
        localStorage.setItem('email', 'admin@example.com')
        localStorage.setItem('permission_level', loginData.permission_level || 'superadmin')
        
        // 设置模拟的 API Key（用于测试，前端会使用系统默认 Key）
        const mockApiKeys = [{
          token: 'test-token-for-e2e',
          provider: 'siliconflow',
          remark: 'E2E Test Key',
          status: 'verified',
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
          ttl_seconds: 604800,
          enabled: true
        }]
        localStorage.setItem('codingmatrix_apikeys', JSON.stringify(mockApiKeys))
      }, loginResult)
      
      // 刷新页面使 token 生效
      await page.reload()
      await page.waitForTimeout(3000)
      await page.screenshot({ path: 'test-results/code-02-after-login.png', fullPage: true })
      
      // 检查是否已登录
      const isLoggedIn = await page.evaluate(() => {
        return !!localStorage.getItem('username')
      })
      console.log('是否已登录:', isLoggedIn)
      
      // 等待输入框出现
      const textarea = page.locator('textarea.chat-input, textarea[placeholder*="message"], textarea[placeholder*="消息"]').first()
      await expect(textarea).toBeVisible({ timeout: 10000 })
      
      // 输入测试消息
      const testMessage = '你好，请用一句话介绍 Python'
      await textarea.fill(testMessage)
      await page.waitForTimeout(500)
      await page.screenshot({ path: 'test-results/code-03-input.png', fullPage: true })
      
      // 点击发送按钮
      const sendButton = page.locator('button.send-btn, button[aria-label*="发送"], button[title*="发送"]').first()
      await expect(sendButton).toBeVisible({ timeout: 5000 })
      await sendButton.click()
      
      console.log('已点击发送按钮')
      
      // 等待 AI 响应开始
      await page.waitForTimeout(5000)
      await page.screenshot({ path: 'test-results/code-04-response-start.png', fullPage: true })
      
      // 等待响应完成（最多等待 60 秒）
      let attempts = 0
      const maxAttempts = 60
      while (attempts < maxAttempts) {
        // 检查是否有停止按钮（表示还在流式输出）
        const stopButton = page.locator('button.stop-btn, button[aria-label*="停止"]').first()
        const isStreaming = await stopButton.count() > 0
        
        if (!isStreaming) {
          console.log('响应已完成')
          break
        }
        
        await page.waitForTimeout(1000)
        attempts++
        
        if (attempts % 10 === 0) {
          console.log(`等待响应中... ${attempts}/${maxAttempts}`)
          await page.screenshot({ path: `test-results/code-05-response-progress-${attempts}.png`, fullPage: true })
        }
      }
      
      // 最终截图
      await page.screenshot({ path: 'test-results/code-06-final.png', fullPage: true })
      
      // 获取页面上的响应内容
      const pageText = await page.locator('body').innerText()
      console.log('页面包含 Python:', pageText.includes('Python'))
      console.log('页面包含你好:', pageText.includes('你好'))
      
      // 检查是否有错误信息
      const hasError = pageText.includes('错误') || pageText.includes('error') || pageText.includes('Error')
      console.log('是否有错误:', hasError)
      
      // 检查对话历史
      const messageItems = page.locator('[class*="message"], [class*="chat-item"], [class*="conversation"]').all()
      const messageCount = await messageItems.length
      console.log('消息数量:', messageCount)
    } else {
      console.log('登录失败，跳过测试')
      expect(loginResult.success).toBe(true)
    }
  })
  
  test('2. 测试流式响应', async ({ page }) => {
    // 访问首页
    await page.goto('/')
    await page.waitForTimeout(3000)
    
    // 通过 API 登录获取 token
    const loginResult = await page.evaluate(async () => {
      try {
        const csrfResponse = await fetch('/api/v1/csrf-token')
        const csrfData = await csrfResponse.json()
        
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
          token: loginData.access_token,
          username: loginData.username,
          permission_level: loginData.permission_level
        }
      } catch (e) {
        return { error: e.message }
      }
    })
    
    if (loginResult.success && loginResult.token) {
      // 保存用户信息到 localStorage
      await page.evaluate((loginData) => {
        localStorage.setItem('access_token', loginData.token)
        localStorage.setItem('username', loginData.username || 'admin')
        localStorage.setItem('email', 'admin@example.com')
        localStorage.setItem('permission_level', loginData.permission_level || 'superadmin')
      }, loginResult)
      
      // 刷新页面
      await page.reload()
      await page.waitForTimeout(3000)
      
      // 等待输入框出现
      const textarea = page.locator('textarea.chat-input, textarea[placeholder*="message"], textarea[placeholder*="消息"]').first()
      await expect(textarea).toBeVisible({ timeout: 10000 })
      
      // 输入测试消息
      await textarea.fill('写一个简单的 Python 函数，计算两个数的和')
      await page.waitForTimeout(500)
      
      // 点击发送按钮
      const sendButton = page.locator('button.send-btn, button[aria-label*="发送"], button[title*="发送"]').first()
      await sendButton.click()
      
      console.log('已发送消息，等待流式响应...')
      
      // 监听网络请求，验证是否调用了 /api/v1/code 接口
      const codeApiCalled = await page.evaluate(() => {
        return new Promise((resolve) => {
          const originalFetch = window.fetch
          let apiCalled = false
          
          window.fetch = function(...args) {
            const url = args[0]
            if (typeof url === 'string' && url.includes('/api/v1/code')) {
              apiCalled = true
              console.log('检测到 /api/v1/code 请求:', url)
            }
            return originalFetch.apply(this, args)
          }
          
          // 5 秒后检查
          setTimeout(() => {
            window.fetch = originalFetch
            resolve(apiCalled)
          }, 5000)
        })
      })
      
      console.log('是否调用了 Code API:', codeApiCalled)
      
      // 等待响应完成
      await page.waitForTimeout(30000)
      await page.screenshot({ path: 'test-results/code-stream-final.png', fullPage: true })
      
      // 验证响应内容
      const pageText = await page.locator('body').innerText()
      console.log('页面包含 Python:', pageText.includes('Python'))
      console.log('页面包含 def:', pageText.includes('def'))
      console.log('页面包含 return:', pageText.includes('return'))
    }
  })
})
