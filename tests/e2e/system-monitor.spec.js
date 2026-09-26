/**
 * 系统监控 E2E 测试
 *
 * 系统监控已从首页工具集迁入管理面板（/admin 默认菜单「系统监控」）。
 * 覆盖：资源概览卡片、网络状态、手动刷新、ECharts 图表渲染。
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

const PERCENT = /^\d{1,3}(\.\d+)?%$/;

test.describe('系统监控', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/admin', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.admin-panel')).toBeVisible({ timeout: 25000 });
    await expect(page.locator('.monitor-section')).toBeVisible({ timeout: 25000 });
  });

  test('打开系统监控', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '系统监控仪表板' })).toBeVisible();
    await expect(page.locator('.status-label')).toHaveText('系统在线');
  });

  test('CPU 使用率显示', async ({ page }) => {
    const card = page.locator('.cpu-card');
    await expect(card).toBeVisible();
    await expect(card.locator('h3')).toHaveText('CPU 使用率');
    await expect(card.locator('.card-value')).toHaveText(PERCENT, { timeout: 15000 });
  });

  test('内存使用率显示', async ({ page }) => {
    const card = page.locator('.memory-card');
    await expect(card).toBeVisible();
    await expect(card.locator('h3')).toHaveText('内存使用');
    await expect(card.locator('.card-value')).toHaveText(PERCENT, { timeout: 15000 });
  });

  test('磁盘使用率显示', async ({ page }) => {
    const card = page.locator('.disk-card');
    await expect(card).toBeVisible();
    await expect(card.locator('h3')).toHaveText('磁盘使用');
    await expect(card.locator('.card-value')).toHaveText(PERCENT, { timeout: 15000 });
  });

  test('网络状态显示', async ({ page }) => {
    const card = page.locator('.network-card');
    await expect(card).toBeVisible();
    await expect(card.locator('.network-status')).toHaveText('网络正常');
    await expect(card.locator('.metric-label')).toHaveText(['上传', '下载']);
  });

  test('手动刷新出现更新时间', async ({ page }) => {
    await page.locator('.monitor-section .action-btn.primary').click();
    await expect(page.locator('.status-time')).toContainText('最后更新：', { timeout: 15000 });
  });

  test('图表渲染', async ({ page }) => {
    const panels = page.locator('.charts-grid .chart-panel');
    await expect(panels).toHaveCount(4);
    await expect(panels.locator('canvas').first()).toBeVisible({ timeout: 15000 });
    await expect(panels.locator('canvas')).toHaveCount(4);
  });
});
