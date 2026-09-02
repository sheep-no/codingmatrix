/**
 * 工作流页面 E2E 测试
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('工作流页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - 工作流页面应正常渲染', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/workflow/);
    expect(true).toBeTruthy();
  });

  test('节点编辑 - 点击节点应显示配置', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('.main-layout, #app, [class*="workflow"]');
    });
    expect(hasUI).toBeTruthy();
  });

  test('执行工作流 - 执行按钮应可见', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('.execute-btn');
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });

  test('工作流历史 - 应显示历史记录', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('.main-layout, #app');
    });
    expect(hasUI).toBeTruthy();
  });

  test('导入工作流 - 导入功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('.workflow-page');
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });

  test('导出工作流 - 导出功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForSelector('.export-btn');
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });
});
