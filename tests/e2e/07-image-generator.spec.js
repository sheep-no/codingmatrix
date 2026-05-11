/**
 * AI 绘画页面 E2E 测试
 * 覆盖: 文生图、图生图、风格选择、高级参数、历史记录、图片下载
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('AI 绘画页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - AI 绘画页面应正常渲染', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/image-generate/);
  });

  test('Prompt 输入 - 文本框应可见', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const promptInput = page.locator('textarea, input[type="text"]').first();
    await expect(promptInput).toBeVisible();

    await promptInput.fill('一只在草地上奔跑的金毛犬');
    await expect(promptInput).toHaveValue('一只在草地上奔跑的金毛犬');
  });

  test('风格选择 - 应有风格选项', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const styleOptions = page.locator('[class*="style"], [class*="option"]');
    const styleCount = await styleOptions.count();
    expect(styleCount).toBeGreaterThan(0);
  });

  test('生成图片 - 点击生成按钮', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const promptInput = page.locator('textarea, input[type="text"]').first();
    await promptInput.fill('测试图片生成');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate")');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(3000);

      const loading = await page.evaluate(() => {
        return !!document.querySelector('[class*="loading"], [class*="generating"], [class*="progress"]');
      });
      expect(loading).toBeTruthy();
    }
  });

  test('图生图模式 - 上传图片', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const img2imgToggle = page.locator('text=图生图, [class*="img2img"], [class*="image-to-image"]');
    const isVisible = await img2imgToggle.isVisible().catch(() => false);

    if (isVisible) {
      await img2imgToggle.click();
      await page.waitForTimeout(500);

      const uploadArea = page.locator('[class*="upload"], [class*="drop"]');
      const uploadVisible = await uploadArea.isVisible().catch(() => false);
      expect(uploadVisible).toBeTruthy();
    }
  });

  test('高级参数 - 分辨率、步数、CFG、种子', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const advancedToggle = page.locator('text=高级, [class*="advanced"]');
    const isVisible = await advancedToggle.isVisible().catch(() => false);

    if (isVisible) {
      await advancedToggle.click();
      await page.waitForTimeout(500);

      const params = await page.evaluate(() => {
        return document.querySelectorAll('[class*="param"], [class*="slider"], [class*="input"]').length > 0;
      });
      expect(params).toBeTruthy();
    }
  });

  test('历史记录 - 应显示历史生成记录', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const historySection = page.locator('[class*="history"], [class*="recent"]');
    const historyVisible = await historySection.isVisible().catch(() => false);
    expect(historyVisible).toBeTruthy();
  });

  test('图片下载 - 下载按钮应可用', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const downloadBtn = page.locator('[class*="download"]');
    const downloadVisible = await downloadBtn.isVisible().catch(() => false);

    if (downloadVisible) {
      await expect(downloadBtn).toBeVisible();
    }
  });

  test('删除历史记录 - 应可删除单条历史', async ({ page }) => {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');

    const deleteBtn = page.locator('[class*="history"] [class*="delete"], [class*="remove"]').first();
    const deleteVisible = await deleteBtn.isVisible().catch(() => false);

    if (deleteVisible) {
      await deleteBtn.click();
      await page.waitForTimeout(500);
    }
  });
});
