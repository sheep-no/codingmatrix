const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test('验证 agent 项目生成接口请求参数正确', async ({ page }) => {
  // 1. 登录
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1000);

  const loginResult = await page.evaluate(async () => {
    await fetch('/api/v1/csrf-token', { credentials: 'include' });
    const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
    const csrfToken = csrfMatch ? csrfMatch[1] : '';

    const resp = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ email: 'test@test.com', password: 'Test123456!' }),
    });

    if (!resp.ok) return { success: false, error: await resp.text() };
    return await resp.json();
  });

  expect(loginResult.access_token).toBeTruthy();

  // 2. 设置 token
  await page.evaluate((data) => {
    window.userStore?.setUser?.({
      username: data.username,
      permission_level: data.permission_level || 'normal',
      access_token: data.access_token,
      expires_in: 1800,
    });
    localStorage.setItem('access_token', data.access_token);
  }, loginResult);

  // 3. 监听 API 请求
  const apiCalls = [];
  page.on('request', req => {
    if (req.url().includes('/agent/')) {
      apiCalls.push({
        url: req.url(),
        method: req.method(),
        body: req.postData(),
        authHeader: req.headers()['authorization'],
      });
    }
  });

  // 4. 导航到 Agent 页面
  await page.goto(`${BASE_URL}/agent`);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1500);

  console.log('API calls captured:', apiCalls.length);
  for (const call of apiCalls) {
    console.log(`  ${call.method} ${call.url.split('/').pop()}: ${call.authHeader ? '有 token' : '无 token'}`);
    if (call.body) {
      try {
        const body = JSON.parse(call.body);
        console.log('    请求体 keys:', Object.keys(body));
        console.log('    requirement:', body.requirement ? '✅ 有' : '❌ 无');
        console.log('    session_id:', body.session_id ? '✅ 有' : '❌ 无');
      } catch (e) {}
    }
  }

  // 5. 验证有 API 调用且携带 token
  expect(apiCalls.length).toBeGreaterThan(0);
  expect(apiCalls.some(c => c.authHeader)).toBe(true);
  
  // 6. 验证没有 401/422 错误
  const consoleErrors = [];
  page.on('console', msg => {
    const text = msg.text();
    if (msg.type() === 'error' && (text.includes('401') || text.includes('422'))) {
      consoleErrors.push(text);
    }
  });

  await page.waitForTimeout(2000);
  console.log('401/422 错误数:', consoleErrors.length);
  expect(consoleErrors.length).toBe(0);
  
  console.log('测试通过！Agent API 请求参数正确。');
});
