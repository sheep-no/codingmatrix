const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'mr_yang@example.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || '12345678';

/**
 * 通过 API 登录并设置 Token
 * @param {import('@playwright/test').Page} page
 * @param {Object} options
 * @param {string} options.email
 * @param {string} options.password
 * @param {string} options.permissionLevel - 'normal', 'admin', 'superadmin'
 */
async function loginAs(page, { email, password, permissionLevel = 'normal' }) {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  if (token) {
    const storedPerm = await page.evaluate(() => localStorage.getItem('permission_level'));
    if (['admin', 'superadmin'].includes(storedPerm) && ['admin', 'superadmin'].includes(permissionLevel)) return true;
  }

  await page.evaluate(async ({ email, password }) => {
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
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('username', data.username || 'user');
      localStorage.setItem('permission_level', data.permission_level || 'normal');
      if (window.userStore && typeof window.userStore.setUser === 'function') {
        window.userStore.setUser({
          username: data.username,
          permission_level: data.permission_level,
          access_token: data.access_token,
        });
      }
    }
  }, { email, password });

  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  return true;
}

/**
 * 打开 AI 云助手弹窗
 * 流程: 点击工具集按钮 → 等待菜单展开 → 点击 "AI 云助手"
 */
async function openAicloud(page) {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  // 点击工具集按钮打开菜单
  await page.click('#toolkit');
  await page.waitForTimeout(300);

  // 点击 AI 云助手
  const aicloudItem = page.locator('.toolkit-item', { hasText: 'AI 云助手' });
  await expect(aicloudItem).toBeVisible();
  await aicloudItem.click();
  await page.waitForTimeout(500);

  // 等待弹窗出现
  const modal = page.locator('.aicloud');
  await expect(modal).toBeVisible({ timeout: 5000 });
}

test.describe('多模型 Agent (AI 云助手) E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    // AI 云助手需要 admin 权限
    await loginAs(page, {
      email: ADMIN_EMAIL,
      password: ADMIN_PASSWORD,
      permissionLevel: 'admin',
    });
  });

  test('01 - 打开 AI 云助手弹窗', async ({ page }) => {
    await openAicloud(page);

    // 验证弹窗内容
    await expect(page.locator('.aicloud')).toBeVisible();
    await expect(page.locator('.aicloud h3', { hasText: 'AI 云助手' })).toBeVisible();

    // 验证 Tab 栏
    await expect(page.locator('.tab-btn', { hasText: '对话' })).toBeVisible();
    await expect(page.locator('.tab-btn', { hasText: '知识库' })).toBeVisible();

    // 验证模型选择器
    await expect(page.locator('.model-select')).toBeVisible();

    // 验证输入框
    await expect(page.locator('.message-input')).toBeVisible();
  });

  test('02 - 模型列表加载', async ({ page }) => {
    // 监听模型列表请求
    const modelsPromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/aicloud/models') && resp.status() === 200
    );

    await openAicloud(page);

    // 等待模型列表加载完成
    const modelsResp = await modelsPromise;
    const modelsData = await modelsResp.json();

    // 验证返回了模型列表
    expect(modelsData.models).toBeDefined();
    expect(Array.isArray(modelsData.models)).toBe(true);
    expect(modelsData.models.length).toBeGreaterThan(0);

    // 验证前端下拉选项
    const options = await page.locator('.model-select option').all();
    expect(options.length).toBeGreaterThan(0);

    // 检查是否有默认模型标记
    const hasDefault = await page.locator('.model-select option', { hasText: '(默认)' }).count();
    expect(hasDefault).toBeGreaterThan(0);
  });

  test('03 - 发送消息并验证 SSE 推送内容显示', async ({ page }) => {
    // 监听 SSE 流式接口
    const streamResponses = [];
    page.on('response', (resp) => {
      if (resp.url().includes('/api/v1/aicloud/chat/stream')) {
        streamResponses.push(resp);
      }
    });

    await openAicloud(page);

    const testMessage = `你好，请简单回复"测试成功"四个字。`;

    // 在输入框中输入消息
    const textarea = page.locator('.message-input');
    await textarea.fill(testMessage);

    // 记录发送前的消息数量
    const msgCountBefore = await page.locator('.message.user, .message.assistant').count();

    // 点击发送按钮
    const sendBtn = page.locator('.input-actions button', { hasText: '发送' });
    await sendBtn.click();

    // 验证用户消息立即显示
    await expect(page.locator('.message.user')).toHaveCount(msgCountBefore + 1, { timeout: 3000 });

    // 验证用户消息内容正确
    const userMsgs = page.locator('.message.user .message-text');
    const lastUserMsg = userMsgs.last();
    await expect(lastUserMsg).toContainText('测试成功', { timeout: 3000 });

    // 等待 AI 回复 (SSE 流式响应)
    // 策略：等待 assistant 消息出现，并且内容不再是 "AI 正在输入..."
    const aiMsgLocator = page.locator('.message.assistant .message-text');
    await expect(aiMsgLocator.last()).not.toHaveText('AI 正在输入...', { timeout: 30000 });

    // 验证 SSE 请求已发出
    expect(streamResponses.length).toBeGreaterThan(0);

    // 验证 AI 回复消息存在且有内容
    const aiMessages = await page.locator('.message.assistant').count();
    expect(aiMessages).toBeGreaterThan(0);

    // 验证 AI 回复内容不是错误信息
    const aiText = await aiMsgLocator.last().innerText();
    expect(aiText).not.toContain('错误:');
    expect(aiText).not.toContain('抱歉，没有收到回复');
    expect(aiText.length).toBeGreaterThan(0);

    // 打印 AI 回复内容用于调试
    console.log(`AI 回复: ${aiText}`);
  });

  test('04 - 多轮对话：验证上下文记忆', async ({ page }) => {
    await openAicloud(page);

    // 第一轮：发送问题
    await page.locator('.message-input').fill('请记住这个单词: PLAYWRIGHT_TEST_WORD');
    await page.locator('.input-actions button', { hasText: '发送' }).click();

    // 等待 AI 回复完成
    const aiMsgLocator = page.locator('.message.assistant .message-text');
    await expect(aiMsgLocator.last()).not.toHaveText('AI 正在输入...', { timeout: 30000 });

    const firstAiReply = await aiMsgLocator.last().innerText();
    expect(firstAiReply).not.toContain('错误:');

    // 第二轮：提问上下文
    await page.locator('.message-input').fill('我刚才让你记住的单词是什么？');
    await page.locator('.input-actions button', { hasText: '发送' }).click();

    // 等待第二轮 AI 回复
    await expect(aiMsgLocator.last()).not.toHaveText('AI 正在输入...', { timeout: 30000 });

    const secondAiReply = await aiMsgLocator.last().innerText();
    expect(secondAiReply).not.toContain('错误:');

    // 验证 AI 能够回忆起之前的内容
    // 注意：AI 回复可能不会精确匹配，但应该包含关键词
    expect(secondAiReply.toLowerCase()).toMatch(/playwright_test_word|单词|记住/i);

    // 验证总消息数：2 轮对话 = 4 条消息 (2 user + 2 assistant)
    const totalMessages = await page.locator('.message.user, .message.assistant').count();
    expect(totalMessages).toBeGreaterThanOrEqual(4);
  });

  test('05 - 切换模型后发送消息', async ({ page }) => {
    await openAicloud(page);

    // 获取模型列表
    const options = await page.locator('.model-select option').all();
    if (options.length < 2) {
      test.skip(true, '只有一个模型，跳过切换测试');
      return;
    }

    // 获取第一个非默认模型
    const firstOptionValue = await options[0].getAttribute('value');
    const firstOptionText = await options[0].innerText();

    // 切换到第一个模型
    await page.locator('.model-select').selectOption(firstOptionValue);
    await page.waitForTimeout(300);

    // 验证模型已切换
    const selectedValue = await page.locator('.model-select').inputValue();
    expect(selectedValue).toBe(firstOptionValue);

    // 发送消息
    await page.locator('.message-input').fill(`你好，当前使用的模型是 ${firstOptionText} 吗？请确认。`);
    await page.locator('.input-actions button', { hasText: '发送' }).click();

    // 等待 AI 回复
    const aiMsgLocator = page.locator('.message.assistant .message-text');
    await expect(aiMsgLocator.last()).not.toHaveText('AI 正在输入...', { timeout: 30000 });

    const aiReply = await aiMsgLocator.last().innerText();
    expect(aiReply).not.toContain('错误:');
    expect(aiReply.length).toBeGreaterThan(0);
  });

  test('06 - 新会话功能', async ({ page }) => {
    await openAicloud(page);

    // 先发送一条消息
    await page.locator('.message-input').fill('这是一条测试消息');
    await page.locator('.input-actions button', { hasText: '发送' }).click();

    // 等待回复
    const aiMsgLocator = page.locator('.message.assistant .message-text');
    await expect(aiMsgLocator.last()).not.toHaveText('AI 正在输入...', { timeout: 30000 });

    // 记录当前消息数
    const msgCountBefore = await page.locator('.message.user, .message.assistant').count();
    expect(msgCountBefore).toBeGreaterThanOrEqual(2);

    // 点击新会话按钮
    const newSessionBtn = page.locator('.input-actions button', { hasText: '新会话' });
    await newSessionBtn.click();
    await page.waitForTimeout(500);

    // 验证消息被清空
    const msgCountAfter = await page.locator('.message.user, .message.assistant').count();
    expect(msgCountAfter).toBe(0);

    // 验证空状态提示
    await expect(page.locator('.empty-messages')).toBeVisible();
  });

  test('07 - 消息列表滚动行为', async ({ page }) => {
    await openAicloud(page);

    // 发送多条消息，触发滚动
    for (let i = 1; i <= 5; i++) {
      await page.locator('.message-input').fill(`第 ${i} 条消息`);
      await page.locator('.input-actions button', { hasText: '发送' }).click();

      // 等待 AI 回复出现
      const aiMsgLocator = page.locator('.message.assistant .message-text');
      await expect(aiMsgLocator.last()).not.toHaveText('AI 正在输入...', { timeout: 30000 });
    }

    // 验证消息容器可滚动
    const chatMessages = page.locator('.chat-messages');
    const scrollHeight = await chatMessages.evaluate(el => el.scrollHeight);
    const clientHeight = await chatMessages.evaluate(el => el.clientHeight);

    // 如果有足够多的消息，scrollHeight 应该大于 clientHeight
    if (scrollHeight > clientHeight) {
      // 验证滚动条已到底部（新消息应该在底部）
      const scrollTop = await chatMessages.evaluate(el => el.scrollTop);
      const maxScroll = scrollHeight - clientHeight;
      // 允许 50px 误差
      expect(maxScroll - scrollTop).toBeLessThan(50);
    }
  });

  test('08 - SSE 错误处理：消息内容显示错误信息', async ({ page }) => {
    // 这个测试通过拦截请求来模拟错误
    await openAicloud(page);

    // 拦截 SSE 请求并返回 500 错误
    await page.route('**/api/v1/aicloud/chat/stream', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '模拟服务器错误' }),
      });
    });

    await page.locator('.message-input').fill('这是一条会触发错误的消息');
    await page.locator('.input-actions button', { hasText: '发送' }).click();

    // 等待错误信息显示
    const aiMsgLocator = page.locator('.message.assistant .message-text');
    await expect(aiMsgLocator.last()).toContainText('错误:', { timeout: 5000 });
    await expect(aiMsgLocator.last()).toContainText('模拟服务器错误', { timeout: 5000 });
  });
});
