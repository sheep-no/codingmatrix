const { test, expect } = require('@playwright/test')

const TEST_EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const TEST_PASSWORD = process.env.TEST_ADMIN_PASSWORD

test('Agent API 测试', async ({ request }) => {
  test.skip(!TEST_PASSWORD, '需要设置 TEST_ADMIN_PASSWORD 才能执行认证 API 验收')
  const csrfResponse = await request.get('/api/v1/csrf-token')
  const csrfData = await csrfResponse.json()
  expect(csrfData.csrf_token).toBeTruthy()
  
  const loginResponse = await request.post('/api/v1/login', {
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfData.csrf_token,
      'Cookie': `csrf_token=${csrfData.csrf_token}`
    },
    data: {
      email: TEST_EMAIL,
      password: TEST_PASSWORD
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
  
  expect(modelConfig.roles).toBeTruthy()
  expect(modelConfig.fallback_chain).toBeTruthy()
})

test('动态供应商 API 测试', async ({ request }) => {
  test.skip(!TEST_PASSWORD, '需要设置 TEST_ADMIN_PASSWORD 才能执行认证 API 验收')
  const csrfResponse = await request.get('/api/v1/csrf-token')
  const csrfData = await csrfResponse.json()
  
  const loginResponse = await request.post('/api/v1/login', {
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfData.csrf_token,
      'Cookie': `csrf_token=${csrfData.csrf_token}`
    },
    data: {
      email: TEST_EMAIL,
      password: TEST_PASSWORD
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
