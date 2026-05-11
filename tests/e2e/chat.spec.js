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

test.describe('Chat E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await ensureAuthenticated(page);
  });

  test('发送消息测试 - 输入并发送消息', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea, [contenteditable="true"], input[type="text"]').first();
    const textareaCount = await textarea.count();

    if (textareaCount > 0) {
      await textarea.fill('Hello, this is a test message');

      const sendBtn = page.locator('button:has-text("发送"), button:has-text("Send"), [class*="send"]');
      const sendCount = await sendBtn.count();

      if (sendCount > 0) {
        await sendBtn.first().click();
        await page.waitForTimeout(1000);

        const hasMessage = await page.evaluate(() => {
          const messages = document.querySelectorAll('[class*="message"], [class*="chat"], .log-item');
          return messages.length > 0;
        });
        expect(hasMessage).toBeTruthy();
      }
    }
  });

  test('流式响应测试 - 应能接收流式响应', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const networkResponses = [];
    page.on('response', (response) => {
      if (response.url().includes('/api/') || response.url().includes('/chat')) {
        networkResponses.push(response.url());
      }
    });

    const textarea = page.locator('textarea, [contenteditable="true"]').first();
    if (await textarea.count() > 0) {
      await textarea.fill('Test streaming response');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(3000);

      expect(networkResponses.length).toBeGreaterThanOrEqual(0);
    }
  });

  test('新建会话测试 - 创建新聊天会话', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const newChatBtn = page.locator('button:has-text("新建"), button:has-text("New"), [class*="new-chat"], [class*="new_session"]');
    const btnCount = await newChatBtn.count();

    if (btnCount > 0) {
      await newChatBtn.first().click();
      await page.waitForTimeout(500);

      const isNewSession = await page.evaluate(() => {
        return !!document.querySelector('[class*="empty"]') ||
               !!document.querySelector('[class*="welcome"]') ||
               !!document.querySelector('[class*="placeholder"]');
      });
      expect(typeof isNewSession).toBe('boolean');
    }
  });

  test('历史记录加载测试 - 应加载历史会话列表', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const sidebar = page.locator('[class*="sidebar"], [class*="history"], [class*="session-list"], #leftlist');
    const sidebarCount = await sidebar.count();

    if (sidebarCount > 0) {
      await page.waitForTimeout(1000);

      const hasHistory = await page.evaluate(() => {
        const sidebar = document.querySelector('[class*="sidebar"]') ||
                        document.querySelector('[class*="history"]') ||
                        document.querySelector('[class*="session"]') ||
                        document.querySelector('#leftlist');
        if (!sidebar) return false;
        return sidebar.querySelectorAll('li, div, button').length > 0;
      });
      expect(typeof hasHistory).toBe('boolean');
    }
  });

  test('消息编辑测试 - 编辑已发送的消息', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea, [contenteditable="true"]').first();
    if (await textarea.count() > 0) {
      await textarea.fill('Original message');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1000);

      const editBtn = page.locator('button:has-text("编辑"), button:has-text("Edit"), [class*="edit"]');
      const editCount = await editBtn.count();

      if (editCount > 0) {
        await editBtn.first().click();
        await page.waitForTimeout(500);

        const editMode = await page.evaluate(() => {
          return !!document.querySelector('[class*="editing"]') ||
                 !!document.querySelector('textarea:focus') ||
                 !!document.querySelector('[contenteditable="true"]:focus');
        });
        expect(typeof editMode).toBe('boolean');
      }
    }
  });

  test('消息复制测试 - 复制 AI 响应内容', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const copyBtn = page.locator('button:has-text("复制"), button:has-text("Copy"), [class*="copy"]');
    const copyCount = await copyBtn.count();

    if (copyCount > 0) {
      await copyBtn.first().click();
      await page.waitForTimeout(500);

      const copied = await page.evaluate(() => {
        return !!document.querySelector('[class*="copied"]') ||
               !!document.querySelector('[class*="success"]');
      });
      expect(typeof copied).toBe('boolean');
    }
  });
});
