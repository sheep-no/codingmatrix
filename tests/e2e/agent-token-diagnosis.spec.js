import { test, expect } from '@playwright/test';

test('Agent 接口 Token 传递诊断', async ({ page }) => {
  const allRequests = [];
  const authRequests = [];

  page.on('request', request => {
    if (request.url().includes('/api/v1/agent')) {
      allRequests.push({
        url: request.url(),
        method: request.method(),
        headers: request.headers(),
      });
    }
  });

  page.on('response', async response => {
    const url = response.url();
    if (url.includes('/api/v1/agent')) {
      const status = response.status();
      let body = '';
      try { body = await response.text(); } catch {}
      authRequests.push({
        url,
        status,
        method: response.request().method(),
        headers: response.request().headers(),
        body: body.substring(0, 300),
      });
    }
  });

  // 获取 CSRF token
  const csrfResponse = await page.request.get('http://localhost:8000/api/v1/csrf-token');
  const csrfData = await csrfResponse.json();
  const csrfToken = csrfData.csrf_token;
  console.log('CSRF Token:', csrfToken ? csrfToken.substring(0, 20) : 'none');

  // 通过 API 登录（需要 CSRF token）
  const context = page.context();
  const loginResponse = await page.request.post('http://localhost:8000/api/v1/login', {
    data: { email: 'test@test.com', password: 'Test123456!' },
    headers: { 'X-CSRF-Token': csrfToken },
  });
  const loginData = await loginResponse.json();
  console.log('登录响应:', JSON.stringify(loginData).substring(0, 200));
  const token = loginData.access_token || loginData.data?.access_token;
  console.log('Token 前 20 字符:', token ? token.substring(0, 20) : 'none');

  // 设置 token 到 localStorage 和 sessionStorage
  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
  await page.evaluate((tok) => {
    localStorage.setItem('access_token', tok);
    localStorage.setItem('username', 'test');
    localStorage.setItem('email', 'test@test.com');
    localStorage.setItem('permission_level', 'normal');
    sessionStorage.setItem('_token', tok);
    sessionStorage.setItem('_token_expiry', String(Date.now() + 3600000));
  }, token);

  console.log('Token 已设置到 localStorage 和 sessionStorage');

  // 导航到 Agent 页面
  await page.goto('http://localhost:5173/agent', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  // 检查 localStorage 中的 token
  const storedToken = await page.evaluate(() => localStorage.getItem('access_token'));
  console.log('localStorage 中的 token:', storedToken ? storedToken.substring(0, 20) + '...' : 'none');

  // 检查 sessionStorage 中的 token
  const sessionToken = await page.evaluate(() => sessionStorage.getItem('_token'));
  console.log('sessionStorage 中的 token:', sessionToken ? sessionToken.substring(0, 20) + '...' : 'none');

  // 检查 window.userStore
  const userStoreToken = await page.evaluate(() => {
    if (window.userStore && window.userStore.getAccessToken) {
      const t = window.userStore.getAccessToken();
      return t ? t.substring(0, 20) + '...' : 'none';
    }
    return 'window.userStore not available';
  }).catch(() => 'error checking userStore');
  console.log('window.userStore.getAccessToken():', userStoreToken);

  // 检查 window.api
  const apiExists = await page.evaluate(() => !!window.api).catch(() => false);
  console.log('window.api 存在:', apiExists);

  // 尝试触发请求 - 填充输入框并点击生成
  const promptInput = page.locator('.prompt-textarea');
  const hasInput = await promptInput.count().then(c => c > 0).catch(() => false);
  console.log('找到输入框:', hasInput);

  if (hasInput) {
    await promptInput.fill('test project');
    await page.waitForTimeout(500);

    const btn = page.locator('button.btn-generate:not(:disabled)');
    const btnCount = await btn.count();
    console.log('可点击的生成按钮:', btnCount);

    if (btnCount > 0) {
      console.log('点击生成按钮...');
      await btn.first().click();
      await page.waitForTimeout(5000);
    }
  }

  // 报告所有 Agent 请求
  console.log('\n=== Agent API 请求汇总 ===');
  if (authRequests.length === 0) {
    console.log('没有捕获到任何 Agent API 请求');
  }
  for (const req of authRequests) {
    console.log(`[${req.status}] ${req.method} ${req.url}`);
    console.log(`  Authorization: ${req.headers['authorization'] ? 'YES (' + req.headers['authorization'].substring(0, 30) + '...)' : 'NO'}`);
    console.log(`  Response: ${req.body.substring(0, 100)}`);
    console.log('');
  }

  // 断言
  expect(authRequests.length).toBeGreaterThan(0);
  for (const req of authRequests) {
    expect(req.status).not.toBe(401);
  }
});
