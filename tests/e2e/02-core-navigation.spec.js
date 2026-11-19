/**
 * 核心布局与导航 E2E 测试
 * 覆盖: 页面加载、路由导航、错误边界、主题切换
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('核心布局与导航', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('首页加载 - 页面应正常渲染', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveTitle(/CodingMatrix/);
    
    // Simple check - page body should have content
    const bodyHTML = await page.innerHTML('body');
    expect(bodyHTML.length).toBeGreaterThan(100);
  });

  test('页面加载 - 响应 HTTP 200', async ({ page }) => {
    const response = await page.goto('/');
    expect(response.ok()).toBeTruthy();
  });

  test('主布局 - 三栏布局应可见', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    const mainLayout = page.locator('.main-layout');
    await expect(mainLayout).toBeVisible({ timeout: 5000 });
  });

  test('侧边栏 - 默认展开状态', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const sidebar = page.locator('#leftlist');
    await expect(sidebar).toBeVisible();
  });

  test('侧边栏折叠 - 点击折叠按钮', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const collapseBtn = page.locator('#collapse-btn');
    const sidebar = page.locator('#leftlist');

    await expect(sidebar).not.toHaveClass(/collapsed/);

    await collapseBtn.click();

    await expect(sidebar).toHaveClass(/collapsed/);
    await expect(collapseBtn).toHaveAttribute('aria-label', '展开侧边栏');
  });

  test('侧边栏展开 - 再次点击恢复', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const collapseBtn = page.locator('#collapse-btn');
    const sidebar = page.locator('#leftlist');

    await collapseBtn.click();
    await expect(sidebar).toHaveClass(/collapsed/);

    await collapseBtn.click();
    await expect(sidebar).not.toHaveClass(/collapsed/);
    await expect(collapseBtn).toHaveAttribute('aria-label', '收起侧边栏');
  });

  test('路由导航 - 项目生成页面', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');
    // Note: /project-generate redirects to /agent
    await expect(page).toHaveURL(/agent/);
  });

  test('路由导航 - 工作流页面', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/workflow/);
  });

  test('路由导航 - PPT 生成页面', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/ppt-generate/);
  });

  test('路由导航 - AI 绘画页面', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/image-generate/);
  });

  test('404 路由 - 未定义路径应重定向到首页', async ({ page }) => {
    await page.goto('/non-existent-route-xyz');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('.main-layout')).toBeVisible();
    await expect(page.getByRole('textbox', { name: '消息输入框' })).toBeVisible();
  });

  test('错误边界 - JavaScript 错误不应导致白屏', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => {
      const app = document.querySelector('#app');
      if (app) app.dispatchEvent(new CustomEvent('test-error'));
    });

    await page.waitForTimeout(500);

    await expect(page.locator('.app-container')).toBeVisible();
    await expect(page.locator('.main-layout')).toBeVisible();
  });

  test('主题切换 - 暗色模式', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const darkBtn = page.getByRole('radio', { name: '夜晚' });
    await expect(darkBtn).toBeVisible();

    await darkBtn.click();

    await expect(darkBtn).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('html')).toHaveClass(/theme-dark/);
    expect(await page.evaluate(() => localStorage.getItem('app-theme'))).toBe('theme-dark');
  });

  test('主题持久化 - 切换主题后刷新应保持', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.getByRole('radio', { name: '夜晚' }).click();
    await expect(page.locator('html')).toHaveClass(/theme-dark/);

    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('html')).toHaveClass(/theme-dark/);
    await expect(page.getByRole('radio', { name: '夜晚' })).toHaveAttribute('aria-checked', 'true');
  });
});
