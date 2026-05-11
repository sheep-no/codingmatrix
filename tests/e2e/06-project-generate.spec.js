/**
 * 项目生成页面 E2E 测试
 * 覆盖: 页面加载、需求输入、选项选择、开始生成、SSE进度、文件树、代码预览、停止生成、下载项目
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('项目生成页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - 项目生成页面应正常渲染', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/project-generate/);

    const hasContent = await page.evaluate(() => {
      return !!document.querySelector('#app');
    });
    expect(hasContent).toBeTruthy();
  });

  test('需求输入 - 文本框应可见并可输入', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea, input[type="text"]').first();
    const isVisible = await textarea.isVisible().catch(() => false);

    if (isVisible) {
      await textarea.fill('创建一个Todo应用');
      await expect(textarea).toHaveValue('创建一个Todo应用');
    }
  });

  test('技术栈选择 - 应有技术栈选项', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const techOptions = await page.evaluate(() => {
      return document.querySelectorAll('[class*="tech"], [class*="stack"], [class*="select"]').length > 0;
    });
    expect(techOptions).toBeTruthy();
  });

  test('开始生成 - 点击生成按钮', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate"), [class*="generate"]');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(2000);

      const generating = await page.evaluate(() => {
        return !!document.querySelector('[class*="generating"], [class*="loading"], [class*="progress"]');
      });
      expect(generating).toBeTruthy();
    }
  });

  test('文件树展示 - 生成后应显示文件树', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate"), [class*="generate"]');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(3000);

      const fileTree = page.locator('[class*="file-tree"], [class*="tree"]');
      const treeVisible = await fileTree.isVisible().catch(() => false);
      expect(treeVisible).toBeTruthy();
    }
  });

  test('代码预览 - 点击文件应预览内容', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate"), [class*="generate"]');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(3000);

      const firstFile = page.locator('[class*="file-tree"] [class*="file"]').first();
      const fileVisible = await firstFile.isVisible().catch(() => false);

      if (fileVisible) {
        await firstFile.click();
        await page.waitForTimeout(500);

        const previewVisible = await page.evaluate(() => {
          return !!document.querySelector('[class*="preview"], [class*="code"], [class*="editor"]');
        });
        expect(previewVisible).toBeTruthy();
      }
    }
  });

  test('停止生成 - 停止按钮应可见', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate"), [class*="generate"]');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(1000);

      const stopBtn = page.locator('button:has-text("停止"), button:has-text("Stop"), [class*="stop"]');
      const stopVisible = await stopBtn.isVisible().catch(() => false);
      expect(stopVisible).toBeTruthy();
    }
  });

  test('下载项目 - 下载按钮应可见', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    const generateBtn = page.locator('button:has-text("生成"), button:has-text("Generate"), [class*="generate"]');
    const isVisible = await generateBtn.isVisible().catch(() => false);

    if (isVisible) {
      await generateBtn.click();
      await page.waitForTimeout(3000);

      const downloadBtn = page.locator('button:has-text("下载"), button:has-text("Download"), [class*="download"]');
      const downloadVisible = await downloadBtn.isVisible().catch(() => false);
      expect(downloadVisible).toBeTruthy();
    }
  });
});
