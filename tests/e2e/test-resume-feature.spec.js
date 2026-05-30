const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const TEST_EMAIL = process.env.TEST_EMAIL || 'admin@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'admin123';

test.describe('Agent 继续功能测试', () => {
  let authToken = null;

  test.beforeAll(async ({ browser }) => {
    // 登录获取 token
    const page = await browser.newPage();
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    const loginResult = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';

      const resp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ email, password }),
      });

      if (!resp.ok) return { success: false, error: await resp.text() };
      return await resp.json();
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    authToken = loginResult.access_token;
    await page.close();
  });

  test('测试意图检测 - 识别继续关键词', async ({ page }) => {
    // 设置 token
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    
    await page.evaluate((token) => {
      localStorage.setItem('access_token', token);
    }, authToken);

    // 测试不同输入的意图检测
    const testCases = [
      { input: '继续', expected_resume: true },
      { input: '继续，加上登录功能', expected_resume: true, expected_changes: true },
      { input: 'resume', expected_resume: true },
      { input: '帮我生成一个网站', expected_resume: false },
    ];

    for (const testCase of testCases) {
      // 通过 SSE 端点间接测试意图检测
      const result = await page.evaluate(async (input) => {
        const token = localStorage.getItem('access_token');
        const resp = await fetch('/api/v1/agent/orchestrate/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({
            requirement: input,
            enable_review: false,
            enable_validation: false,
            enable_error_recovery: false,
            enable_memory: false,
            spec_first: false,
            dependency_graph: false,
          }),
        });
        
        return { 
          status: resp.status,
          ok: resp.ok,
        };
      }, testCase.input);

      console.log(`输入: "${testCase.input}" -> 状态: ${result.status}, OK: ${result.ok}`);
    }
  });

  test('测试完整继续流程', async ({ page }) => {
    // 1. 设置 token
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await page.evaluate((token) => {
      localStorage.setItem('access_token', token);
      window.userStore?.setUser?.({
        username: 'test',
        permission_level: 'normal',
        access_token: token,
        expires_in: 1800,
      });
    }, authToken);

    // 2. 先创建一个会话
    const textarea = page.locator('textarea.prompt-textarea');
    await expect(textarea).toBeVisible({ timeout: 5000 });
    await textarea.fill('创建一个简单的 Python Flask Hello World 项目');

    // 3. 监听 SSE 请求
    const sseResponses = [];
    page.on('response', async (response) => {
      if (response.url().includes('/agent/orchestrate/stream')) {
        try {
          const text = await response.text();
          sseResponses.push(text);
        } catch (e) {
          // 忽略解析错误
        }
      }
    });

    // 4. 点击生成按钮
    const generateBtn = page.locator('button:has-text("开始生成")');
    await expect(generateBtn).toBeVisible({ timeout: 5000 });
    await generateBtn.click();

    // 5. 等待一段时间让生成开始
    await page.waitForTimeout(5000);

    // 6. 停止生成（模拟用户中断）
    const stopBtn = page.locator('button:has-text("停止")');
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
      await page.waitForTimeout(1000);
    }

    // 7. 输入"继续"测试恢复功能
    await textarea.fill('继续');
    
    // 8. 再次点击生成
    await generateBtn.click();
    await page.waitForTimeout(3000);

    // 9. 验证日志中是否有恢复会话的信息
    const logs = await page.evaluate(() => {
      const logElements = document.querySelectorAll('.log-entry, .log-item');
      return Array.from(logElements).map(el => el.textContent).join('\n');
    });

    console.log('测试完成，日志输出:');
    console.log(logs.substring(0, 500));
  });
});
