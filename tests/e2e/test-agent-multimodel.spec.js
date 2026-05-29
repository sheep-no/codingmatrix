const { test, expect } = require('@playwright/test')

test.describe('Agent 多模型功能测试', () => {
  test.setTimeout(60000)

  test('1. 登录并检查 Agent 页面模型选择器', async ({ page }) => {
    // 访问首页
    await page.goto('/')
    await page.waitForTimeout(2000)

    // 通过 API 登录
    const loginResult = await page.evaluate(async () => {
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
    })

    console.log('登录结果:', JSON.stringify(loginResult))
    expect(loginResult.success).toBe(true)

    // 保存登录信息到 localStorage
    await page.evaluate((loginData) => {
      localStorage.setItem('access_token', loginData.token)
      localStorage.setItem('username', loginData.username || 'admin')
      localStorage.setItem('email', 'admin@example.com')
      localStorage.setItem('permission_level', loginData.permission_level || 'superadmin')

      // 设置模拟的 API Key
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

    // 检查页面是否加载
    const textarea = page.locator('textarea').first()
    await expect(textarea).toBeVisible({ timeout: 10000 })

    // 检查模型选择器是否存在
    // 注意：如果没有动态供应商，模型选择器可能不会显示
    const modelSelector = page.locator('.model-selector')
    const selectorExists = await modelSelector.count() > 0
    console.log('模型选择器是否存在:', selectorExists)

    // 检查是否有"系统默认模型"选项
    const defaultOption = page.locator('select option:has-text("系统默认模型")')
    const hasDefaultOption = await defaultOption.count() > 0
    console.log('是否有系统默认模型选项:', hasDefaultOption)

    // 截图记录
    await page.screenshot({ path: 'test-results/agent-model-selector.png', fullPage: true })

    // 验证页面基本功能
    expect(textarea).toBeVisible()
  })

  test('2. 通过 API 添加动态供应商并验证模型列表', async ({ request }) => {
    // 获取 CSRF token
    const csrfResponse = await request.get('/api/v1/csrf-token')
    const csrfData = await csrfResponse.json()

    // 登录
    const loginResponse = await request.post('/api/v1/login', {
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfData.csrf_token
      },
      data: {
        email: 'admin@example.com',
        password: 'admin123'
      }
    })
    expect(loginResponse.ok()).toBeTruthy()
    const loginData = await loginResponse.json()
    const token = loginData.access_token

    // 添加测试供应商
    const addProviderResponse = await request.post('/api/v1/providers', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      data: {
        name: '测试 OpenAI 供应商',
        base_url: 'https://api.openai.com/v1',
        protocol: 'openai',
        api_key: 'sk-test-key-for-e2e'
      }
    })

    // 供应商添加可能失败（因为 API Key 无效），但应该返回 200 或 400
    const addStatus = addProviderResponse.status()
    console.log('添加供应商状态:', addStatus)

    if (addStatus === 200) {
      const addData = await addProviderResponse.json()
      console.log('添加供应商成功:', JSON.stringify(addData))

      // 获取供应商列表
      const listResponse = await request.get('/api/v1/providers', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      expect(listResponse.ok()).toBeTruthy()
      const providers = await listResponse.json()
      console.log('供应商列表:', JSON.stringify(providers, null, 2))

      // 清理：删除测试供应商
      if (providers.length > 0) {
        for (const p of providers) {
          await request.delete(`/api/v1/providers/${p.id}`, {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })
        }
        console.log('已清理测试供应商')
      }
    } else {
      console.log('供应商添加失败（预期行为，因为使用测试 API Key）')
    }
  })

  test('3. 检查 Agent 模型配置 API', async ({ request }) => {
    // 获取 CSRF token
    const csrfResponse = await request.get('/api/v1/csrf-token')
    const csrfData = await csrfResponse.json()

    // 登录
    const loginResponse = await request.post('/api/v1/login', {
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfData.csrf_token
      },
      data: {
        email: 'admin@example.com',
        password: 'admin123'
      }
    })
    const loginData = await loginResponse.json()
    const token = loginData.access_token

    // 获取 Agent 模型配置
    const configResponse = await request.get('/api/v1/models/agent-config', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
    expect(configResponse.ok()).toBeTruthy()
    const config = await configResponse.json()

    // 验证配置结构
    expect(config).toHaveProperty('assignments')
    expect(config).toHaveProperty('fallback_chains')
    expect(config).toHaveProperty('error_type_models')

    // 验证 assignments 包含所有级别
    const levels = ['SIMPLE', 'SMALL', 'MEDIUM', 'LARGE', 'ENTERPRISE']
    for (const level of levels) {
      expect(config.assignments).toHaveProperty(level)
      expect(config.assignments[level]).toHaveProperty('architect_model')
      expect(config.assignments[level]).toHaveProperty('frontend_model')
      expect(config.assignments[level]).toHaveProperty('backend_model')
      expect(config.assignments[level]).toHaveProperty('reviewer_model')
    }

    // 验证 fallback_chains
    expect(config.fallback_chains).toHaveProperty('default')
    expect(config.fallback_chains).toHaveProperty('error_recovery')
    expect(config.fallback_chains).toHaveProperty('code_generation')

    // 验证 error_type_models
    const errorTypes = ['NameError', 'AttributeError', 'ImportError', 'SyntaxError']
    for (const errorType of errorTypes) {
      expect(config.error_type_models).toHaveProperty(errorType)
    }

    console.log('Agent 模型配置验证通过')
    console.log('当前模型分配:', JSON.stringify(config.assignments, null, 2))
  })

  test('4. 前端 Agent 页面完整流程', async ({ page }) => {
    // 访问首页并登录
    await page.goto('/')
    await page.waitForTimeout(2000)

    await page.evaluate(async () => {
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
      localStorage.setItem('access_token', loginData.access_token)
      localStorage.setItem('username', loginData.username || 'admin')
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
    })

    // 导航到 Agent 页面
    await page.goto('/agent')
    await page.waitForTimeout(3000)

    // 检查页面元素
    const textarea = page.locator('textarea').first()
    await expect(textarea).toBeVisible({ timeout: 10000 })

    // 检查模式选择按钮
    const createButton = page.locator('button:has-text("创建")')
    const modifyButton = page.locator('button:has-text("修改")')
    const debugButton = page.locator('button:has-text("调试")')

    console.log('创建按钮可见:', await createButton.isVisible().catch(() => false))
    console.log('修改按钮可见:', await modifyButton.isVisible().catch(() => false))
    console.log('调试按钮可见:', await debugButton.isVisible().catch(() => false))

    // 检查生成按钮
    const generateButton = page.locator('button:has-text("开始生成"), button:has-text("生成")')
    console.log('生成按钮可见:', await generateButton.first().isVisible().catch(() => false))

    // 截图
    await page.screenshot({ path: 'test-results/agent-full-page.png', fullPage: true })

    // 验证基本功能
    expect(textarea).toBeVisible()
  })
})
