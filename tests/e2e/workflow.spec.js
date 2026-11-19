/**
 * 工作流页面 E2E 测试
 *
 * 覆盖输入与本地交互状态。真实工作流执行会调用外部模型，
 * 依赖模型 Key，不在本文件断言 SSE 内容。
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

const WORKFLOW_PLACEHOLDER = '描述你想要实现的功能，AI 将自动生成工作流...';

test.describe('工作流功能', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/workflow', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.workflow-page')).toBeVisible({ timeout: 30000 });
  });

  test('打开工作流', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'AI 工作流编排' })).toBeVisible();
  });

  test('输入自然语言描述', async ({ page }) => {
    const prompt = page.getByPlaceholder(WORKFLOW_PLACEHOLDER);
    await prompt.fill('查询天气并生成图表');
    await expect(prompt).toHaveValue('查询天气并生成图表');
  });

  test('空描述时执行按钮禁用，填写后启用', async ({ page }) => {
    const execute = page.locator('.execute-btn');
    await expect(execute).toBeDisabled();
    await page.getByPlaceholder(WORKFLOW_PLACEHOLDER).fill('整理一份日报');
    await expect(execute).toBeEnabled();
  });

  test('初始展示画布占位提示', async ({ page }) => {
    await expect(page.locator('.preview-placeholder')).toBeVisible();
  });

  test('无节点时导出按钮禁用', async ({ page }) => {
    await expect(page.getByRole('button', { name: '导出' })).toBeDisabled();
  });
});
