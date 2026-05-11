/**
 * PPT 生成 E2E 测试
 * 
 * 测试 PPT 生成功能：
 * - 主题输入
 * - 模板选择
 * - 生成进度
 * - 预览与下载
 */
import { test, expect } from '@playwright/test';

test.describe('PPT 生成', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('打开 PPT 生成', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await expect(page.locator('.ppt-generator')).toBeVisible();
  });

  test('输入主题', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await page.locator('.topic-input').fill('人工智能发展');
    await expect(page.locator('.topic-input')).toHaveValue('人工智能发展');
  });

  test('选择模板', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await expect(page.locator('.template-select')).toBeVisible();
  });

  test('选择页数', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await expect(page.locator('.pages-select')).toBeVisible();
  });

  test('生成任务', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await page.locator('.topic-input').fill('AI 发展');
    await page.locator('.generate-btn').click();
    
    await expect(page.locator('.task-progress')).toBeVisible();
  });

  test('预览 PPT', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await expect(page.locator('.ppt-preview')).toBeVisible();
  });

  test('下载 PPT', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=PPT 生成').click();
    
    await expect(page.locator('.download-btn')).toBeVisible();
  });
});
