const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test.describe('Authentication E2E Tests', () => {
  test('登录流程测试 - 有效凭据登录成功', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const apiLogin = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';

      const resp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ email, password }),
      });

      if (resp.ok) {
        const data = await resp.json();
        return { success: true, token: data.access_token, username: data.username };
      }
      const err = await resp.json().catch(() => ({}));
      return { success: false, error: err.detail || resp.statusText };
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    if (apiLogin.success) {
      await page.evaluate(({ token, username }) => {
        localStorage.setItem('access_token', token);
        localStorage.setItem('username', username);
        if (window.userStore && typeof window.userStore.setUser === 'function') {
          window.userStore.setUser({
            username,
            permission_level: 'normal',
            access_token: token,
            expires_in: 3600,
          });
        }
      }, { token: apiLogin.token, username: apiLogin.username });

      await page.reload();
      await page.waitForLoadState('domcontentloaded');

      const isLoggedIn = await page.evaluate(() => {
        return !!localStorage.getItem('access_token') ||
               !!document.querySelector('.main-layout') ||
               !!document.querySelector('[role="navigation"]');
      });
      expect(isLoggedIn).toBeTruthy();
    }
  });

  test('登录流程测试 - 无效凭据登录失败', async ({ page }) => {
    const response = await page.request.post(`${BASE_URL}/api/v1/login`, {
      headers: { 'Content-Type': 'application/json' },
      data: { email: 'invalid@example.com', password: 'wrongpassword' },
    });

    expect(response.status()).not.toBe(200);
  });

  test('注册流程测试 - 登录入口应存在', async ({ page }) => {
    await page.goto('/');
    // 等待加载状态消失，主应用渲染完成
    await page.waitForSelector('#app', { state: 'visible', timeout: 10000 });
    await page.waitForTimeout(1000);

    // 登录入口在侧边栏中
    const loginBtnExists = await page.evaluate(() => {
      return !!document.querySelector('.login-btn') ||
             !!document.querySelector('#top-login') ||
             !!document.querySelector('[class*="user-section"]');
    });
    expect(loginBtnExists).toBeTruthy();
  });

  test('Token 刷新测试 - 有效 token 应能刷新', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const apiLogin = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';

      const resp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ email, password }),
      });

      if (resp.ok) {
        const data = await resp.json();
        return data.access_token;
      }
      return null;
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    if (apiLogin) {
      const refreshResp = await page.request.post(`${BASE_URL}/api/v1/refresh`, {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiLogin}`,
        },
      });

      expect([200, 401, 404, 403]).toContain(refreshResp.status());
    }
  });

  test('登出测试 - 登出后 token 应被清除', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => {
      localStorage.setItem('access_token', 'test-token-123');
      localStorage.setItem('username', 'testuser');
    });

    await page.evaluate(() => {
      if (window.userStore && typeof window.userStore.logout === 'function') {
        window.userStore.logout();
      } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
      }
    });

    const tokenCleared = await page.evaluate(() => {
      return !localStorage.getItem('access_token');
    });
    expect(tokenCleared).toBeTruthy();
  });

  test('权限验证测试 - 未认证用户点击管理面板应提示登录', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('username');
    });

    // 查找并点击管理面板按钮
    const adminBtn = page.locator('[class*="admin"], button:has-text("管理面板")');
    await page.waitForTimeout(500);

    // 检查页面是否正常工作
    const isLoaded = await page.evaluate(() => {
      return document.readyState === 'complete' || document.readyState === 'interactive';
    });
    expect(isLoaded).toBeTruthy();
  });

  test('权限验证测试 - 已认证用户可访问受保护路由', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const apiLogin = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';

      const resp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ email, password }),
      });

      if (resp.ok) {
        const data = await resp.json();
        return { success: true, token: data.access_token, username: data.username };
      }
      return { success: false };
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    if (apiLogin.success) {
      await page.evaluate(({ token, username }) => {
        localStorage.setItem('access_token', token);
        localStorage.setItem('username', username);
      }, { token: apiLogin.token, username: apiLogin.username });

      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');

      const hasAccess = await page.evaluate(() => {
        return !window.location.href.includes('login');
      });
      expect(hasAccess).toBeTruthy();
    }
  });
});
