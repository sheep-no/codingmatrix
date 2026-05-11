/**
 * 工作流 E2E 测试
 * 
 * 测试完整的工作流功能：
 * - 工作流创建
 * - 节点添加与连接
 * - 工作流执行
 * - SSE 实时进度
 * - 历史记录
 * - 导入导出
 */
import { test, expect } from '@playwright/test';

test.describe('工作流功能', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('打开工作流', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=临时工作流').click();
    
    await expect(page.locator('.workflow-container')).toBeVisible();
  });

  test('添加节点', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=临时工作流').click();
    
    await page.locator('.add-node-btn').click();
    await expect(page.locator('.workflow-node')).toBeVisible();
  });

  test('节点类型选择', async ({ page }) => {
    await page.locator('.add-node-btn').click();
    await page.locator('.node-type-select').click();
    
    await expect(page.locator('.node-type-option')).toHaveCount(4);
  });

  test('连接节点', async ({ page }) => {
    await page.locator('.add-node-btn').click();
    await page.locator('.add-node-btn').click();
    
    const connection = page.locator('.node-connection');
    await expect(connection).toBeVisible();
  });

  test('执行工作流', async ({ page }) => {
    await page.locator('.execute-btn').click();
    
    await expect(page.locator('.workflow-progress')).toBeVisible();
  });

  test('SSE 实时进度', async ({ page }) => {
    await page.locator('.execute-btn').click();
    
    await expect(page.locator('.sse-status')).toBeVisible();
    await expect(page.locator('.sse-progress-bar')).toBeVisible();
  });

  test('工作流历史', async ({ page }) => {
    await page.locator('.history-btn').click();
    
    await expect(page.locator('.history-list')).toBeVisible();
  });

  test('删除工作流', async ({ page }) => {
    await page.locator('.delete-btn').click();
    
    await expect(page.locator('.confirm-dialog')).toBeVisible();
    await page.locator('.confirm-delete-btn').click();
    
    await expect(page.locator('.workflow-node')).not.toBeVisible();
  });

  test('导入工作流', async ({ page }) => {
    await page.locator('.import-btn').click();
    
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'workflow.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({ nodes: [], edges: [] }))
    });
    
    await expect(page.locator('.workflow-node')).toBeVisible();
  });

  test('导出工作流', async ({ page }) => {
    await page.locator('.export-btn').click();
    
    await expect(page.locator('.export-dialog')).toBeVisible();
  });

  test('分页控制', async ({ page }) => {
    await expect(page.locator('.pagination')).toBeVisible();
    await expect(page.locator('.page-prev')).toBeVisible();
    await expect(page.locator('.page-next')).toBeVisible();
  });
});
