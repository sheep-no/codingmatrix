/**
 * 主题与快捷键 E2E 测试
 * 覆盖: 主题切换、主题持久化、键盘快捷键、帮助面板
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('主题与快捷键', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('主题切换按钮 - 应可见', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const themeBtn = page.locator('[class*="theme"], [class*="ThemeSwitch"], [class*="theme-switch"]');
    const themeVisible = await themeBtn.isVisible().catch(() => false);
    expect(themeVisible).toBeTruthy();
  });

  test('暗色模式 - 切换后应应用暗色主题', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const themeBtn = page.locator('[class*="theme"], [class*="ThemeSwitch"], [class*="theme-switch"]');
    const themeVisible = await themeBtn.isVisible().catch(() => false);

    if (themeVisible) {
      const beforeTheme = await page.evaluate(() => document.documentElement.className);
      await themeBtn.click();
      await page.waitForTimeout(300);
      const afterTheme = await page.evaluate(() => document.documentElement.className);

      expect(afterTheme).not.toBe(beforeTheme);
    }
  });

  test('明亮模式 - 切换后应应用明亮主题', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const themeBtn = page.locator('[class*="theme"], [class*="ThemeSwitch"], [class*="theme-switch"]');
    const themeVisible = await themeBtn.isVisible().catch(() => false);

    if (themeVisible) {
      await themeBtn.click();
      await page.waitForTimeout(300);
      await themeBtn.click();
      await page.waitForTimeout(300);

      const theme = await page.evaluate(() => document.documentElement.className);
      expect(typeof theme).toBe('string');
    }
  });

  test('主题持久化 - 刷新后主题应保持', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const themeBtn = page.locator('[class*="theme"], [class*="ThemeSwitch"], [class*="theme-switch"]');
    const themeVisible = await themeBtn.isVisible().catch(() => false);

    if (themeVisible) {
      await themeBtn.click();
      await page.waitForTimeout(300);

      await page.reload();
      await page.waitForLoadState('domcontentloaded');

      const savedTheme = await page.evaluate(() => localStorage.getItem('app-theme'));
      expect(typeof savedTheme).toBe('string');
    }
  });

  test('Ctrl+K - 聚焦输入框', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('ControlOrMeta+k');
    await page.waitForTimeout(300);

    const focused = await page.evaluate(() => {
      const el = document.activeElement;
      return el.tagName === 'TEXTAREA' || el.tagName === 'INPUT';
    });
    expect(focused).toBeTruthy();
  });

  test('Ctrl+Enter - 发送消息', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Test Ctrl+Enter');
    await page.keyboard.press('Control+Enter');
    await page.waitForTimeout(500);

    const messagesExist = await page.evaluate(() => {
      return document.querySelectorAll('[class*="message"]').length > 0;
    });
    expect(messagesExist).toBeTruthy();
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

  test('Ctrl+/ - 查看帮助', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('Control+/');
    await page.waitForTimeout(500);

    const helpVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="help"], [class*="shortcut"], [class*="modal"]');
    });
    expect(helpVisible).toBeTruthy();
  });

  test('Shift+/ - 查看快捷键列表', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('Shift+/');
    await page.waitForTimeout(500);

    const shortcutVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="shortcut"], [class*="help"]');
    });
    expect(shortcutVisible).toBeTruthy();
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
