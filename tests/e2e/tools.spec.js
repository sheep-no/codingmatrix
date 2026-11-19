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

    const toolkitBtn = page.locator('#toolkit');
    await expect(toolkitBtn).toBeVisible();

    await toolkitBtn.click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();
    await expect(toolkitBtn).toHaveAttribute('aria-expanded', 'true');

    await toolkitBtn.click();
    await expect(page.locator('#toolkit-menu')).not.toBeVisible();
    await expect(toolkitBtn).toHaveAttribute('aria-expanded', 'false');
  });

  test('工具面板打开/关闭测试 - 工具面板应包含工具项', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.locator('#toolkit').click();

    const menu = page.locator('#toolkit-menu');
    await expect(menu).toBeVisible();

    // 未登录态下的真实菜单条目
    for (const label of ['项目', '能力', '文档', '设置', 'Docker 配置', 'Nginx 配置', 'PPT 生成', 'AI 绘画']) {
      await expect(menu.locator('.toolkit-item', { hasText: label }).first()).toBeVisible();
    }
  });

  test('快捷键测试 - 键盘快捷键应触发对应操作', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.getByRole('textbox', { name: '消息输入框' });
    await expect(textarea).not.toBeFocused();

    await page.keyboard.press('Control+k');

    // mod+k 的契约是聚焦首页消息输入框
    await expect(textarea).toBeFocused();
  });

  test('快捷键测试 - Escape 键应关闭模态框', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.locator('#toolkit').click();
    await expect(page.locator('#toolkit-menu')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.locator('#toolkit-menu')).not.toBeVisible();
  });

  test('拖拽上传测试 - 拖拽区域应存在', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // 首页的附件入口由上传按钮 + 隐藏 file input 组成
    await expect(page.getByRole('button', { name: '上传文件或图片' })).toBeVisible();
    await expect(page.locator('.hidden-file-input[type="file"]')).toHaveCount(1);
  });

  test('拖拽上传测试 - 文件上传 input 应存在', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const fileInput = page.locator('.hidden-file-input[type="file"]');
    await expect(fileInput).toHaveAttribute('multiple', '');

    // 点击上传按钮应弹出文件选择器
    const chooserPromise = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: '上传文件或图片' }).click();
    const chooser = await chooserPromise;
    expect(chooser).toBeTruthy();
  });

  test('工具面板测试 - 项目生成工具应可打开', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    await page.locator('#toolkit').click();
    await page.locator('#toolkit-menu .toolkit-item', { hasText: '项目' }).first().click();

    // 已登录（beforeEach 完成 API 登录）时「项目」直接进入 Agent 工作区
    await expect(page).toHaveURL(/\/agent$/);
    await expect(page.locator('.agent-page')).toBeVisible();
  });
});
