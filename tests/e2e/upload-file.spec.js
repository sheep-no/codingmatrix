/**
 * 文件上传 E2E 测试
 *
 * 覆盖首页输入区的真实上传链路：隐藏 file input 选择文件后出现附件预览，
 * 支持多文件、上传结束后离开「上传中」中间态、可移除附件、拖拽时出现拖拽区。
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

const FILE_INPUT = 'input.hidden-file-input';
const PREVIEW_ITEM = '.attached-files .file-preview-item';

test.describe('文件上传功能', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page.locator(FILE_INPUT)).toBeAttached({ timeout: 15000 });
  });

  test('上传按钮可见', async ({ page }) => {
    await expect(page.locator('button.upload-btn[aria-label="上传文件或图片"]')).toBeVisible();
  });

  test('上传单个文件显示预览', async ({ page }) => {
    await page.locator(FILE_INPUT).setInputFiles({
      name: 'sample.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('hello upload')
    });

    const item = page.locator(PREVIEW_ITEM).first();
    await expect(page.locator('.attached-files')).toBeVisible();
    await expect(item).toBeVisible();
    await expect(item.locator('.file-name')).toHaveText('sample.txt');
  });

  test('上传结束后不再停留在上传中', async ({ page }) => {
    await page.locator(FILE_INPUT).setInputFiles({
      name: 'note.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('a'.repeat(512))
    });

    // 无论后端成功或失败，UI 都必须离开「上传中」中间态：
    // 成功显示文件大小，失败显示「上传失败」，避免附件永久卡住
    const item = page.locator(PREVIEW_ITEM).first();
    await expect(item).not.toHaveClass(/uploading/, { timeout: 20000 });
    const sizeCount = await item.locator('.file-size').count();
    const errorCount = await item.locator('.error-status').count();
    expect(sizeCount + errorCount).toBeGreaterThan(0);
  });

  test('多文件上传', async ({ page }) => {
    await page.locator(FILE_INPUT).setInputFiles([
      { name: 'one.txt', mimeType: 'text/plain', buffer: Buffer.from('1') },
      { name: 'two.txt', mimeType: 'text/plain', buffer: Buffer.from('2') }
    ]);

    await expect(page.locator(PREVIEW_ITEM)).toHaveCount(2);
    await expect(page.locator(PREVIEW_ITEM, { hasText: 'one.txt' })).toHaveCount(1);
    await expect(page.locator(PREVIEW_ITEM, { hasText: 'two.txt' })).toHaveCount(1);
  });

  test('移除附件', async ({ page }) => {
    await page.locator(FILE_INPUT).setInputFiles({
      name: 'removable.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('remove me')
    });

    await expect(page.locator(PREVIEW_ITEM)).toHaveCount(1);
    await page.locator(PREVIEW_ITEM).first().locator('.remove-btn').click();
    await expect(page.locator(PREVIEW_ITEM)).toHaveCount(0);
    await expect(page.locator('.attached-files')).toHaveCount(0);
  });

  test('拖拽时显示拖拽区', async ({ page }) => {
    await page.evaluate(() => {
      const dataTransfer = new DataTransfer();
      document.body.dispatchEvent(
        new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer })
      );
    });
    await expect(page.locator('.file-drop-zone')).toBeVisible();
    await expect(page.locator('.drop-title')).toHaveText('拖拽文件到此处');
  });
});
