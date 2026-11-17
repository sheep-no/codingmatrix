// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 测试 Agent 功能：捕获文件生成和 diff 对比过程
 */
// 真实模型生成长流程，仅在提供 TEST_SILICONFLOW_API_KEY 时启用
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

test.describe('Agent 文件生成和 Diff 测试', () => {
  test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）')

  
  test('1. 捕获文件生成和 diff 过程', async ({ page }) => {
    test.setTimeout(300000)

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
    
    // 记录 SSE 是否发出；响应体在流结束前无法读取，产物以 DOM 文件列表为准
    const sseRequests = []
    page.on('request', request => {
      if (request.url().includes('/api/v1/agent/orchestrate/stream')) {
        sseRequests.push(request.url())
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
    
    // 保存用户信息和 API Key
    await page.evaluate((loginData) => {
      localStorage.setItem('access_token', loginData.token)
      localStorage.setItem('username', loginData.username || 'admin')
      localStorage.setItem('email', 'mr_yang@example.com')
      localStorage.setItem('permission_level', loginData.permission_level || 'superadmin')
      
    }, loginResult)
    
    await syncRealApiKeys(page)
    // Key 必须在进入 Agent 页前写入，Pinia store 初始化时才读取 localStorage
    await page.goto('/agent')
    await page.waitForTimeout(3000)
    await page.screenshot({ path: 'test-results/agent-diff-01-initial.png', fullPage: true })
    
    // 输入项目描述
    const textarea = page.locator('textarea.prompt-textarea')
    await expect(textarea).toBeVisible({ timeout: 10000 })
    
    const testPrompt = '创建一个简单的 Python 计算器，包含 main.py 和 calculator.py'
    await textarea.fill(testPrompt)
    await page.waitForTimeout(500)
    
    // 点击生成按钮
    const generateButton = page.locator('button[aria-label="发送需求"]').first()
    await expect(generateButton).toBeVisible({ timeout: 5000 })
    await generateButton.click()
    console.log('已点击生成按钮')
    
    // 等待生成开始，并等待左侧文件列表出现真实产物
    await page.waitForTimeout(2000)
    await page.screenshot({ path: 'test-results/agent-diff-02-generating-2s.png', fullPage: true })

    const fileItem = page.locator('.file-item').first()
    await expect(fileItem).toBeVisible({ timeout: 240000 })
    await page.screenshot({ path: 'test-results/agent-diff-03-file-generated.png', fullPage: true })

    const files = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.file-item .file-name'))
        .map(item => item.textContent?.trim())
        .filter(Boolean)
    )
    console.log('生成的文件:', JSON.stringify(files))

    // 点击文件验证预览
    await fileItem.click()
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-results/agent-diff-04-file-preview.png', fullPage: true })

    // 若存在 diff 入口，打开并验证弹窗
    const diffButton = page.getByRole('button', { name: /变更|Diff/ }).first()
    if (await diffButton.count() > 0) {
      await diffButton.click()
      await page.waitForTimeout(1000)
      await page.screenshot({ path: 'test-results/agent-diff-05-diff-modal.png', fullPage: true })
    }

    await page.screenshot({ path: 'test-results/agent-diff-06-final.png', fullPage: true })

    expect(sseRequests.length).toBeGreaterThan(0)
    expect(files.length).toBeGreaterThan(0)
  })
})
