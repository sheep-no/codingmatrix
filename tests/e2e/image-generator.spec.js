/**
 * AI 绘画 E2E 测试
 * 
 * 测试图像生成功能：
 * - 文本生成图像
 * - 参数配置
 * - 历史记录
 * - 图片下载
 */
import { test, expect } from '@playwright/test';

test.describe('AI 绘画', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('打开 AI 绘画', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await expect(page.locator('.image-generator')).toBeVisible();
  });

  test('输入提示词', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await page.locator('.prompt-input').fill('一只可爱的猫咪');
    await expect(page.locator('.prompt-input')).toHaveValue('一只可爱的猫咪');
  });

  test('选择模型', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await expect(page.locator('.model-select')).toBeVisible();
  });

  test('选择尺寸', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await expect(page.locator('.size-select')).toBeVisible();
  });

  test('生成图像', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await page.locator('.prompt-input').fill('一只猫咪');
    await page.locator('.generate-btn').click();
    
    await expect(page.locator('.generating-indicator')).toBeVisible();
  });

  test('历史记录限制', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await expect(page.locator('.history-count')).toBeVisible();
  });

  test('图片预览', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await expect(page.locator('.image-preview')).toBeVisible();
  });

  test('下载图片', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await expect(page.locator('.download-btn')).toBeVisible();
  });

  test('删除历史记录', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 绘画').click();
    
    await page.locator('.history-delete-btn').first().click();
    
    await expect(page.locator('.confirm-dialog')).toBeVisible();
  });
});
