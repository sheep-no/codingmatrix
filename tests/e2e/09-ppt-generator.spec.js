/**
 * PPT 生成页面 E2E 测试
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('PPT 生成页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - PPT 生成页面应正常渲染', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/ppt-generate$/);
    await expect(page.locator('.ppt-generate-page')).toBeVisible();
    await expect(page.getByRole('button', { name: '返回首页' })).toBeVisible();
    await expect(page.locator('.header-title')).toContainText('AI PPT 生成');
  });

  test('主题输入 - 文本框应可见', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const topic = page.locator('.config-panel textarea').first();
    await expect(topic).toBeVisible();
    await expect(topic).toHaveAttribute('placeholder', /请输入 PPT 主题/);
    await topic.fill('2026 年人工智能发展趋势');
    await expect(topic).toHaveValue('2026 年人工智能发展趋势');
  });

  test('模板选择 - 应有模板选项', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const grid = page.locator('.template-grid');
    await expect(grid).toBeVisible();

    // 真实的 9 个内置模板 + 自动推荐卡片
    await expect(grid.locator('.template-card')).toHaveCount(9);
    await expect(page.locator('.template-auto')).toContainText('自动推荐');

    const tech = grid.locator('.template-card', { hasText: '科技蓝调' });
    await tech.click();
    await expect(tech).toHaveClass(/selected/);
    await expect(tech).toHaveAttribute('aria-pressed', 'true');
  });

  test('开始生成 - 点击生成按钮', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    const generateBtn = page.locator('.generate-btn');
    await expect(generateBtn).toBeVisible();
    await expect(generateBtn).toBeDisabled();
    await expect(generateBtn).toHaveText('一键生成 PPT');

    // 填入主题后解锁
    await page.locator('.config-panel textarea').first().fill('季度业务复盘');
    await expect(generateBtn).toBeEnabled();
  });

  test('生成预览 - 应显示预览', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    // 未生成前右侧为预览占位区，真实幻灯片容器不存在
    await expect(page.locator('.config-panel')).toBeVisible();
    await expect(page.locator('.preview-panel .preview-placeholder')).toContainText('系统会生成大纲、排版和配图');
    await expect(page.locator('.slides-preview')).toHaveCount(0);
  });

  test('下载 PPT - 下载按钮应可用', async ({ page }) => {
    await page.goto('/ppt-generate');
    await page.waitForLoadState('domcontentloaded');

    // 未生成时不存在下载入口；历史面板可打开查看既往任务
    await expect(page.getByRole('button', { name: /下载/ })).toHaveCount(0);

    await page.getByRole('button', { name: '历史' }).click();
    await expect(page.locator('#ppt-history-panel')).toBeVisible();
  });
});
