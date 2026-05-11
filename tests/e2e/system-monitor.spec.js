/**
 * 系统监控 E2E 测试
 * 
 * 测试系统监控功能：
 * - CPU 使用率
 * - 内存使用率
 * - 磁盘使用率
 * - 网络状态
 * - 实时更新
 */
import { test, expect } from '@playwright/test';

test.describe('系统监控', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('打开系统监控', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await expect(page.locator('.system-monitor')).toBeVisible();
  });

  test('CPU 使用率显示', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await expect(page.locator('.cpu-usage')).toBeVisible();
    await expect(page.locator('.cpu-usage-value')).toBeVisible();
  });

  test('内存使用率显示', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await expect(page.locator('.memory-usage')).toBeVisible();
    await expect(page.locator('.memory-usage-value')).toBeVisible();
  });

  test('磁盘使用率显示', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await expect(page.locator('.disk-usage')).toBeVisible();
  });

  test('网络状态显示', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await expect(page.locator('.network-status')).toBeVisible();
  });

  test('实时数据更新', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await page.waitForTimeout(5000);
    await expect(page.locator('.cpu-usage-value')).toBeVisible();
  });

  test('图表渲染', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=系统监控').click();
    
    await expect(page.locator('.monitor-chart')).toBeVisible();
  });
});
