// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 测试 Agent 功能：捕获文件生成和 diff 对比过程
 */
test.describe('Agent 文件生成和 Diff 测试', () => {
  
  test('1. 捕获文件生成和 diff 过程', async ({ page }) => {
    // 监听所有网络请求
    const requests = []
    page.on('request', request => {
      if (request.url().includes('/api/v1/')) {
        requests.push({
          url: request.url(),
          method: request.method(),
          timestamp: Date.now()
        })
      }
    })
    
    // 监听 SSE 消息
    const sseMessages = []
    await page.evaluate(() => {
      window.__sseMessages = []
      
      const originalFetch = window.fetch
      window.fetch = function(...args) {
        const url = args[0]
        if (typeof url === 'string' && url.includes('/api/v1/agent/orchestrate/stream')) {
          return originalFetch.apply(this, args).then(response => {
            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            
            const processStream = async () => {
              try {
                while (true) {
                  const { done, value } = await reader.read()
                  if (done) break
                  
                  const text = decoder.decode(value)
                  const lines = text.split('\n').filter(line => line.trim())
                  
                  for (const line of lines) {
                    if (line.startsWith('data: ')) {
                      try {
                        const data = JSON.parse(line.slice(6))
                        window.__sseMessages.push({
                          type: data.type,
                          timestamp: Date.now(),
                          data: data
                        })
                      } catch (e) {
                        // ignore
                      }
                    }
                  }
                }
              } catch (e) {
                console.error('流读取错误:', e)
              }
            }
            
            processStream()
            
            return new Response(response.body, {
              status: response.status,
              statusText: response.statusText,
              headers: response.headers
            })
          })
        }
        return originalFetch.apply(this, args)
      }
    })
    
    // 访问首页并登录
    await page.goto('/')
    await page.waitForTimeout(2000)
    
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
    
    console.log('登录结果:', JSON.stringify(loginResult))
    
    if (!loginResult.success || !loginResult.token) {
      console.log('登录失败，跳过测试')
      expect(loginResult.success).toBe(true)
      return
    }
    
    // 保存用户信息和 API Key
    await page.evaluate((loginData) => {
      localStorage.setItem('access_token', loginData.token)
      localStorage.setItem('username', loginData.username || 'admin')
      localStorage.setItem('email', 'admin@example.com')
      localStorage.setItem('permission_level', loginData.permission_level || 'superadmin')
      
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
    
    // 导航到 Agent 页面
    await page.goto('/agent')
    await page.waitForTimeout(3000)
    await page.screenshot({ path: 'test-results/agent-diff-01-initial.png', fullPage: true })
    
    // 输入项目描述
    const textarea = page.locator('textarea').first()
    await expect(textarea).toBeVisible({ timeout: 10000 })
    
    const testPrompt = '创建一个简单的 Python 计算器，包含 main.py 和 calculator.py'
    await textarea.fill(testPrompt)
    await page.waitForTimeout(500)
    
    // 点击生成按钮
    const generateButton = page.locator('button:has-text("开始生成")').first()
    await expect(generateButton).toBeVisible({ timeout: 5000 })
    await generateButton.click()
    console.log('已点击生成按钮')
    
    // 等待生成开始并定期截图
    await page.waitForTimeout(2000)
    await page.screenshot({ path: 'test-results/agent-diff-02-generating-2s.png', fullPage: true })
    
    // 等待 10 秒后截图
    await page.waitForTimeout(8000)
    await page.screenshot({ path: 'test-results/agent-diff-03-generating-10s.png', fullPage: true })
    
    // 检查是否有文件生成
    const fileCheck1 = await page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item, .file-list-item, [class*="file"]')
      const fileList = Array.from(fileItems).map(item => item.textContent?.trim()).filter(Boolean)
      
      // 检查是否有 diff 按钮
      const diffButtons = document.querySelectorAll('button:has-text("变更"), button:has-text("Diff")')
      
      return {
        fileCount: fileList.length,
        files: fileList.slice(0, 10),
        hasDiffButton: diffButtons.length > 0,
        sseMessageCount: window.__sseMessages?.length || 0,
        sseMessageTypes: (window.__sseMessages || []).reduce((acc, msg) => {
          acc[msg.type] = (acc[msg.type] || 0) + 1
          return acc
        }, {})
      }
    })
    console.log('10秒后检查:', JSON.stringify(fileCheck1, null, 2))
    
    // 等待 30 秒后截图
    await page.waitForTimeout(20000)
    await page.screenshot({ path: 'test-results/agent-diff-04-generating-30s.png', fullPage: true })
    
    // 再次检查文件
    const fileCheck2 = await page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item, .file-list-item, [class*="file"]')
      const fileList = Array.from(fileItems).map(item => item.textContent?.trim()).filter(Boolean)
      
      const diffButtons = document.querySelectorAll('button:has-text("变更"), button:has-text("Diff")')
      
      // 检查日志
      const logItems = document.querySelectorAll('.log-item, .log-entry, [class*="log"]')
      const logs = Array.from(logItems).map(item => item.textContent?.trim()).filter(Boolean)
      
      return {
        fileCount: fileList.length,
        files: fileList.slice(0, 10),
        hasDiffButton: diffButtons.length > 0,
        logCount: logs.length,
        logs: logs.slice(0, 10),
        sseMessageCount: window.__sseMessages?.length || 0,
        sseMessageTypes: (window.__sseMessages || []).reduce((acc, msg) => {
          acc[msg.type] = (acc[msg.type] || 0) + 1
          return acc
        }, {})
      }
    })
    console.log('30秒后检查:', JSON.stringify(fileCheck2, null, 2))
    
    // 等待 60 秒后截图
    await page.waitForTimeout(30000)
    await page.screenshot({ path: 'test-results/agent-diff-05-generating-60s.png', fullPage: true })
    
    // 检查是否有文件和 diff
    const fileCheck3 = await page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item, .file-list-item, [class*="file"]')
      const fileList = Array.from(fileItems).map(item => item.textContent?.trim()).filter(Boolean)
      
      const diffButtons = document.querySelectorAll('button:has-text("变更"), button:has-text("Diff")')
      
      // 检查是否有 diff 弹窗
      const diffModal = document.querySelector('.diff-view, .modal-content')
      
      return {
        fileCount: fileList.length,
        files: fileList.slice(0, 10),
        hasDiffButton: diffButtons.length > 0,
        hasDiffModal: !!diffModal,
        sseMessageCount: window.__sseMessages?.length || 0,
        sseMessageTypes: (window.__sseMessages || []).reduce((acc, msg) => {
          acc[msg.type] = (acc[msg.type] || 0) + 1
          return acc
        }, {})
      }
    })
    console.log('60秒后检查:', JSON.stringify(fileCheck3, null, 2))
    
    // 如果有 diff 按钮，点击它
    if (fileCheck3.hasDiffButton) {
      const diffButton = page.locator('button:has-text("变更"), button:has-text("Diff")').first()
      await diffButton.click()
      await page.waitForTimeout(1000)
      await page.screenshot({ path: 'test-results/agent-diff-06-diff-modal.png', fullPage: true })
      console.log('已打开 diff 弹窗')
    }
    
    // 如果有文件，点击第一个文件
    if (fileCheck3.fileCount > 0) {
      const firstFile = page.locator('.file-item, .file-list-item').first()
      await firstFile.click()
      await page.waitForTimeout(1000)
      await page.screenshot({ path: 'test-results/agent-diff-07-file-preview.png', fullPage: true })
      console.log('已打开文件预览')
    }
    
    // 最终截图
    await page.screenshot({ path: 'test-results/agent-diff-08-final.png', fullPage: true })
    
    // 获取 SSE 消息统计
    const sseStats = await page.evaluate(() => {
      const messages = window.__sseMessages || []
      return {
        total: messages.length,
        types: messages.reduce((acc, msg) => {
          acc[msg.type] = (acc[msg.type] || 0) + 1
          return acc
        }, {}),
        fileMessages: messages.filter(m => m.type === 'file').length,
        diffMessages: messages.filter(m => m.type === 'file_diff').length
      }
    })
    console.log('SSE 消息统计:', JSON.stringify(sseStats, null, 2))
    
    // 验证结果
    console.log('\n=== 测试结果总结 ===')
    console.log('1. SSE 消息总数:', sseStats.total)
    console.log('2. 文件消息数量:', sseStats.fileMessages)
    console.log('3. Diff 消息数量:', sseStats.diffMessages)
    console.log('4. 消息类型分布:', JSON.stringify(sseStats.types))
    
    // 断言
    expect(sseStats.total).toBeGreaterThan(0)
  })
})
