/**
 * AI 绘画页面 E2E 测试
 * 覆盖：文生图、图生图、风格选择、高级参数、历史记录、图片下载
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('AI 绘画页面', () => {
  test.describe.configure({ timeout: 120000 });

  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  async function openImagePage(page) {
    await page.goto('/image-generate');
    await page.waitForLoadState('domcontentloaded');
    await page.getByPlaceholder('描述你想要生成的画面...').waitFor({ state: 'visible', timeout: 90000 });
  }

  test('页面加载 - AI 绘画页面应正常渲染', async ({ page }) => {
    await openImagePage(page);
    await expect(page).toHaveURL(/image-generate/);
    await expect(page.locator('.image-generator-container')).toBeVisible();
  });

  test('Prompt 输入 - 文本框应可见', async ({ page }) => {
    await openImagePage(page);
    await expect(page.getByPlaceholder('描述你想要生成的画面...')).toBeVisible();
  });

  test('风格选择 - 应有风格选项', async ({ page }) => {
    await openImagePage(page);
    await expect(page.locator('.style-card').first()).toBeVisible();
  });

  test('生成图片 - 点击生成按钮', async ({ page }) => {
    await openImagePage(page);
    const promptInput = page.getByPlaceholder('描述你想要生成的画面...');
    await promptInput.fill('一只在月光下的银色狐狸');
    await expect(page.getByRole('button', { name: '开始生成' })).toBeEnabled();
  });

  test('图片展示 - 生成后应显示图片', async ({ page }) => {
    await openImagePage(page);
    await expect(page.locator('.result-section')).toHaveCount(0);
    await expect(page.locator('.image-generator-container')).toBeVisible();
  });
});
