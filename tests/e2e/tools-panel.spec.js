/**
 * 工具集面板 E2E 测试
 * 
 * 测试工具集功能：
 * - 工具集菜单展开
 * - 工具列表完整性
 * - 工具切换
 * - 权限控制
 * - 搜索功能
 */
import { test, expect } from '@playwright/test';

test.describe('工具集面板', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('工具集按钮可见', async ({ page }) => {
    await expect(page.locator('#toolkit')).toBeVisible();
    await expect(page.locator('#toolkit')).toContainText('工具集');
  });

  test('展开工具集菜单', async ({ page }) => {
    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();
  });

  test('工具列表完整性', async ({ page }) => {
    await page.locator('#toolkit').click();
    
    const expectedTools = [
      '图表编辑器',
      'Nginx 配置',
      'Docker 配置',
      '系统检测',
      'AI 虚拟姬',
      'PPT 生成',
      'AI 绘画',
      '任务队列',
      'AI 云助手',
      '系统监控',
      'AI 项目生成',
      '临时工作流',
      '搜索历史'
    ];
    
    for (const tool of expectedTools) {
      await expect(page.locator(`text=${tool}`)).toBeVisible();
    }
  });

  test('管理员工具权限控制', async ({ page }) => {
    await page.locator('#toolkit').click();
    
    const adminTool = page.locator('text=管理员面板');
    const isVisible = await adminTool.isVisible().catch(() => false);
    
    if (isVisible) {
      await expect(adminTool).toHaveClass(/admin-tool/);
    }
  });

  test('工具项点击', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=图表编辑器').click();
    
    await expect(page.locator('#toolkit-menu')).not.toBeVisible();
  });

  test('搜索框显示', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=搜索历史').click();
    
    await expect(page.locator('.search-box')).toBeVisible();
    await expect(page.locator('.search-input')).toBeFocused();
  });

  test('搜索功能', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=搜索历史').click();
    
    await page.locator('.search-input').fill('测试');
    await page.locator('.search-btn').click();
    
    await expect(page.locator('.history-item')).toHaveCount(0);
  });

  test('搜索清除', async ({ page }) => {
    await page.locator('#toolkit').click();
    await page.locator('text=搜索历史').click();
    
    await page.locator('.search-input').fill('测试');
    await page.locator('.clear-btn').click();
    
    await expect(page.locator('.search-input')).toHaveValue('');
  });

  test('点击外部关闭菜单', async ({ page }) => {
    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();
    
    await page.locator('main').click();
    await expect(page.locator('#toolkit-menu')).not.toBeVisible();
  });

  test('侧边栏折叠', async ({ page }) => {
    await page.locator('#collapse-btn').click();
    
    await expect(page.locator('#leftlist')).toHaveClass(/collapsed/);
  });

  test('新建会话', async ({ page }) => {
    await page.locator('#newSpeak').click();
    
    await expect(page.locator('.chat-messages')).toBeEmpty();
  });
});
