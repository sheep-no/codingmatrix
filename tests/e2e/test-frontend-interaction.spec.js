// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 模拟用户在前端完整交互流程
 */
test.describe('前端 Code 接口完整交互测试', () => {
  
  test('1. 访问首页并检查 API Key 状态', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)
    
    // 截图
    await page.screenshot({ path: 'test-results/01-homepage.png', fullPage: true })
    
    // 检查是否有 API Key 相关提示
    const pageContent = await page.content()
    const hasApiKeyHint = pageContent.includes('API Key') || pageContent.includes('apikey')
    console.log('页面包含 API Key 相关内容:', hasApiKeyHint)
    
    // 检查页面标题
    console.log('页面标题:', await page.title())
  })

  test('2. 导航到设置页面检查 API Key 管理', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForTimeout(2000)
    
    await page.screenshot({ path: 'test-results/02-settings.png', fullPage: true })
    
    // 检查是否有 API Key 管理 Tab
    const apiKeyTab = page.locator('text=API Key 管理')
    const hasApiKeyTab = await apiKeyTab.count() > 0
    console.log('找到 API Key 管理 Tab:', hasApiKeyTab)
    
    // 点击 API Key 管理 Tab
    if (hasApiKeyTab) {
      await apiKeyTab.click()
      await page.waitForTimeout(1000)
      await page.screenshot({ path: 'test-results/02-apikey-tab.png', fullPage: true })
      
      // 检查是否有硅基流动必填提示
      const pageText = await page.locator('body').innerText()
      const hasSiliconflowHint = pageText.includes('硅基流动') || pageText.includes('SiliconFlow')
      console.log('包含硅基流动相关内容:', hasSiliconflowHint)
      
      const hasRequiredHint = pageText.includes('必填')
      console.log('包含必填提示:', hasRequiredHint)
    }
  })

  test('3. 检查 Agent 页面设置弹窗', async ({ page }) => {
    await page.goto('/agent')
    await page.waitForTimeout(3000)
    
    await page.screenshot({ path: 'test-results/03-agent-page.png', fullPage: true })
    
    // 查找设置按钮（通常是齿轮图标或"设置"文字）
    const settingsButton = page.locator('button:has-text("设置"), [class*="settings"], [aria-label*="设置"]').first()
    const hasSettingsButton = await settingsButton.count() > 0
    console.log('找到设置按钮:', hasSettingsButton)
    
    if (hasSettingsButton) {
      await settingsButton.click()
      await page.waitForTimeout(1000)
      await page.screenshot({ path: 'test-results/03-settings-modal.png', fullPage: true })
      
      // 检查弹窗内容
      const modalContent = await page.locator('body').innerText()
      const hasApiKeyConfig = modalContent.includes('API Key') || modalContent.includes('前往 API Key 管理')
      console.log('设置弹窗包含 API Key 配置:', hasApiKeyConfig)
    }
  })

  test('4. 模拟在聊天界面输入并发送', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(3000)
    
    // 查找聊天输入框
    const chatInput = page.locator('textarea, [contenteditable="true"], input[type="text"]').first()
    const hasChatInput = await chatInput.count() > 0
    console.log('找到聊天输入框:', hasChatInput)
    
    if (hasChatInput) {
      // 输入测试内容
      await chatInput.fill('你好，请介绍一下 Python')
      await page.waitForTimeout(500)
      await page.screenshot({ path: 'test-results/04-input-filled.png', fullPage: true })
      
      // 查找发送按钮
      const sendButton = page.locator('button:has-text("发送"), button[type="submit"], [class*="send"]').first()
      const hasSendButton = await sendButton.count() > 0
      console.log('找到发送按钮:', hasSendButton)
      
      if (hasSendButton) {
        // 点击发送
        await sendButton.click()
        console.log('已点击发送按钮')
        
        // 等待响应
        await page.waitForTimeout(5000)
        await page.screenshot({ path: 'test-results/04-after-send.png', fullPage: true })
        
        // 检查是否有响应内容
        const responseContent = await page.locator('body').innerText()
        console.log('页面内容长度:', responseContent.length)
      }
    }
  })

  test('5. 直接通过浏览器 fetch 调用 code 接口', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(2000)
    
    // 在浏览器中执行 fetch 请求
    const result = await page.evaluate(async () => {
      try {
        // 先获取 token（从 localStorage 或 cookie）
        const token = localStorage.getItem('access_token') || ''
        
        const response = await fetch('/api/v1/code', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            prompt: '你好',
            model: 'Qwen/Qwen2.5-7B-Instruct',
            stream: false
          })
        })
        
        const data = await response.json()
        return {
          status: response.status,
          data: data,
          hasToken: !!token
        }
      } catch (error) {
        return {
          error: error.message,
          hasToken: false
        }
      }
    })
    
    console.log('浏览器 fetch 结果:', JSON.stringify(result, null, 2))
  })

  test('6. 检查前端 API Key Store 状态', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(2000)
    
    // 检查 Pinia store 中的 API Key 状态
    const storeState = await page.evaluate(() => {
      // 尝试访问 Pinia store
      const app = document.querySelector('#app')?.__vue_app__
      if (!app) return { error: 'Vue app not found' }
      
      // 尝试获取 apikey store
      try {
        const pinia = app.config.globalProperties.$pinia
        if (!pinia) return { error: 'Pinia not found' }
        
        // 从 localStorage 获取
        const storedKeys = localStorage.getItem('codingmatrix_apikeys')
        return {
          storedKeys: storedKeys ? JSON.parse(storedKeys) : [],
          hasStoredKeys: !!storedKeys
        }
      } catch (e) {
        return { error: e.message }
      }
    })
    
    console.log('API Key Store 状态:', JSON.stringify(storeState, null, 2))
  })
})
