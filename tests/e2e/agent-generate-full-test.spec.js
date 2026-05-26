const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test('Agent 项目生成 - 验证请求参数和响应', async ({ page }) => {
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

  // 3. 导航到 Agent 页面
  await page.goto(`${BASE_URL}/agent`);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1000);

  // 4. 在输入框中输入需求
  const textarea = page.locator('textarea.prompt-textarea');
  await expect(textarea).toBeVisible({ timeout: 5000 });
  await textarea.fill('创建一个简单的 Python Flask Hello World 项目');

  // 5. 监听 API 请求
  const apiCalls = [];
  page.on('request', req => {
    if (req.url().includes('/agent/') && req.method() === 'POST') {
      apiCalls.push({
        url: req.url(),
        method: req.method(),
        body: req.postData(),
        authHeader: req.headers()['authorization'],
      });
    }
  });

  // 6. 点击生成按钮
  const generateBtn = page.locator('button.btn-generate');
  await expect(generateBtn).toBeVisible({ timeout: 5000 });
  await generateBtn.click();

  // 7. 等待 API 请求
  await page.waitForTimeout(3000);

  console.log('API POST calls captured:', apiCalls.length);
  for (const call of apiCalls) {
    console.log(`  POST ${call.url.split('/').pop()}: ${call.authHeader ? '有 token' : '无 token'}`);
    if (call.body) {
      try {
        const body = JSON.parse(call.body);
        console.log('    请求体 keys:', Object.keys(body));
        console.log('    requirement:', body.requirement ? `✅ ${body.requirement.substring(0, 20)}...` : '❌ 无');
        console.log('    session_id:', body.session_id ? `✅ ${body.session_id}` : '❌ 无');
        console.log('    enable_review:', body.enable_review);
        console.log('    enable_memory:', body.enable_memory);
      } catch (e) {
        console.log('    请求体解析失败:', call.body.substring(0, 100));
      }
    }
  }

  // 8. 验证请求参数正确
  const generateCalls = apiCalls.filter(c => c.url.includes('/orchestrate/stream') || c.url.includes('/generate'));
  expect(generateCalls.length).toBeGreaterThan(0);
  
  for (const call of generateCalls) {
    expect(call.authHeader).toBeTruthy();
    const body = JSON.parse(call.body);
    expect(body.requirement).toBeTruthy();
    if (call.url.includes('/generate')) {
      expect(body.session_id).toBeTruthy();
    }
  }

  console.log('测试通过！项目生成请求参数正确。');
});
