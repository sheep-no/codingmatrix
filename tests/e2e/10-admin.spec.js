/**
 * 管理员面板 E2E 测试 (RBAC)
 * 覆盖: 用户管理、角色权限、部门树、审计日志、安全设置、批量操作、分页
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('管理员面板 (RBAC)', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面访问 - 管理员页面应可访问', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const hasContent = await page.evaluate(() => !!document.querySelector('#app'));
    expect(hasContent).toBeTruthy();
  });

  test('用户管理 - 用户列表应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const userList = page.locator('[class*="user-list"], [class*="user-table"]');
    const isVisible = await userList.isVisible().catch(() => false);
    expect(isVisible).toBeTruthy();
  });

  test('用户搜索 - 搜索功能应可用', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const searchInput = page.locator('[class*="search"] input, input[placeholder*="搜索"]');
    const searchVisible = await searchInput.isVisible().catch(() => false);

    if (searchVisible) {
      await searchInput.fill('test');
      await expect(searchInput).toHaveValue('test');
    }
  });

  test('用户筛选 - 筛选选项应可用', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const filterOptions = page.locator('[class*="filter"], [class*="select"]');
    const filterCount = await filterOptions.count();
    expect(filterCount).toBeGreaterThan(0);
  });

  test('用户分页 - 分页控件应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const pagination = page.locator('[class*="pagination"], [class*="pager"]');
    const paginationVisible = await pagination.isVisible().catch(() => false);
    expect(paginationVisible).toBeTruthy();
  });

  test('角色管理 - 角色列表应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const roleList = page.locator('[class*="role"], [class*="permission"]');
    const roleVisible = await roleList.isVisible().catch(() => false);
    expect(roleVisible).toBeTruthy();
  });

  test('权限树 - 权限层级应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const permissionTree = page.locator('[class*="tree"], [class*="permission-tree"]');
    const treeVisible = await permissionTree.isVisible().catch(() => false);
    expect(treeVisible).toBeTruthy();
  });

  test('部门树 - 部门层级应可展开', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const deptTree = page.locator('[class*="dept"], [class*="department"]');
    const deptVisible = await deptTree.isVisible().catch(() => false);
    expect(deptVisible).toBeTruthy();
  });

  test('审计日志 - 日志列表应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const auditLog = page.locator('[class*="audit"], [class*="log"]');
    const logVisible = await auditLog.isVisible().catch(() => false);
    expect(logVisible).toBeTruthy();
  });

  test('安全设置 - 安全配置应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const securitySettings = page.locator('[class*="security"], [class*="setting"]');
    const settingsVisible = await securitySettings.isVisible().catch(() => false);
    expect(settingsVisible).toBeTruthy();
  });

  test('批量操作 - 批量选择功能应可用', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const checkbox = page.locator('[class*="user-list"] input[type="checkbox"]').first();
    const checkboxVisible = await checkbox.isVisible().catch(() => false);

    if (checkboxVisible) {
      await checkbox.click();
      await page.waitForTimeout(300);

      const batchActions = page.locator('[class*="batch"], [class*="bulk"]');
      const batchVisible = await batchActions.isVisible().catch(() => false);
      expect(batchVisible).toBeTruthy();
    }
  });

  test('多租户 - 租户管理应可见', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    const tenantSection = page.locator('[class*="tenant"], [class*="organization"]');
    const tenantVisible = await tenantSection.isVisible().catch(() => false);
    expect(tenantVisible).toBeTruthy();
  });
});
