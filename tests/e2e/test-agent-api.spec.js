const { test, expect } = require('@playwright/test')

test('Agent API 测试', async ({ request }) => {
  const csrfResponse = await request.get('/api/v1/csrf-token')
  const csrfData = await csrfResponse.json()
  expect(csrfData.csrf_token).toBeTruthy()
  
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
  expect(loginData.access_token).toBeTruthy()
  
  const modelConfigResponse = await request.get('/api/v1/models/agent-config', {
    headers: {
      'Authorization': `Bearer ${loginData.access_token}`
    }
  })
  expect(modelConfigResponse.ok()).toBeTruthy()
  const modelConfig = await modelConfigResponse.json()
  console.log('Agent model config:', JSON.stringify(modelConfig, null, 2))
  
  expect(modelConfig.assignments).toBeTruthy()
  expect(modelConfig.fallback_chains).toBeTruthy()
})

test('动态供应商 API 测试', async ({ request }) => {
  const csrfResponse = await request.get('/api/v1/csrf-token')
  const csrfData = await csrfResponse.json()
  
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
  
  const providersResponse = await request.get('/api/v1/providers', {
    headers: {
      'Authorization': `Bearer ${loginData.access_token}`
    }
  })
  expect(providersResponse.ok()).toBeTruthy()
  const providers = await providersResponse.json()
  console.log('动态供应商列表:', JSON.stringify(providers, null, 2))
})
