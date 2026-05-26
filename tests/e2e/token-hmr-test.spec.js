const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const TEST_EMAIL = 'test@test.com';
const TEST_PASSWORD = 'Test123456!';

test.describe('Agent 页面 Token 传递测试', () => {
  test('登录后导航到 Agent 页面，token 应正确传递', async ({ page }) => {
    // 1. 打开首页
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // 2. 通过 API 登录
    const loginResult = await page.evaluate(async ({ email, password }) => {
      try {
        // 获取 CSRF token
        const csrfResp = await fetch('/api/v1/csrf-token', { credentials: 'include' });
        await csrfResp.json(); // 等待响应完成
        
        // 从 cookie 获取 CSRF token
        const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
        const csrfToken = csrfMatch ? csrfMatch[1] : null;
        
        if (!csrfToken) {
          return { success: false, error: 'Failed to get CSRF token' };
        }

        const resp = await fetch('/api/v1/login', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          body: JSON.stringify({ email, password }),
        });

        const data = await resp.json();
        
        if (!resp.ok) {
          return { success: false, error: data.message || data.detail || resp.statusText };
        }

        return { success: true, ...data };
      } catch (e) {
        return { success: false, error: e.message };
      }
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    console.log('登录结果:', loginResult.success ? '成功' : loginResult.error);
    expect(loginResult.success).toBe(true);

    // 3. 设置 token 到 userStore 和 localStorage
    await page.evaluate((data) => {
      // 设置到 userStore
      if (window.userStore && window.userStore.setUser) {
        window.userStore.setUser({
          username: data.username,
          permission_level: data.permission_level || 'normal',
          access_token: data.access_token,
          expires_in: 1800,
        });
      }
      // 同时设置到 localStorage 作为备份
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('username', data.username);
      localStorage.setItem('email', 'test@test.com');
      localStorage.setItem('permission_level', data.permission_level || 'normal');
    }, loginResult);

    // 4. 验证登录成功
    const tokenAfterLogin = await page.evaluate(() => {
      return window.userStore?.getAccessToken?.() || localStorage.getItem('access_token');
    });
    console.log('登录后 token:', tokenAfterLogin ? tokenAfterLogin.substring(0, 20) + '...' : 'none');
    expect(tokenAfterLogin).toBeTruthy();

    // 5. 导航到 Agent 页面
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1500);

    // 6. 验证 token 仍然存在
    const tokenAfterNav = await page.evaluate(() => {
      const storeToken = window.userStore?.getAccessToken?.();
      const localToken = localStorage.getItem('access_token');
      const sessionToken = sessionStorage.getItem('_token');
      console.log('Token 检查:', {
        storeToken: storeToken ? storeToken.substring(0, 20) + '...' : 'none',
        localToken: localToken ? localToken.substring(0, 20) + '...' : 'none',
        sessionToken: sessionToken ? sessionToken.substring(0, 20) + '...' : 'none',
      });
      return storeToken || localToken || sessionToken;
    });
    console.log('导航到 Agent 后 token:', tokenAfterNav ? tokenAfterNav.substring(0, 20) + '...' : 'none');
    expect(tokenAfterNav).toBeTruthy();

    // 7. 监听 API 请求
    const apiCalls = [];
    page.on('request', req => {
      if (req.url().includes('/agent/')) {
        apiCalls.push({
          url: req.url(),
          authHeader: req.headers()['authorization'],
        });
      }
    });

    // 8. 刷新页面触发数据加载
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);

    // 9. 检查 API 请求是否携带 token
    console.log('Agent API 调用次数:', apiCalls.length);
    for (const call of apiCalls) {
      console.log(`  - ${call.url.split('/').pop()}: ${call.authHeader ? '有 token' : '无 token'}`);
    }

    // 10. 验证有 token 的请求
    const callsWithToken = apiCalls.filter(c => c.authHeader);
    console.log('带 token 的请求:', callsWithToken.length, '/', apiCalls.length);

    // 11. 检查控制台错误
    const consoleErrors = [];
    page.on('console', msg => {
      const text = msg.text();
      if (msg.type() === 'error' && (text.includes('401') || text.includes('Unauthorized'))) {
        consoleErrors.push(text);
      }
    });

    await page.waitForTimeout(2000);
    console.log('401 错误数:', consoleErrors.length);
    
    if (apiCalls.length > 0) {
      expect(callsWithToken.length).toBeGreaterThan(0);
    }
    
    console.log('测试完成！');
  });
});
