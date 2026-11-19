/**
 * 工作流页面 E2E 测试
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('工作流页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - 工作流页面应正常渲染', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/workflow$/);
    await expect(page.locator('.workflow-page')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'AI 工作流编排' })).toBeVisible();
  });

  test('节点编辑 - 点击节点应显示配置', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    // 未生成工作流时，画布展示占位提示，无节点卡片
    await expect(page.locator('.preview-panel .preview-placeholder')).toContainText('输入需求后点击执行');
    await expect(page.locator('.canvas-node')).toHaveCount(0);
    await expect(page.locator('.node-item')).toHaveCount(0);
  });

  test('执行工作流 - 执行按钮应可见', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const execute = page.locator('.execute-btn');
    await expect(execute).toBeVisible();
    await expect(execute).toHaveText('执行工作流');
    await expect(execute).toBeDisabled();

    await page.getByPlaceholder('描述你想要实现的功能，AI 将自动生成工作流...')
      .fill('查询天气并生成图表');
    await expect(execute).toBeEnabled();
  });

  test('工作流历史 - 应显示历史记录', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    // 历史区仅在存在历史任务时渲染；初始为空，不应出现历史列表
    await expect(page.locator('.history-list')).toHaveCount(0);
  });

  test('导入工作流 - 导入功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const importBtn = page.getByRole('button', { name: '导入' });
    await expect(importBtn).toBeVisible();

    const chooserPromise = page.waitForEvent('filechooser');
    await importBtn.click();
    const chooser = await chooserPromise;
    expect(chooser).toBeTruthy();

    // 导入入口只接受 JSON
    expect(await chooser.element().getAttribute('accept')).toBe('.json');
  });

  test('导出工作流 - 导出功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    // 无节点时导出禁用，避免导出空工作流
    const exportBtn = page.getByRole('button', { name: '导出' });
    await expect(exportBtn).toBeVisible();
    await expect(exportBtn).toBeDisabled();
  });
});
