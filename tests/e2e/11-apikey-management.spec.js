// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * API Key 管理 E2E 测试
 * 测试多供应商 API Key 的提交、管理、测试和 Agent 配置
 */

test.describe('API Key Management', () => {
  test.beforeEach(async ({ page }) => {
    // 访问设置页面
    await page.goto('/settings')
  })

  test('1. 设置页面加载正常', async ({ page }) => {
    expect(page.url()).toContain('/settings')
    
    // 检查 Tab 存在
    await expect(page.locator('text=API Key 管理')).toBeVisible()
    await expect(page.locator('text=Agent 模型配置')).toBeVisible()
  })

  test('2. 获取 RSA 公钥成功', async ({ page }) => {
    // 等待公钥加载
    await page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/agent/apikey/public-key') &&
        response.status() === 200
    )
    
    // 检查公钥显示
    const publicKeyText = await page.textContent('.public-key-info')
    expect(publicKeyText).toContain('RSA-2048')
  })

  test('3. 提交硅基流动 API Key', async ({ page }) => {
    const testKey = `sk-test-${Date.now()}`
    
    // 填写表单
    await page.selectOption('[name="provider"]', 'siliconflow')
    await page.fill('[name="apiKey"]', testKey)
    await page.selectOption('[name="ttl"]', '24h')
    await page.fill('[name="remark"]', 'E2E 测试 Key')
    
    // 点击保存
    await page.click('button:has-text("保存")')
    
    // 等待提交成功
    await page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/agent/apikey') &&
        response.status() === 200
    )
    
    // 检查 Key 卡片显示
    await expect(page.locator('.api-key-card')).toContainText('硅基流动')
    await expect(page.locator('.api-key-card')).toContainText('E2E 测试 Key')
  })

  test('4. 测试 Key 连接', async ({ page }) => {
    // 找到测试连接按钮
    const testButton = page.locator('button:has-text("测试连接")').first()
    await testButton.click()
    
    // 等待测试结果
    await page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/agent/apikey/test') &&
        response.status() === 200
    )
    
    // 检查状态更新（可能成功或失败，但应该有状态显示）
    const statusElement = page.locator('.key-status').first()
    await expect(statusElement).toBeVisible()
  })

  test('5. 启用/禁用 Key', async ({ page }) => {
    const toggleButton = page.locator('button:has-text("禁用")').first()
    
    // 如果按钮存在，点击切换
    if (await toggleButton.count() > 0) {
      await toggleButton.click()
      
      // 等待状态更新
      await page.waitForTimeout(1000)
      
      // 检查按钮文本变化
      const newButtonText = await toggleButton.textContent()
      expect(newButtonText).toBe('启用')
    }
  })

  test('6. 清除 Key', async ({ page }) => {
    const clearButton = page.locator('button:has-text("清除")').first()
    
    if (await clearButton.count() > 0) {
      // 点击清除
      await clearButton.click()
      
      // 确认对话框
      await page.click('button:has-text("确认")')
      
      // 等待删除成功
      await page.waitForResponse(
        (response) =>
          response.url().includes('/api/v1/agent/apikey/') &&
          response.method() === 'DELETE' &&
          response.status() === 200
      )
      
      // 检查卡片消失
      await expect(page.locator('.api-key-card').first()).not.toBeVisible()
    }
  })

  test('7. Agent 环节配置显示', async ({ page }) => {
    // 切换到 Agent 配置 Tab
    await page.click('button:has-text("Agent 模型配置")')
    
    // 等待 Tab 切换
    await page.waitForTimeout(500)
    
    // 检查 9 个环节显示
    const expectedLayers = [
      '决策层',
      '执行层前端',
      '执行层后端',
      '架构设计',
      '攻坚层',
      '审查层',
      '修复层',
      '交叉验证',
      '反思层'
    ]
    
    for (const layer of expectedLayers) {
      await expect(page.locator(`text=${layer}`)).toBeVisible()
    }
  })

  test('8. 配置 Agent 环节模型', async ({ page }) => {
    // 切换到 Agent 配置 Tab
    await page.click('button:has-text("Agent 模型配置")')
    await page.waitForTimeout(500)
    
    // 选择第一个环节的下拉框
    const selectElement = page.locator('select').first()
    await selectElement.selectOption('system_default')
    
    // 等待自动保存
    await page.waitForTimeout(1000)
    
    // 检查保存提示
    const saveMessage = page.locator('.save-status')
    if (await saveMessage.count() > 0) {
      expect(await saveMessage.textContent()).toContain('保存')
    }
  })

  test('9. 重置 Agent 配置', async ({ page }) => {
    // 切换到 Agent 配置 Tab
    await page.click('button:has-text("Agent 模型配置")')
    await page.waitForTimeout(500)
    
    // 点击重置按钮
    const resetButton = page.locator('button:has-text("重置为默认")')
    if (await resetButton.count() > 0) {
      await resetButton.click()
      
      // 等待重置完成
      await page.waitForResponse(
        (response) =>
          response.url().includes('/api/v1/agent/model-overrides') &&
          response.status() === 200
      )
      
      // 检查所有下拉框恢复为系统默认
      const selects = page.locator('select')
      const count = await selects.count()
      
      for (let i = 0; i < count; i++) {
        const select = selects.nth(i)
        const value = await select.inputValue()
        expect(value).toBe('system_default')
      }
    }
  })

  test('10. 供应商选择完整性', async ({ page }) => {
    const providerSelect = page.locator('[name="provider"]').first()
    const options = await providerSelect.locator('option').all()
    
    const providerNames = []
    for (const option of options) {
      const value = await option.getAttribute('value')
      if (value) {
        providerNames.push(value)
      }
    }
    
    // 检查所有支持的供应商
    expect(providerNames).toContain('siliconflow')
    expect(providerNames).toContain('openai')
    expect(providerNames).toContain('anthropic')
    expect(providerNames).toContain('bailian')
    expect(providerNames).toContain('zhipu')
    expect(providerNames).toContain('deepseek')
  })

  test('11. TTL 选项完整性', async ({ page }) => {
    const ttlSelect = page.locator('[name="ttl"]').first()
    const options = await ttlSelect.locator('option').all()
    
    const ttlValues = []
    for (const option of options) {
      const value = await option.getAttribute('value')
      if (value) {
        ttlValues.push(value)
      }
    }
    
    // 检查所有 TTL 选项
    expect(ttlValues).toContain('1h')
    expect(ttlValues).toContain('24h')
    expect(ttlValues).toContain('7d')
    expect(ttlValues).toContain('30d')
  })

  test('12. 本地存储安全', async ({ page }) => {
    // 等待页面加载完成
    await page.waitForTimeout(2000)
    
    // 检查 localStorage 内容
    const localStorageContent = await page.evaluate(() => {
      const keys = localStorage.getItem('codingmatrix_apikeys')
      return keys ? JSON.parse(keys) : null
    })
    
    if (localStorageContent) {
      // 确认没有明文 Key
      const contentStr = JSON.stringify(localStorageContent)
      expect(contentStr).not.toContain('sk-')
      expect(contentStr).not.toContain('key')
    }
  })
})
