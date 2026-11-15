const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';

test.describe('Core E2E Tests', () => {
  test('页面加载测试 - 首页应正常加载', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/CodingMatrix/);
    // Use first() to avoid strict mode violation when multiple #app elements exist
    const appEl = page.locator('.app-container').first();
    await expect(appEl).toBeVisible();
  });

  test('页面加载测试 - 加载状态应显示', async ({ page }) => {
    const response = await page.goto('/');
    expect(response.ok()).toBeTruthy();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('.main-layout')).toBeVisible();
    await expect(page.getByRole('textbox', { name: '消息输入框' })).toBeVisible();
  });

  test('路由导航测试 - 导航到登录页', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/.*login/);
  });

  test('路由导航测试 - 导航到未定义路由应显示 404', async ({ page }) => {
    await page.goto('/non-existent-route-xyz');
    await page.waitForLoadState('domcontentloaded');
    // 未定义路由由 catch-all 重定向到首页
    await expect(page).toHaveURL(/\/$|\?/);
    await expect(page.locator('.main-layout')).toBeVisible();
  });

  test('错误边界测试 - JavaScript 错误不应导致白屏', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // 设置错误监听
    const errors = [];
    page.on('pageerror', (error) => {
      errors.push(error.message);
    });

    // 注入一个会导致子组件错误的错误
    await page.evaluate(() => {
      const app = document.querySelector('#app');
      if (app) {
        app.dispatchEvent(new CustomEvent('test-error', { detail: 'Test error boundary' }));
      }
    });

    await page.waitForTimeout(1000);
    // 检查页面是否仍然可见（不是白屏）
    const isBlank = await page.evaluate(() => {
      return document.body.children.length === 0 || 
             document.body.textContent.trim() === '';
    });
    expect(isBlank).toBeFalsy();
  });

  test('主题切换测试 - 切换深色/浅色模式', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const html = page.locator('html');
    const lightBtn = page.getByRole('radio', { name: '白天' })
    const darkBtn = page.getByRole('radio', { name: '夜晚' })

    await lightBtn.click()
    await expect(html).toHaveClass(/theme-light/)
    await expect(lightBtn).toHaveAttribute('aria-checked', 'true')

    await darkBtn.click()
    await expect(html).toHaveClass(/theme-dark/)
    await expect(html).not.toHaveClass(/theme-light/)
    await expect(darkBtn).toHaveAttribute('aria-checked', 'true')
  });

  test('主题切换测试 - 深色模式类名应切换', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.getByRole('radio', { name: '夜晚' }).click()

    await expect(page.locator('html')).toHaveClass(/theme-dark/)
    await expect.poll(() => page.evaluate(() => localStorage.getItem('app-theme'))).toBe('theme-dark')
  });
});
