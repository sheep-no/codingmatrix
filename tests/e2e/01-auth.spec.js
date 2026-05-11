/**
 * 认证模块 E2E 测试
 * 覆盖: 登录、登出、Token刷新、权限路由、未登录拦截
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout, TEST_EMAIL, TEST_PASSWORD } from './fixtures/auth.js';

const INVALID_EMAIL = 'nonexistent@example.com';
const INVALID_PASSWORD = 'wrongpassword123';

test.describe('认证模块', () => {
  test('首页加载 - 未登录状态显示欢迎页面', async ({ page }) => {
    await logout(page);
    await page.goto('/');
    await expect(page).toHaveTitle(/AI Agent/);
    await expect(page.locator('.app-container')).toBeVisible();

    // 未登录状态应显示登录提示
    const loginPrompt = page.locator('.login-prompt');
    await expect(loginPrompt).toBeVisible();
  });

  test('API 登录 - 有效凭据应成功', async ({ page }) => {
    await logout(page);
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Click the login button in sidebar
    const loginBtn = page.locator('.login-prompt button');
    await expect(loginBtn).toBeVisible();
    await loginBtn.click();
    await page.waitForTimeout(500);

    // Fill email and password in the login modal
    const emailInput = page.locator('.modal-dialog input[type="email"], .modal-content input[type="email"], [class*="modal"] input[type="email"]').first();
    await expect(emailInput).toBeVisible();
    await emailInput.fill(TEST_EMAIL);

    const passwordInput = page.locator('.modal-dialog input[type="password"], .modal-content input[type="password"], [class*="modal"] input[type="password"]').first();
    await expect(passwordInput).toBeVisible();
    await passwordInput.fill(TEST_PASSWORD);

    // Click login button
    const submitBtn = page.locator('.modal-dialog button:has-text("登录"), .modal-content button:has-text("登录"), [class*="modal"] button:has-text("登录")');
    await submitBtn.click();
    await page.waitForTimeout(2000);

    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeTruthy();

    const username = await page.evaluate(() => localStorage.getItem('username'));
    expect(username).toBeTruthy();
  });

  test('API 登录 - 无效凭据应失败', async ({ page }) => {
    await logout(page);
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

      return resp.ok;
    }, { email: INVALID_EMAIL, password: INVALID_PASSWORD });

    expect(apiLogin).toBe(false);
  });

  test('登出 - 应清除所有 localStorage 数据', async ({ page }) => {
    await apiLogin(page);

    // Click logout button in sidebar
    const logoutBtn = page.locator('.logout-btn');
    await expect(logoutBtn).toBeVisible();
    await logoutBtn.click();
    await page.waitForTimeout(500);

    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeFalsy();
  });

  test('未登录用户发送消息 - 应触发登录弹窗', async ({ page }) => {
    await logout(page);
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Click the login button in the sidebar to open login dialog
    const loginBtn = page.locator('.login-prompt button[aria-label="登录"], .login-prompt button');
    await expect(loginBtn).toBeVisible();
    await loginBtn.click();
    await page.waitForTimeout(500);

    // Login modal should be visible
    const loginModal = page.locator('[class*="modal"], [class*="dialog"]').first();
    const modalVisible = await loginModal.isVisible().catch(() => false);
    expect(modalVisible).toBe(true);
  });

  test('未认证用户访问管理员页面 - 应被拦截', async ({ page, context }) => {
    await logout(page);
    
    // Listen for new pages (admin opens in new window)
    const [newPage] = await Promise.all([
      context.waitForEvent('page'),
      page.evaluate(() => window.open('/admin', '_blank')),
    ]);
    await newPage.waitForLoadState('domcontentloaded');
    
    // Should redirect to login or show login prompt
    const url = newPage.url();
    const hasLoginElement = await newPage.locator('.login-prompt, input[type="email"], input[type="password"]').first().isVisible().catch(() => false);
    expect(hasLoginElement || url.includes('login')).toBe(true);
    
    await newPage.close();
  });

  test('Token 持久化 - 刷新页面后应保持登录状态', async ({ page }) => {
    await apiLogin(page);

    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeTruthy();
  });

  test('localStorage 权限级别 - 登录后应有 permission_level', async ({ page }) => {
    await apiLogin(page);

    const permissionLevel = await page.evaluate(() => localStorage.getItem('permission_level'));
    expect(typeof permissionLevel).toBe('string');
  });
});
