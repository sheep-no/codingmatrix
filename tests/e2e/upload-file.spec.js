/**
 * 文件上传 E2E 测试
 * 
 * 测试完整的文件上传流程：
 * - 上传按钮可见性
 * - 文件选择与预览
 * - 上传进度显示
 * - 上传成功/失败处理
 * - 多文件上传
 */
import { test, expect } from '@playwright/test';

test.describe('文件上传功能', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('上传按钮可见', async ({ page }) => {
    await expect(page.locator('[aria-label="上传文件"]')).toBeVisible();
  });

  test('上传单张图片文件', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    
    await fileInput.setInputFiles({
      name: 'test.png',
      mimeType: 'image/png',
      buffer: Buffer.from('fake image data')
    });

    await expect(page.locator('.upload-preview')).toBeVisible();
  });

  test('上传进度显示', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    
    await fileInput.setInputFiles({
      name: 'large-file.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.alloc(1024 * 1024)
    });

    await expect(page.locator('.upload-progress')).toBeVisible();
  });

  test('上传错误处理', async ({ page }) => {
    await page.route('**/api/v1/upload', async route => {
      await route.fulfill({
        status: 500,
        body: JSON.stringify({ error: '服务器错误' })
      });
    });

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('test content')
    });

    await expect(page.locator('.upload-error')).toBeVisible();
  });

  test('取消上传', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'large-file.zip',
      mimeType: 'application/zip',
      buffer: Buffer.alloc(10 * 1024 * 1024)
    });

    await page.locator('.upload-cancel-btn').click();
    await expect(page.locator('.upload-progress')).not.toBeVisible();
  });
});
