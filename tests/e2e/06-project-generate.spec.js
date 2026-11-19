/**
 * 项目生成页面 E2E 测试
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('项目生成页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - Agent 页面应正常渲染', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/agent$/);
    await expect(page.locator('.agent-page')).toBeVisible();
    await expect(page.getByRole('textbox', { name: '项目需求' })).toBeVisible();
    await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible();
  });

  test('需求输入 - 文本框应可见并可输入', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const input = page.getByRole('textbox', { name: '项目需求' });
    await expect(input).toBeVisible();
    await input.fill('生成一个待办事项应用');
    await expect(input).toHaveValue('生成一个待办事项应用');
  });

  test('技术栈选择 - 应有模板选项', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    // 快速模板已下线，工作区以会话/项目导航 + 文件产物面板承载技术栈信息
    await expect(page.locator('.agent-sidebar[aria-label="会话、项目与文件导航"]')).toBeVisible();
    await expect(page.locator('.agent-file-panel')).toBeVisible();
    await expect(page.locator('.agent-file-panel .empty-title')).toHaveText('项目产物');
  });

  test('开始生成 - 点击生成按钮', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const sendBtn = page.getByRole('button', { name: '发送需求' });
    await expect(sendBtn).toBeDisabled();

    await page.getByRole('textbox', { name: '项目需求' }).fill('生成一个博客系统');
    await expect(sendBtn).toBeEnabled();
  });

  test('文件树展示 - 生成后应显示文件树', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    // 尚未生成时，侧栏与文件面板都应处于空态
    await expect(page.locator('.agent-sidebar')).toBeVisible();
    await expect(page.locator('.agent-file-panel .empty-title')).toHaveText('项目产物');
    await expect(page.locator('.agent-file-panel .file-tree')).toHaveCount(0);
  });

  test('代码预览 - 点击文件应预览内容', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const panel = page.locator('.agent-file-panel');
    await expect(panel.locator('.empty-text')).toContainText('从左侧文件列表选择文件');
    await expect(panel.locator('.code-preview, pre')).toHaveCount(0);
  });

  test('停止生成 - 停止按钮应可见', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/agent$/);
    await expect(page.locator('.agent-page')).toBeVisible();

    // 空闲态展示「发送需求」，生成中才切换为「停止生成」
    await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible();
    await expect(page.getByRole('button', { name: '停止生成' })).toHaveCount(0);
  });

  test('下载项目 - 下载按钮应可见', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/agent$/);

    // 无产物时不存在下载入口，导入项目入口常驻
    await expect(page.getByRole('button', { name: '导入项目' })).toBeVisible();
    await expect(page.getByRole('button', { name: /下载/ })).toHaveCount(0);
  });
});
