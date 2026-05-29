const { test, expect } = require('@playwright/test')

test.describe('模型管理功能测试', () => {
  test.setTimeout(60000)

  test('1. 通过前端 API 更新降级链配置', async ({ page }) => {
    // 访问页面并登录
    await page.goto('/')
    await page.waitForTimeout(2000)

    // 通过浏览器上下文登录
    const loginResult = await page.evaluate(async () => {
      const csrfResponse = await fetch('/api/v1/csrf-token', { credentials: 'include' })
      const csrfData = await csrfResponse.json()
      
      const loginResponse = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfData.csrf_token
        },
        body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' })
      })
      return await loginResponse.json()
    })

    console.log('登录成功，权限:', loginResult.permission_level)
    expect(loginResult.access_token).toBeTruthy()

    // 保存 token 到 localStorage
    await page.evaluate((data) => {
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('permission_level', data.permission_level)
    }, loginResult)

    // 获取当前配置
    const currentConfig = await page.evaluate(async (token) => {
      const resp = await fetch('/api/v1/models/agent-config', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      return await resp.json()
    }, loginResult.access_token)
    
    console.log('当前降级链:', JSON.stringify(currentConfig.fallback_chains, null, 2))

    // 更新降级链配置
    const updateResult = await page.evaluate(async ({ token, chains }) => {
      const results = []
      for (const [chainName, models] of Object.entries(chains)) {
        const resp = await fetch('/api/v2/models/agent-config/fallback-chain', {
          method: 'PUT',
          credentials: 'include',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ chain_name: chainName, models })
        })
        results.push({ chain: chainName, status: resp.status, ok: resp.ok })
      }
      return results
    }, {
      token: loginResult.access_token,
      chains: {
        'default': ['qwen3-8b', 'glm-4-9b', 'qwen2.5-7b', 'qwen3.5-4b'],
        'error_recovery': ['deepseek-r1', 'qwen3-8b', 'glm-z1-9b', 'qwen3.5-4b'],
        'code_generation': ['deepseek-r1', 'qwen3-8b', 'qwen2.5-7b', 'glm-4-9b']
      }
    })

    console.log('更新结果:')
    for (const r of updateResult) {
      console.log(`  ${r.chain}: ${r.status} ${r.ok ? '✓' : '✗'}`)
    }

    // 验证更新后的配置
    const newConfig = await page.evaluate(async (token) => {
      const resp = await fetch('/api/v1/models/agent-config', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      return await resp.json()
    }, loginResult.access_token)

    console.log('\n更新后的降级链:')
    for (const [key, value] of Object.entries(newConfig.fallback_chains)) {
      console.log(`  ${key}: ${value.join(' -> ')}`)
    }

    // 验证降级链已更新
    expect(newConfig.fallback_chains.default).toEqual(['qwen3-8b', 'glm-4-9b', 'qwen2.5-7b', 'qwen3.5-4b'])
    expect(newConfig.fallback_chains.error_recovery).toEqual(['deepseek-r1', 'qwen3-8b', 'glm-z1-9b', 'qwen3.5-4b'])
    expect(newConfig.fallback_chains.code_generation).toEqual(['deepseek-r1', 'qwen3-8b', 'qwen2.5-7b', 'glm-4-9b'])
    console.log('\n降级链配置验证通过!')
  })

  test('2. 通过前端 API 更新错误类型模型映射', async ({ page }) => {
    // 访问页面并登录
    await page.goto('/')
    await page.waitForTimeout(2000)

    const loginResult = await page.evaluate(async () => {
      const csrfResponse = await fetch('/api/v1/csrf-token', { credentials: 'include' })
      const csrfData = await csrfResponse.json()
      const loginResponse = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfData.csrf_token
        },
        body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' })
      })
      return await loginResponse.json()
    })

    const token = loginResult.access_token
    expect(token).toBeTruthy()

    // 更新错误类型模型映射
    const mappings = [
      { error_type: 'NameError', model_id: 'qwen3-8b' },
      { error_type: 'AttributeError', model_id: 'qwen3-8b' },
      { error_type: 'ImportError', model_id: 'glm-4-9b' },
      { error_type: 'SyntaxError', model_id: 'deepseek-r1' },
      { error_type: 'TypeError', model_id: 'qwen3-8b' },
      { error_type: 'KeyError', model_id: 'glm-4-9b' },
      { error_type: 'IndexError', model_id: 'qwen3-8b' },
      { error_type: 'LogicError', model_id: 'deepseek-r1' }
    ]

    const updateResult = await page.evaluate(async ({ token, mappings }) => {
      const results = []
      for (const mapping of mappings) {
        const resp = await fetch('/api/v2/models/agent-config/error-type-model', {
          method: 'PUT',
          credentials: 'include',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(mapping)
        })
        results.push({ ...mapping, status: resp.status, ok: resp.ok })
      }
      return results
    }, { token, mappings })

    console.log('更新错误类型模型映射:')
    for (const r of updateResult) {
      console.log(`  ${r.error_type} -> ${r.model_id}: ${r.status} ${r.ok ? '✓' : '✗'}`)
    }

    // 验证更新后的配置
    const newConfig = await page.evaluate(async (token) => {
      const resp = await fetch('/api/v1/models/agent-config', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      return await resp.json()
    }, token)

    console.log('\n更新后的错误类型模型映射:')
    for (const [key, value] of Object.entries(newConfig.error_type_models)) {
      console.log(`  ${key}: ${value}`)
    }

    // 验证映射已更新
    expect(newConfig.error_type_models.SyntaxError).toBe('deepseek-r1')
    expect(newConfig.error_type_models.LogicError).toBe('deepseek-r1')
    expect(newConfig.error_type_models.ImportError).toBe('glm-4-9b')
    console.log('\n错误类型模型映射验证通过!')
  })

  test('3. 验证所有模型在前端可见', async ({ request }) => {
    // 获取模型列表
    const modelsResponse = await request.get('/api/v1/models/')
    expect(modelsResponse.ok()).toBeTruthy()
    const modelsData = await modelsResponse.json()

    console.log(`\n系统模型总数: ${modelsData.total}`)
    console.log('\n所有可用模型:')
    for (const model of modelsData.models) {
      const caps = model.capabilities.join(', ')
      const tags = model.tags.join(', ')
      console.log(`  - ${model.id}: ${model.name} [${caps}] ${tags}`)
    }

    // 验证新增模型存在
    const newModelIds = ['bge-m3', 'bge-reranker-v2-m3', 'bce-reranker', 'bge-large-zh', 'sense-voice', 'telespeech-asr', 'hunyuan-mt']
    for (const modelId of newModelIds) {
      const found = modelsData.models.find(m => m.id === modelId)
      expect(found).toBeTruthy()
      console.log(`✓ 新增模型 ${modelId} 存在`)
    }

    console.log('\n所有新增模型验证通过!')
  })
})
