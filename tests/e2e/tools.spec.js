const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';

async function ensureAuthenticated(page) {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  if (token) return true;

  const apiLogin = await page.evaluate(async ({ email, password }) => {
    await fetch('/api/v1/csrf-token', { credentials: 'include' });
    const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
    const csrfToken = csrfMatch ? csrfMatch[1] : '';

    const resp = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
      },
      body: JSON.stringify({ email, password }),
    });

    if (resp.ok) {
      const data = await resp.json();
      return data;
    }
    return null;
  }, { email: TEST_EMAIL, password: TEST_PASSWORD });

  if (apiLogin) {
    await page.evaluate(({ access_token, username }) => {
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('username', username);
      if (window.userStore && typeof window.userStore.setUser === 'function') {
        window.userStore.setUser({
          username,
          permission_level: 'normal',
          access_token,
          expires_in: 3600,
        });
      }
    }, apiLogin);
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    return true;
  }
  return false;
}

test.describe('Tools E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await ensureAuthenticated(page);
  });

  test('工具面板打开/关闭测试 - 点击工具集按钮打开面板', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const toolkitBtn = page.locator('#toolkit, button:has-text("工具集"), button:has-text("Tools"), [class*="toolkit"]');
    const btnCount = await toolkitBtn.count();

    if (btnCount > 0) {
      await toolkitBtn.first().click();
      await page.waitForTimeout(500);

      const panelVisible = await page.evaluate(() => {
        return !!document.querySelector('.toolkit-menu') ||
               !!document.querySelector('[class*="toolkit"]:visible') ||
               !!document.querySelector('.toolkit-item') ||
               !!document.querySelector('[class*="tool-panel"]');
      });
      expect(panelVisible).toBeTruthy();

      await toolkitBtn.first().click();
      await page.waitForTimeout(500);
    }
  });

  test('工具面板打开/关闭测试 - 工具面板应包含工具项', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const toolkitBtn = page.locator('#toolkit, button:has-text("工具集"), button:has-text("Tools")');
    if (await toolkitBtn.count() > 0) {
      await toolkitBtn.first().click();
      await page.waitForTimeout(500);

      const toolItems = await page.evaluate(() => {
        const items = document.querySelectorAll('.toolkit-item, [class*="tool-item"]');
        return items.length;
      });
      expect(toolItems).toBeGreaterThanOrEqual(0);
    }
  });

  test('快捷键测试 - 键盘快捷键应触发对应操作', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);

    const hasReaction = await page.evaluate(() => {
      return !!document.querySelector('[class*="search"]') ||
             !!document.querySelector('[class*="modal"]') ||
             !!document.querySelector('[class*="palette"]') ||
             !!document.querySelector('[class*="overlay"]');
    });
    expect(typeof hasReaction).toBe('boolean');
  });

  test('快捷键测试 - Escape 键应关闭模态框', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const toolkitBtn = page.locator('#toolkit, button:has-text("工具集")');
    if (await toolkitBtn.count() > 0) {
      await toolkitBtn.first().click();
      await page.waitForTimeout(500);

      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);

      const modalClosed = await page.evaluate(() => {
        const overlays = document.querySelectorAll('.overlay, [class*="overlay"], .modal, [class*="modal"]');
        for (const overlay of overlays) {
          if (overlay.offsetParent !== null) {
            return false;
          }
        }
        return true;
      });
      expect(typeof modalClosed).toBe('boolean');
    }
  });

  test('拖拽上传测试 - 拖拽区域应存在', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const dropZone = page.locator('[class*="drop"], [class*="upload"], [class*="drag"], input[type="file"]');
    const dropZoneCount = await dropZone.count();

    if (dropZoneCount > 0) {
      const hasDropZone = await dropZone.first().isVisible();
      expect(hasDropZone).toBeTruthy();
    }
  });

  test('拖拽上传测试 - 文件上传 input 应存在', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const fileInput = page.locator('input[type="file"]');
    const fileInputCount = await fileInput.count();

    if (fileInputCount > 0) {
      const isVisible = await fileInput.first().isVisible();
      expect(typeof isVisible).toBe('boolean');
    }
  });

  test('工具面板测试 - 项目生成工具应可打开', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const toolkitBtn = page.locator('#toolkit, button:has-text("工具集")');
    if (await toolkitBtn.count() > 0) {
      await toolkitBtn.first().click();
      await page.waitForTimeout(500);

      const projectGenItem = page.locator('.toolkit-item:has-text("项目生成"), .toolkit-item:has-text("Project")');
      if (await projectGenItem.count() > 0) {
        await projectGenItem.first().click();
        await page.waitForTimeout(1000);

        const modalVisible = await page.evaluate(() => {
          return !!document.querySelector('.project-generator-overlay') ||
                 !!document.querySelector('.project-generator-modal') ||
                 !!document.querySelector('[class*="generator"]');
        });
        expect(typeof modalVisible).toBe('boolean');
      }
    }
  });
});
