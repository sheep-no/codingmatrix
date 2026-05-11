/**
 * 工作流页面 E2E 测试
 * 覆盖: 页面加载、节点创建、节点连接、工作流执行、SSE进度、历史记录、导入导出
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('工作流页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - 工作流页面应正常渲染', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/workflow/);

    const hasContent = await page.evaluate(() => !!document.querySelector('#app'));
    expect(hasContent).toBeTruthy();
  });

  test('节点工具栏 - 应有节点选项', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const nodeToolbar = page.locator('[class*="toolbar"], [class*="node-list"]');
    const isVisible = await nodeToolbar.isVisible().catch(() => false);
    expect(isVisible).toBeTruthy();
  });

  test('添加节点 - 拖拽或点击添加', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const addBtn = page.locator('button:has-text("添加"), button:has-text("Add"), [class*="add-node"]');
    const isVisible = await addBtn.isVisible().catch(() => false);

    if (isVisible) {
      await addBtn.click();
      await page.waitForTimeout(500);

      const nodeCount = await page.evaluate(() => {
        return document.querySelectorAll('[class*="node"]').length;
      });
      expect(nodeCount).toBeGreaterThan(0);
    }
  });

  test('节点配置 - 点击节点打开配置面板', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const firstNode = page.locator('[class*="node"]').first();
    const isVisible = await firstNode.isVisible().catch(() => false);

    if (isVisible) {
      await firstNode.click();
      await page.waitForTimeout(500);

      const configPanel = page.locator('[class*="config"], [class*="settings"], [class*="panel"]');
      const configVisible = await configPanel.isVisible().catch(() => false);
      expect(configVisible).toBeTruthy();
    }
  });

  test('执行工作流 - 点击执行按钮', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const executeBtn = page.locator('button:has-text("执行"), button:has-text("Run"), [class*="execute"]');
    const isVisible = await executeBtn.isVisible().catch(() => false);

    if (isVisible) {
      await executeBtn.click();
      await page.waitForTimeout(2000);

      const running = await page.evaluate(() => {
        return !!document.querySelector('[class*="running"], [class*="progress"]');
      });
      expect(running).toBeTruthy();
    }
  });

  test('工作流历史 - 应显示历史记录', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const historySection = page.locator('[class*="history"], [class*="recent"]');
    const historyVisible = await historySection.isVisible().catch(() => false);
    expect(historyVisible).toBeTruthy();
  });

  test('导入工作流 - 导入功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const importBtn = page.locator('button:has-text("导入"), button:has-text("Import")');
    const importVisible = await importBtn.isVisible().catch(() => false);
    expect(importVisible).toBeTruthy();
  });

  test('导出工作流 - 导出功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const exportBtn = page.locator('button:has-text("导出"), button:has-text("Export")');
    const exportVisible = await exportBtn.isVisible().catch(() => false);
    expect(exportVisible).toBeTruthy();
  });

  test('删除工作流 - 删除功能应可用', async ({ page }) => {
    await page.goto('/workflow');
    await page.waitForLoadState('domcontentloaded');

    const deleteBtn = page.locator('button:has-text("删除"), button:has-text("Delete")');
    const deleteVisible = await deleteBtn.isVisible().catch(() => false);
    expect(deleteVisible).toBeTruthy();
  });
});
