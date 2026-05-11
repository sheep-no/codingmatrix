/**
 * 项目生成 E2E 测试
 * 
 * 测试完整的项目生成流程：
 * - 会话管理
 * - 多轮对话
 * - 代码预览
 * - 文件导出
 * - 视觉分析
 * - 代码审查
 */
import { test, expect } from '@playwright/test';

test.describe('项目生成流程', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('打开项目生成器', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 项目生成').click();
    
    await expect(page.locator('.project-generator')).toBeVisible();
  });

  test('发送项目需求', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 项目生成').click();
    
    await page.locator('.chat-input textarea').fill('创建一个贪吃蛇游戏');
    await page.locator('.send-button').click();

    await expect(page.locator('.chat-messages')).toContainText('贪吃蛇');
  });

  test('代码预览标签切换', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=AI 项目生成').click();
    
    await expect(page.locator('[data-tab="preview"]')).toBeVisible();
    await expect(page.locator('[data-tab="vision"]')).toBeVisible();
    await expect(page.locator('[data-tab="review"]')).toBeVisible();
  });

  test('视觉分析面板', async ({ page }) => {
    await page.locator('[data-tab="vision"]').click();
    
    await expect(page.locator('.vision-analysis')).toBeVisible();
    await expect(page.locator('.vision-description')).toBeVisible();
  });

  test('代码审查面板', async ({ page }) => {
    await page.locator('[data-tab="review"]').click();
    
    await expect(page.locator('.code-review')).toBeVisible();
    await expect(page.locator('.review-issues')).toBeVisible();
  });

  test('Agent 状态显示', async ({ page }) => {
    await expect(page.locator('.agent-status')).toBeVisible();
    await expect(page.locator('.agent-status')).toContainText('空闲');
  });

  test('文件树显示', async ({ page }) => {
    await expect(page.locator('.file-tree')).toBeVisible();
  });

  test('代码高亮', async ({ page }) => {
    await page.locator('[data-tab="preview"]').click();
    
    const codeBlock = page.locator('pre code');
    await expect(codeBlock).toHaveClass(/hljs/);
  });

  test('多文件切换', async ({ page }) => {
    await page.locator('.file-tree .file-item').first().click();
    
    const codeBlock = page.locator('pre code');
    await expect(codeBlock).toBeVisible();
  });

  test('导出项目', async ({ page }) => {
    await page.locator('.export-button').click();
    
    await expect(page.locator('.export-dialog')).toBeVisible();
    await expect(page.locator('text=导出格式')).toBeVisible();
  });

  test('新建会话', async ({ page }) => {
    await page.locator('#newSpeak').click();
    
    await expect(page.locator('.chat-messages')).toBeEmpty();
  });

  test('会话切换', async ({ page }) => {
    await page.locator('.session-select').click();
    await expect(page.locator('.session-dropdown')).toBeVisible();
  });
});
