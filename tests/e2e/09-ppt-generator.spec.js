/**
 * PPT 生成页面 E2E 测试
 * 覆盖: 页面加载、需求输入、模板选择、生成进度、预览、下载
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('PPT 生成页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - PPT 生成页面应正常渲染', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/ppt-generate/);

    const hasContent = await page.evaluate(() => !!document.querySelector('#app'));
    expect(hasContent).toBeTruthy();
  });

  test('主题输入 - 文本框应可见', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const topicInput = page.locator('textarea, input[type="text"]').first();
    await expect(topicInput).toBeVisible();

    await topicInput.fill('人工智能技术发展趋势');
    await expect(topicInput).toHaveValue('人工智能技术发展趋势');
  });

  test('模板选择 - 应有模板选项', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const templateOptions = page.locator('[class*="template"], [class*="option"], [class*="style"]');
    const templateCount = await templateOptions.count();
    expect(templateCount).toBeGreaterThan(0);
  });

  test('开始生成 - 点击生成按钮', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const topicInput = page.locator('textarea, input[type="text"]').first();
    await topicInput.fill('测试PPT生成');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate")');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(3000);

      const generating = await page.evaluate(() => {
        return !!document.querySelector('[class*="generating"], [class*="loading"], [class*="progress"]');
      });
      expect(generating).toBeTruthy();
    }
  });

  test('生成预览 - 应显示预览', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const topicInput = page.locator('textarea, input[type="text"]').first();
    await topicInput.fill('测试预览');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate")');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(3000);

      const previewVisible = await page.evaluate(() => {
        return !!document.querySelector('[class*="preview"], [class*="slide"]');
      });
      expect(previewVisible).toBeTruthy();
    }
  });

  test('下载 PPT - 下载按钮应可用', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const downloadBtn = page.locator('button:has-text("下载"), button:has-text("Download")');
    const downloadVisible = await downloadBtn.isVisible().catch(() => false);
    expect(downloadVisible).toBeTruthy();
  });
});
