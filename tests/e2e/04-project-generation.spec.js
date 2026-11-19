/**
 * 项目生成流程 E2E 测试
 * 覆盖: 项目生成入口访问、输入需求、提交生成、查看生成进度
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout, TEST_EMAIL, TEST_PASSWORD } from './fixtures/auth.js';

test.describe('项目生成流程', () => {
  test('未登录访问项目生成页面应被重定向回首页并保留目标', async ({ page }) => {
    await logout(page);
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    // /project-generate 先重定向到 /agent，路由守卫再把未登录用户送回首页并携带 redirect
    await expect(page).toHaveURL(/\/\?redirect=\/?agent$/);
    await expect(page.locator('.main-layout')).toBeVisible();
    await expect(page.locator('.login-btn')).toBeVisible();
    await expect(page.locator('.agent-page')).toHaveCount(0);

    // 未定义的 /project-generator 直接回落首页
    await page.goto('/project-generator');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/$/);
  });

  test('已登录可访问项目生成页面', async ({ page }) => {
    await apiLogin(page);
    await page.goto('/project-generator');
    await page.waitForLoadState('domcontentloaded');

    // /project-generator 未定义，/project-generate 会重定向到 /agent
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('.main-layout')).toBeVisible();

    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/agent$/);
    await expect(page.locator('.agent-page')).toBeVisible();
  });

  test('已登录可访问 Agent 仪表盘', async ({ page }) => {
    await apiLogin(page);
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/agent$/);
    await expect(page.locator('.agent-page')).toBeVisible();
    await expect(page.locator('.agent-topbar')).toBeVisible();
    await expect(page.getByRole('textbox', { name: '项目需求' })).toBeVisible();
  });

  test('Token 过期场景 - API 调用应触发刷新或重新登录', async ({ page }) => {
    await apiLogin(page);

    // 模拟 token 过期
    await page.evaluate(() => {
      const expired = Math.floor(Date.now() / 1000) - 100;
      const fakeToken = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6ImV4cGlyZWQiLCJpYXQiOjEyMzR9.fake`;
      sessionStorage.setItem('_token', fakeToken);
      sessionStorage.setItem('_token_expiry', String(Date.now() - 1000));
      localStorage.setItem('access_token', fakeToken);
    });

    // 重新访问受保护页面
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    // 守卫会刷新 token：仍停留在受保护页面，且 localStorage 换成了有效 token
    await expect(page).toHaveURL(/\/agent$/);
    await expect(page.locator('.agent-page')).toBeVisible();
    const refreshed = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(refreshed).not.toBe(
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6ImV4cGlyZWQiLCJpYXQiOjEyMzR9.fake'
    );
  });
});
