// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 测试 Agent SSE 流式响应是否正常工作
 */
// 真实模型生成长流程，仅在提供 TEST_SILICONFLOW_API_KEY 时启用
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

test.describe('Agent SSE 流式响应测试', () => {
  test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）')

  test.setTimeout(360000)
  
  test('1. 验证 SSE 流式响应返回进度事件', async ({ page }) => {
    const sseEvents = []
    
    page.on('console', msg => {
      if (msg.type() === 'error' || msg.type() === 'warn') {
        console.log(`浏览器 ${msg.type()}: ${msg.text()}`)
      }
    })
    
    await page.goto('/')
    await page.waitForTimeout(2000)
    
    // 登录
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
        return { success: loginResponse.ok, token: loginData.access_token }
      } catch (e) {
        return { error: e.message }
      }
    })
    
    console.log('登录结果:', JSON.stringify(loginResult))
    expect(loginResult.success).toBe(true)
    
    // 保存用户信息到 localStorage
    await page.evaluate((loginData) => {
      localStorage.setItem('access_token', loginData.token)
      localStorage.setItem('username', 'admin')
      localStorage.setItem('email', 'mr_yang@example.com')
      localStorage.setItem('permission_level', 'superadmin')
    }, loginResult)

    // 同步服务端已配置的真实 Key（伪造 token 会触发 UserAPIKeyNotFoundError）
    await syncRealApiKeys(page)
    
    // 直接测试 SSE 流式响应
    const sseResult = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token')
      const apiKeys = JSON.parse(localStorage.getItem('codingmatrix_apikeys') || '[]')
      const apiKeyToken = apiKeys.length > 0 ? apiKeys[0].token : undefined
      
      if (!token) {
        return { error: 'No token found in localStorage', success: false }
      }
      
      const response = await fetch('/api/v1/agent/orchestrate/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'X-API-Key-Token': apiKeyToken || ''
        },
        credentials: 'include',
        body: JSON.stringify({
          requirement: '只生成 hello.py 一个文件，输出 Hello World',
          enable_review: false,
          enable_validation: false,
          enable_error_recovery: false,
          enable_memory: false,
          spec_first: false,
          dependency_graph: false,
          require_approval: false,
          api_key_token: apiKeyToken
        })
      })
      
      if (!response.ok) {
        return { error: `HTTP ${response.status}`, events: [] }
      }
      
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      const events = []
      let timeout = setTimeout(() => {
        reader.cancel()
      }, 300000) // 5分钟超时
      
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
                const event = { type: data.type, hasData: !!data.data }
                if (data.type === 'file') {
                  event.path = data.path
                  event.hasContent = !!data.content
                  event.contentLength = data.content ? data.content.length : 0
                }
                events.push(event)
              } catch (e) {
                events.push({ type: 'parse_error', raw: line.slice(6, 100) })
              }
            }
          }
        }
      } catch (e) {
        // reader.cancel() 会抛出异常，这是正常的
      }
      clearTimeout(timeout)
      
      return { success: true, eventCount: events.length, events: events }
    })
    
    console.log('SSE 流式响应结果:', JSON.stringify({
      success: sseResult.success,
      eventCount: sseResult.eventCount,
      eventTypes: sseResult.events.map(e => e.type)
    }))
    
    // 验证 SSE 流返回了事件
    expect(sseResult.success).toBe(true)
    expect(sseResult.eventCount).toBeGreaterThan(0)
    
    // 验证事件类型
    const eventTypes = sseResult.events.map(e => e.type)
    console.log('事件类型:', eventTypes)
    
    // 应该至少有 progress 事件
    expect(eventTypes).toContain('progress')
    
    // 检查是否有 file 事件
    const fileEvents = sseResult.events.filter(e => e.type === 'file')
    console.log('file 事件数量:', fileEvents.length)
    if (fileEvents.length > 0) {
      console.log('file 事件详情:', JSON.stringify(fileEvents[0]))
    }
    
    // 检查是否有 done 事件
    const doneEvents = sseResult.events.filter(e => e.type === 'done')
    console.log('done 事件数量:', doneEvents.length)
    
    // 验证有 file 和 done 事件
    expect(fileEvents.length).toBeGreaterThan(0)
    expect(doneEvents.length).toBeGreaterThan(0)
  })
})
