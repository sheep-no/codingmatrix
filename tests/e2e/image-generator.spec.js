/**
 * AI 绘画页面 E2E 测试
 *
 * 只覆盖本地可验证的界面行为，真实文生图需要外部模型 Key，
 * 由 image-generation-acceptance.spec.js 在具备 Key 的环境验证。
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('AI 绘画', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/image-generate', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.image-generate-page')).toBeVisible({ timeout: 30000 });
  });

  test('打开 AI 绘画', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'AI 绘画' })).toBeVisible();
  });

  test('输入提示词', async ({ page }) => {
    const prompt = page.getByPlaceholder('描述你想要生成的画面...');
    await prompt.fill('一只可爱的猫咪');
    await expect(prompt).toHaveValue('一只可爱的猫咪');
  });

  test('选择风格', async ({ page }) => {
    const style = page.locator('.style-card').first();
    await expect(style).toBeVisible();
    await style.click();
    await expect(style).toHaveClass(/selected/);
  });

  test('选择分辨率', async ({ page }) => {
    const resolution = page.locator('#image-resolution');
    await expect(resolution).toBeVisible();
    await resolution.selectOption('768x768');
    await expect(resolution).toHaveValue('768x768');
  });

  test('空描述时生成按钮禁用，填写后启用', async ({ page }) => {
    const generate = page.locator('.btn-generate');
    await expect(generate).toBeDisabled();
    await page.getByPlaceholder('描述你想要生成的画面...').fill('一只猫咪');
    await expect(generate).toBeEnabled();
  });

  test('切换到图生图显示参考图片上传区', async ({ page }) => {
    await page.getByRole('button', { name: '图生图' }).click();
    await expect(page.locator('.upload-area')).toBeVisible();
  });

  test('高级选项可展开并显示随机种子', async ({ page }) => {
    await page.locator('.advanced-options summary').click();
    await expect(page.locator('.seed-input')).toBeVisible();
  });
});
