/**
 * PPT 生成页面 E2E 测试
 *
 * 覆盖页面配置与大纲交互；真实生成 PPTX 依赖模型 Key，
 * 由 ppt-generation-acceptance.spec.js 在具备 Key 的环境验证。
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

const TOPIC_PLACEHOLDER = '请输入 PPT 主题，例如：帮我做一个关于 2026 年人工智能发展趋势的技术汇报';

test.describe('PPT 生成', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/ppt-generate', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.ppt-generate-page')).toBeVisible({ timeout: 30000 });
  });

  test('打开 PPT 生成', async ({ page }) => {
    await expect(page.getByPlaceholder(TOPIC_PLACEHOLDER)).toBeVisible();
  });

  test('输入主题', async ({ page }) => {
    const topic = page.getByPlaceholder(TOPIC_PLACEHOLDER);
    await topic.fill('人工智能发展');
    await expect(topic).toHaveValue('人工智能发展');
  });

  test('选择模板', async ({ page }) => {
    // 等待后端模板注册表加载完成（“产品路演”只存在于注册表，不在内置兜底列表），
    // 避免加载完成后列表重排把点击落到错误的卡片上
    await expect(page.locator('.template-name', { hasText: '产品路演' })).toBeVisible({ timeout: 15000 });
    // 用模板名精确定位：卡片可访问名称还包含场景描述，“商务汇报”会命中多张卡片
    const template = page.locator('.template-card').filter({
      has: page.locator('.template-name', { hasText: /^商务汇报$/ })
    });
    await expect(template).toBeVisible();
    await template.click();
    await expect(template).toHaveAttribute('aria-pressed', 'true');
  });

  test('选择页数', async ({ page }) => {
    const slideCount = page.locator('.option-select').first();
    await expect(slideCount).toBeVisible();
    const option = await slideCount.locator('option').nth(1).getAttribute('value');
    await slideCount.selectOption(option);
    await expect(slideCount).toHaveValue(option);
  });

  test('空主题时生成按钮禁用，填写后启用', async ({ page }) => {
    const generate = page.locator('.generate-btn');
    await expect(generate).toBeDisabled();
    await page.getByPlaceholder(TOPIC_PLACEHOLDER).fill('AI 发展');
    await expect(generate).toBeEnabled();
  });

  test('打开生成历史面板', async ({ page }) => {
    // 按钮可访问名称来自可见文本“历史”，title 不参与命名
    await page.getByRole('button', { name: '历史', exact: true }).click();
    await expect(page.locator('#ppt-history-panel')).toBeVisible();
  });
});
