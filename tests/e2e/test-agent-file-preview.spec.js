// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 测试 Agent 功能：文件预览、diff 对比、消息推送
 */
// 真实模型生成长流程，仅在提供 TEST_SILICONFLOW_API_KEY 时启用
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

test.describe('Agent 功能测试', () => {
  test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）')

  test.setTimeout(300000) // 5 minutes for generation
  
  test('1. 使用 Agent 生成项目并检查文件预览和 diff', async ({ page }) => {
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
    
    page.on('console', msg => {
      if (msg.type() === 'error' || msg.type() === 'warn') {
        console.log(`浏览器 ${msg.type()}: ${msg.text()}`)
      }
    })
    
    // 访问首页
    await page.goto('/')
    await page.waitForTimeout(2000)
    
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
            email: 'mr_yang@example.com',
            password: '12345678'
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
    
    // 保存用户信息和 API Key 到 localStorage
    await page.evaluate((loginData) => {
      localStorage.setItem('access_token', loginData.token)
      localStorage.setItem('username', loginData.username || 'admin')
      localStorage.setItem('email', 'mr_yang@example.com')
      localStorage.setItem('permission_level', loginData.permission_level || 'superadmin')
      
    }, loginResult)
    
    await syncRealApiKeys(page)
    // 导航到 Agent 页面
    await page.goto('/agent')
    await page.waitForTimeout(3000)
    await page.screenshot({ path: 'test-results/agent-01-initial.png', fullPage: true })
    
    // 查找输入框并输入项目描述
    const textarea = page.locator('textarea.prompt-textarea')
    await expect(textarea).toBeVisible({ timeout: 10000 })
    
    const testPrompt = '创建一个简单的 Python 计算器，支持加减乘除运算，包含 main.py 和 requirements.txt'
    await textarea.fill(testPrompt)
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-results/agent-02-prompt.png', fullPage: true })
    
    // 点击生成按钮
    const generateButton = page.locator('button[aria-label="发送需求"]').first()
    await expect(generateButton).toBeVisible({ timeout: 5000 })
    await generateButton.click()
    console.log('已点击生成按钮，开始生成项目...')
    
    // 等待生成开始
    await page.waitForTimeout(5000)
    await page.screenshot({ path: 'test-results/agent-03-generating.png', fullPage: true })
    
    // 等待生成完成（最多 180 秒）
    let attempts = 0
    const maxAttempts = 180
    let isGenerating = true
    
    while (attempts < maxAttempts && isGenerating) {
      await page.waitForTimeout(1000)
      attempts++
      
      // 检查是否还在生成中
      isGenerating = await page.evaluate(() => {
        // 检查是否有停止按钮
        const buttons = Array.from(document.querySelectorAll('button'))
        const hasStopButton = buttons.some(btn => btn.textContent?.includes('停止'))
        
        // 检查是否有生成中按钮
        const hasGeneratingButton = buttons.some(btn => btn.textContent?.includes('生成中'))
        
        return hasStopButton || hasGeneratingButton
      })
      
      if (attempts % 30 === 0) {
        console.log(`等待生成中... ${attempts}/${maxAttempts}, isGenerating: ${isGenerating}`)
        await page.screenshot({ path: `test-results/agent-04-progress-${attempts}.png`, fullPage: true })
      }
    }
    
    console.log('生成过程完成，等待最终结果...')
    await page.waitForTimeout(5000)
    await page.screenshot({ path: 'test-results/agent-05-complete.png', fullPage: true })
    
    // 检查网络请求
    const agentRequests = requests.filter(r => r.url.includes('/agent/orchestrate'))
    console.log('Agent orchestrate 请求数量:', agentRequests.length)
    console.log('Agent 请求详情:', JSON.stringify(agentRequests, null, 2))
    
    // 等待文件列表出现真实产物后再统计
    const firstFile = page.locator('.file-item').first()
    await expect(firstFile).toBeVisible({ timeout: 240000 })
    const generatedFiles = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.file-item .file-name'))
        .map(item => item.textContent?.trim())
        .filter(Boolean)
    )
    console.log('生成的文件列表:', generatedFiles)
    
    // 点击第一个文件查看预览
    await firstFile.click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-results/agent-06-file-preview.png', fullPage: true })

    // 检查是否有 diff 按钮
    const diffButton = page.getByRole('button', { name: /变更|Diff/ }).first()
    const hasDiffButton = await diffButton.count() > 0
    console.log('是否有 diff 按钮:', hasDiffButton)

    if (hasDiffButton) {
      await diffButton.click()
      await page.waitForTimeout(1000)
      await page.screenshot({ path: 'test-results/agent-07-diff-modal.png', fullPage: true })
      console.log('已打开 diff 弹窗')
    }
    
    // 检查日志区域
    const logMessages = await page.evaluate(() => {
      const logItems = document.querySelectorAll('.log-item, .log-entry')
      return Array.from(logItems).map(item => item.textContent?.trim()).filter(Boolean)
    })
    console.log('日志消息数量:', logMessages.length)
    if (logMessages.length > 0) {
      console.log('前 5 条日志:', logMessages.slice(0, 5))
    }
    
    // 最终截图
    await page.screenshot({ path: 'test-results/agent-08-final.png', fullPage: true })
    
    // 验证结果
    console.log('\n=== 测试结果总结 ===')
    console.log('1. Agent orchestrate 请求数量:', agentRequests.length)
    console.log('2. 生成的文件数量:', generatedFiles.length)
    console.log('3. 日志消息数量:', logMessages.length)
    
    // 断言
    expect(agentRequests.length).toBeGreaterThan(0)
    expect(generatedFiles.length).toBeGreaterThan(0)
  })
})
