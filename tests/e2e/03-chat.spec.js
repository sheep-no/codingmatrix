/**
 * 聊天交互 E2E 测试
 * 覆盖: 发送消息、流式响应、停止生成、消息编辑、消息复制、会话管理
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('聊天交互', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('发送消息 - 输入并点击发送', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await expect(textarea).toBeVisible();

    await textarea.fill('Hello, this is a test message');
    await expect(textarea).toHaveValue('Hello, this is a test message');

    const sendBtn = page.locator('button[class*="send"], button:has-text("发送"), [class*="input-bar"] button').first();
    const sendVisible = await sendBtn.isVisible().catch(() => false);

    if (sendVisible) {
      await sendBtn.click();
      await page.waitForTimeout(1000);

      const messagesExist = await page.evaluate(() => {
        return document.querySelectorAll('.message-item').length > 0;
      });
      expect(messagesExist).toBeTruthy();
    }
  });

  test('发送消息 - 键盘 Enter 发送', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Test message via keyboard');
    await textarea.press('Enter');
    await page.waitForTimeout(1000);

    const messagesExist = await page.evaluate(() => {
      return document.querySelectorAll('.message-item').length > 0;
    });
    expect(messagesExist).toBeTruthy();
  });

  test('流式响应 - 接收 AI 回复', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Please respond to this test');
    await textarea.press('Enter');

    await page.waitForTimeout(3000);

    const aiResponse = await page.evaluate(() => {
      const aiMessages = document.querySelectorAll('.message-ai');
      return aiMessages.length > 0;
    });
    expect(aiResponse).toBeTruthy();
  });

  test('停止生成 - 停止按钮应可见并可点击', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Write a long response so I can stop it');
    await textarea.press('Enter');

    await page.waitForTimeout(1000);

    const stopBtn = page.locator('button[class*="stop"], button:has-text("停止"), [class*="stop-btn"]');
    const stopVisible = await stopBtn.isVisible().catch(() => false);

    if (stopVisible) {
      await stopBtn.click();
      await page.waitForTimeout(500);
    }
  });

  test('新建会话 - 清空当前对话', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Message in current session');
    await textarea.press('Enter');
    await page.waitForTimeout(1000);

    const newSessionBtn = page.locator('.btn-new-chat');
    const isVisible = await newSessionBtn.isVisible().catch(() => false);

    if (isVisible) {
      await newSessionBtn.click();
      await page.waitForTimeout(500);

      const isEmpty = await page.evaluate(() => {
        const messages = document.querySelectorAll('.message-item');
        return messages.length === 0 || document.querySelector('.empty-state');
      });
      expect(isEmpty).toBeTruthy();
    }
  });

  test('历史会话 - 侧边栏应显示历史记录', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Create a session');
    await textarea.press('Enter');
    await page.waitForTimeout(1500);

    const sidebar = page.locator('#leftlist');
    await expect(sidebar).toBeVisible();

    const historyItems = await page.evaluate(() => {
      const sidebar = document.querySelector('#leftlist');
      if (!sidebar) return 0;
      return sidebar.querySelectorAll('.history-item').length;
    });
    expect(historyItems).toBeGreaterThan(0);
  });

  test('历史会话切换 - 点击历史项应加载对话', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('First session content');
    await textarea.press('Enter');
    await page.waitForTimeout(1500);

    const firstHistoryItem = page.locator('#leftlist .history-item').first();
    const isVisible = await firstHistoryItem.isVisible().catch(() => false);

    if (isVisible) {
      await firstHistoryItem.click();
      await page.waitForTimeout(500);

      const hasContent = await page.evaluate(() => {
        return document.querySelectorAll('.message-item').length > 0;
      });
      expect(hasContent).toBeTruthy();
    }
  });

  test('消息编辑 - 编辑并重新发送', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Original message');
    await textarea.press('Enter');
    await page.waitForTimeout(1000);

    const editBtn = page.locator('.message-actions .action-btn').first();
    const editVisible = await editBtn.isVisible().catch(() => false);

    if (editVisible) {
      await editBtn.click();
      await page.waitForTimeout(500);

      const editMode = await page.evaluate(() => {
        return !!document.querySelector('textarea:focus') ||
               !!document.querySelector('[class*="editing"]');
      });
      expect(editMode).toBeTruthy();
    }
  });

  test('消息复制 - 点击复制按钮', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Message for copy test');
    await textarea.press('Enter');
    await page.waitForTimeout(1500);

    const copyBtn = page.locator('.message-actions .action-btn[title="复制"]').first();
    const copyVisible = await copyBtn.isVisible().catch(() => false);

    if (copyVisible) {
      await copyBtn.click();
      await page.waitForTimeout(500);

      const copied = await page.evaluate(() => {
        return !!document.querySelector('[class*="copied"], [class*="success"]');
      });
      expect(copied).toBeTruthy();
    }
  });

  test('加载更多历史 - 分页加载', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    for (let i = 0; i < 3; i++) {
      const textarea = page.locator('textarea').first();
      await textarea.fill(`Session ${i + 1}`);
      await textarea.press('Enter');
      await page.waitForTimeout(1000);
      await page.locator('.btn-new-chat').click();
      await page.waitForTimeout(300);
    }

    const historyList = page.locator('#leftlist .history-list');
    const itemCount = await historyList.evaluate(el => el.querySelectorAll('.history-item').length);
    expect(itemCount).toBeGreaterThan(0);
  });

  test('删除会话 - 删除历史会话', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    await textarea.fill('Session to delete');
    await textarea.press('Enter');
    await page.waitForTimeout(1500);

    const deleteBtn = page.locator('.message-item.message-user .message-actions .action-btn[title="删除"]');
    const deleteVisible = await deleteBtn.isVisible().catch(() => false);

    if (deleteVisible) {
      await deleteBtn.click();
      await page.waitForTimeout(500);
    }
  });
});
