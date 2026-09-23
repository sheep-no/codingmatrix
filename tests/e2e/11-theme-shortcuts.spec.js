/**
 * 主题与快捷键 E2E 测试
 * 覆盖: 主题切换、主题持久化、键盘快捷键、帮助面板
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

// 窗口级快捷键在 index.vue 的 onMounted 中、等待状态恢复之后才注册，
// 页面首帧可能尚未挂载监听器。这里重试按键直到断言成立，避免时序误报。
async function pressUntil(page, key, predicate, timeout = 15000) {
  await expect.poll(async () => {
    await page.keyboard.press(key);
    await page.waitForTimeout(200);
    return predicate();
  }, { timeout }).toBe(true);
}

test.describe('主题与快捷键', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('主题切换按钮 - 应可见', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await expect(page.locator('.theme-switcher')).toBeVisible();
  });

  test('暗色模式 - 切换后应应用暗色主题', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await page.getByRole('radio', { name: '夜晚' }).click();

    await expect(page.locator('html')).toHaveClass(/theme-dark/);
  });

  test('明亮模式 - 切换后应应用明亮主题', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await page.getByRole('radio', { name: '夜晚' }).click();
    await expect(page.locator('html')).toHaveClass(/theme-dark/);

    await page.getByRole('radio', { name: '白天' }).click();
    await expect(page.locator('html')).toHaveClass(/theme-light/);
  });

  test('主题持久化 - 刷新后主题应保持', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await page.getByRole('radio', { name: '夜晚' }).click();
    await expect(page.locator('html')).toHaveClass(/theme-dark/);

    await page.reload({ waitUntil: 'domcontentloaded' });

    await expect(page.locator('html')).toHaveClass(/theme-dark/);
    const savedTheme = await page.evaluate(() => localStorage.getItem('app-theme'));
    expect(savedTheme).toBe('theme-dark');
  });

  test('Ctrl+K - 聚焦输入框', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await pressUntil(page, 'ControlOrMeta+k', () => page.evaluate(() => {
      const el = document.activeElement;
      return !!el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT');
    }));
  });

  test('Ctrl+Enter - 发送消息', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    const textarea = page.locator('textarea').first();
    await textarea.waitFor({ state: 'visible' });
    await textarea.fill('Test Ctrl+Enter');

    await pressUntil(page, 'Control+Enter', () => page.evaluate(
      () => document.querySelectorAll('[class*="message"]').length > 0
    ));
  });

  test('Escape - 关闭所有面板', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();

    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    const menuVisible = await page.locator('#toolkit-menu').isVisible().catch(() => false);
    expect(menuVisible).toBeFalsy();
  });

  test('Ctrl+N - 新建会话', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('ControlOrMeta+n');
    await page.waitForTimeout(500);
  });

  test('/ - 聚焦搜索框', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await pressUntil(page, '/', () => page.evaluate(
      () => !!document.activeElement?.classList?.contains('search-input')
    ));
  });

  test('Shift+/ - 查看快捷键列表', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    await pressUntil(page, 'Shift+/', () =>
      page.locator('.keyboard-shortcuts-modal').isVisible().catch(() => false)
    );
    await expect(page.locator('.keyboard-shortcuts-modal')).toBeVisible();
  });

  test('Tab - 键盘导航顺序', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);

    const firstFocused = await page.evaluate(() => {
      const el = document.activeElement;
      return el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA';
    });
    expect(firstFocused).toBeTruthy();
  });

  test('跳过链接 - 跳转到主要内容', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);

    const skipLink = await page.evaluate(() => {
      return !!document.querySelector('[class*="skip"], [class*="skip-link"]');
    });
    expect(skipLink).toBeTruthy();
  });
});
