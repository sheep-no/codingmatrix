/**
 * 项目生成页面 E2E 测试
 *
 * /project-generate 已收敛到 /agent，这里验证 Agent 工作台的
 * 入口、输入、会话与工作区结构；真实生成依赖外部模型 Key。
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('项目生成流程', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('项目生成入口重定向到 Agent 工作台', async ({ page }) => {
    await page.goto('/project-generate', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/agent/);
    await expect(page.locator('.agent-page')).toBeVisible({ timeout: 30000 });
  });

  test('发送项目需求', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    const prompt = page.locator('[data-testid="agent-prompt-input"]');
    await expect(prompt).toBeVisible({ timeout: 30000 });

    await prompt.fill('创建一个贪吃蛇游戏');
    await expect(prompt).toHaveValue('创建一个贪吃蛇游戏');
    await expect(page.getByRole('button', { name: '发送需求' })).toBeEnabled();
  });

  test('空需求时发送按钮禁用', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: '发送需求' })).toBeDisabled();
  });

  test('工作区初始展示引导空状态', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    const emptyState = page.locator('.agent-workspace .empty-state');
    await expect(emptyState).toBeVisible({ timeout: 30000 });
    await expect(emptyState).toContainText('从一个想法，开始构建');
  });

  test('文件面板展示项目产物空态', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    const filePanel = page.locator('.agent-file-panel');
    await expect(filePanel).toBeVisible({ timeout: 30000 });
    await expect(filePanel).toContainText('项目产物');
  });

  test('新建会话', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.session-list')).toBeVisible({ timeout: 30000 });
    await page.getByRole('button', { name: '新建会话' }).click();
    await expect(page.locator('.session-list')).toBeVisible();
  });

  test('会话切换入口可见', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.agent-sidebar .session-list')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('.agent-sidebar')).toContainText('会话历史');
  });

  test('顶部栏展示 Agent 标题与状态', async ({ page }) => {
    await page.goto('/agent', { waitUntil: 'domcontentloaded' });
    const topbar = page.locator('.agent-topbar');
    await expect(topbar).toContainText('CodingMatrix');
    await expect(topbar.locator('.topbar-status')).toBeVisible();
  });
});
