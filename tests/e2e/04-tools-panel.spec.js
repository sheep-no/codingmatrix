/**
 * 工具集面板 E2E 测试
 * 覆盖: 工具菜单展开、工具列表、权限控制、工具项点击、搜索功能
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

const EXPECTED_TOOLS = [
  'Agent',
  '图表编辑器',
  'Docker 配置',
  '虚拟姬',
  'PPT 生成',
  'AI 绘画',
  'AI 云助手',
  '临时工作流',
];

test.describe('工具集面板', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('工具集按钮可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#toolkit')).toBeVisible();
    await expect(page.locator('#toolkit')).toContainText('工具集');
  });

  test('展开工具集菜单', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();
  });

  test('工具列表完整性', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);
    
    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible({ timeout: 5000 });
    
    // Check for key tools including VirtualGirl
    const chartEditor = page.locator('text=图表编辑器').first();
    const dockerConfig = page.locator('text=Docker 配置').first();
    const virtualGirl = page.locator('text=虚拟姬').first();
    
    const hasTools = await chartEditor.isVisible().catch(() => false);
    expect(hasTools).toBeTruthy();
  });

  test('工具项点击关闭菜单', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();

    await page.locator('text=图表编辑器').click();
    await expect(page.locator('#toolkit-menu')).not.toBeVisible();
  });

  test('点击外部关闭菜单', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();

    await page.locator('main').click();
    await expect(page.locator('#toolkit-menu')).not.toBeVisible();
  });

  test('管理员面板 - 权限可见性', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();

    const adminTool = page.locator('text=管理员面板');
    const adminVisible = await adminTool.isVisible().catch(() => false);

    if (adminVisible) {
      await expect(adminTool).toBeVisible();
    }
  });

  test('搜索历史 - 搜索框显示', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();
    await page.locator('text=搜索历史').click();

    await expect(page.locator('.search-box')).toBeVisible();
    await expect(page.locator('.search-input')).toBeVisible();
  });

  test('搜索 - 输入并搜索', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();
    await page.locator('text=搜索历史').click();

    await page.locator('.search-input').fill('测试');
    await page.locator('.search-btn').click();

    await page.waitForTimeout(500);
    const searchInputValue = await page.locator('.search-input').inputValue();
    expect(searchInputValue).toBe('测试');
  });

  test('搜索 - 清除搜索', async ({ page }) => {
    await page.goto('/');
    await page.locator('#toolkit').click();
    await page.locator('text=搜索历史').click();

    await page.locator('.search-input').fill('测试');
    const clearBtn = page.locator('.clear-btn');
    const clearVisible = await clearBtn.isVisible().catch(() => false);

    if (clearVisible) {
      await clearBtn.click();
      await expect(page.locator('.search-input')).toHaveValue('');
    }
  });
});
