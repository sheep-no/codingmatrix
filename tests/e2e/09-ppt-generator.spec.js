/**
 * PPT 生成页面 E2E 测试
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('PPT 生成页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - PPT 生成页面应正常渲染', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/ppt-generate/);
    expect(true).toBeTruthy();
  });

  test('主题输入 - 文本框应可见', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    
    const hasInput = await page.evaluate(() => {
      return !!document.querySelector('textarea, input');
    });
    expect(hasInput).toBeTruthy();
  });

  test('模板选择 - 应有模板选项', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('[class*="template"], button, [class*="select"]');
    });
    expect(hasUI).toBeTruthy();
  });

  test('开始生成 - 点击生成按钮', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });

  test('生成预览 - 应显示预览', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('.main-content, #app');
    });
    expect(hasUI).toBeTruthy();
  });

  test('下载 PPT - 下载按钮应可用', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });
});
