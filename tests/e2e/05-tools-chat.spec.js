/**
 * 工具面板交互 E2E 测试
 * 覆盖：图表编辑器、Docker 配置、虚拟姬、临时工作流、PPT 生成、AI 绘画等工具
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('工具面板交互', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#toolkit').click();
  });

  test('图表编辑器 - 点击打开', async ({ page }) => {
    await page.locator('text=图表编辑器').click();
    await page.waitForTimeout(500);
    
    const menuClosed = await page.locator('#toolkit-menu').isHidden();
    expect(menuClosed).toBeTruthy();
  });

  test('Docker 配置 - 点击打开', async ({ page }) => {
    await page.locator('text=Docker 配置').click();
    await page.waitForTimeout(500);
    
    const menuClosed = await page.locator('#toolkit-menu').isHidden();
    expect(menuClosed).toBeTruthy();
  });

  test('AI 虚拟姬 - 点击打开', async ({ page }) => {
    await page.locator('text=虚拟姬').click();
    await page.waitForTimeout(800);

    const hasVirtualGirl = await page.evaluate(() => {
      return !!document.querySelector('.virtual-girl-window') ||
             !!document.querySelector('[class*="virtual-girl"]');
    });
    
    const menuClosed = await page.locator('#toolkit-menu').isHidden().catch(() => true);
    expect(menuClosed || hasVirtualGirl).toBeTruthy();
  });

  test('临时工作流 - 点击打开', async ({ page }) => {
    await page.locator('text=临时工作流').click();
    await page.waitForTimeout(500);
    
    const menuClosed = await page.locator('#toolkit-menu').isHidden();
    expect(menuClosed).toBeTruthy();
  });

  test('PPT 生成 - 点击打开', async ({ page }) => {
    await page.locator('text=PPT 生成').click();
    await page.waitForTimeout(500);
    
    const menuClosed = await page.locator('#toolkit-menu').isHidden();
    expect(menuClosed).toBeTruthy();
  });

  test('AI 绘画 - 点击打开', async ({ page }) => {
    await page.locator('text=AI 绘画').click();
    await page.waitForTimeout(500);
    
    const menuClosed = await page.locator('#toolkit-menu').isHidden();
    expect(menuClosed).toBeTruthy();
  });
});
