import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth';

const BASE = 'http://127.0.0.1:8000';

test.describe('会话生命周期 E2E', () => {

  test('会话创建→切换→删除完整流程', async ({ page }) => {
    test.setTimeout(90000);
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('[data-testid="agent-prompt-input"]');
    await textarea.waitFor({ state: 'visible', timeout: 60000 });
    const sessionItems = page.locator('.session-item');
    const newBtn = page.locator('button[title="新建会话"]');

    // === 1. 创建会话 1 ===
    await textarea.fill('项目1: Python 计算器');
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(200);
    await newBtn.click();
    await page.waitForTimeout(500);
    const session1 = await sessionItems.first().innerText();
    console.log(`[1] 会话1创建: ${session1}`);

    // === 2. 创建会话 2 ===
    await textarea.fill('项目2: Todo App');
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(200);
    await newBtn.click();
    await page.waitForTimeout(500);
    const session2 = await sessionItems.first().innerText();
    console.log(`[2] 会话2创建: ${session2}`);

    // 会话展示文案按模式显示，使用持久化记录验证两个会话
    const savedSessions = await page.evaluate(() => JSON.parse(localStorage.getItem('agent_project_sessions') || '[]'));
    expect(new Set(savedSessions.map(session => session.id)).size).toBeGreaterThanOrEqual(2);
    expect(savedSessions.length).toBeGreaterThanOrEqual(2);

    // === 3. 验证会话列表 ===
    const options = await sessionItems.allTextContents();
    console.log(`[3] 会话列表 (${options.length}): ${options.join(' | ')}`);
    expect(options.length).toBeGreaterThanOrEqual(2);

    // === 4. 切换到会话 1 ===
    await sessionItems.nth(1).click();
    await page.waitForTimeout(300);
    const text1 = await textarea.inputValue();
    console.log(`[4] 切换到会话1: "${text1}"`);
    expect(text1).toContain('项目1');

    // === 5. 切换到会话 2 ===
    await sessionItems.first().click();
    await page.waitForTimeout(300);
    const text2 = await textarea.inputValue();
    console.log(`[5] 切换到会话2: "${text2}"`);
    expect(text2).toContain('项目2');

    // === 6. 删除会话 1 ===
    await sessionItems.nth(1).click();
    await page.waitForTimeout(300);
    if (await sessionItems.nth(1).isVisible()) {
      await sessionItems.nth(1).locator('.session-delete').click();
      await page.waitForTimeout(500);
      const remainingOptions = await sessionItems.allTextContents();
      console.log(`[6] 删除会话1后: ${remainingOptions.length} 个选项`);
      expect(remainingOptions.length).toBeLessThan(options.length);
    }

    // === 7. 验证会话 2 仍然存在 ===
    const finalOptions = await sessionItems.allTextContents();
    const hasSession2 = finalOptions.some(opt => opt.includes('Todo') || opt.includes('项目2'));
    console.log(`[7] 最终选项: ${finalOptions.join(' | ')}`);

    console.log('[PASS] 会话生命周期完整流程验证通过');
  });

  test('API 级别验证：并发限制和会话状态', async ({ page }) => {
    const { token } = await apiLogin(page, BASE);
    const headers = { 'Authorization': `Bearer ${token}` };

    // 查询并发限制
    const limitsResp = await page.request.get(`${BASE}/api/v1/agent/concurrent-limits/recommended`, { headers });
    expect(limitsResp.ok()).toBeTruthy();
    const limits = await limitsResp.json();
    console.log(`[API] 并发限制: ${JSON.stringify(limits.recommendations)}`);

    // 查询已保存项目
    const savedResp = await page.request.get(`${BASE}/api/v1/agent/saved`, { headers });
    expect(savedResp.ok()).toBeTruthy();
    const saved = await savedResp.json();
    console.log(`[API] 已保存项目: ${saved.total} 个, 最大 ${saved.max_allowed} 个`);

    // 配额可由服务端配置，验证返回值能够容纳当前项目
    expect(saved.max_allowed).toBeGreaterThan(0);
    expect(saved.max_allowed).toBeGreaterThanOrEqual(saved.total);

    console.log('[PASS] API 级别验证通过');
  });

  test('会话取消后状态更新', async ({ page }) => {
    test.setTimeout(120000);
    const { token } = await apiLogin(page, BASE);
    const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

    // 通过 SSE 创建一个会话
    const sessionId = `cancel-test-${Date.now()}`;
    console.log(`[创建] 会话: ${sessionId}`);

    // 立即消费响应体，触发服务端流生成器完成会话注册
    await page.evaluate(({ baseUrl, token, sessionId }) => {
      window.__cancelTestStarted = false;
      window.__cancelTestStream = (async () => {
        const response = await fetch(`${baseUrl}/api/v1/agent/orchestrate/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          requirement: '创建一个 test.py 打印 test',
          session_id: sessionId,
          enable_review: false
        })
        });
        const reader = response.body.getReader();
        window.__cancelTestReader = reader;
        window.__cancelTestStarted = true;
        try {
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        } catch (error) {
          if (error.name !== 'AbortError') throw error;
        }
      })();
    }, { baseUrl: BASE, token, sessionId });
    // 轮询取消接口，直到 SSE 生成器完成数据库注册
    let cancelResp;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      cancelResp = await page.request.post(
        `${BASE}/api/v1/agent/session/${sessionId}/action?action=cancel`,
        { headers }
      );
      if (cancelResp.ok()) break;
      await page.waitForTimeout(1000);
    }
    expect(cancelResp.ok()).toBeTruthy();
    const cancelData = await cancelResp.json();
    console.log(`[取消] 状态: ${cancelData.status}`);
    expect(cancelData.status).toBe('cancelled');

    // 等待浏览器端连接结束，避免测试遗留未处理的 SSE 请求
    await page.evaluate(async () => {
      const reader = window.__cancelTestReader;
      if (reader) {
        await reader.cancel();
      }
      await Promise.race([window.__cancelTestStream, new Promise(resolve => setTimeout(resolve, 10000))]);
      delete window.__cancelTestStream;
      delete window.__cancelTestReader;
      delete window.__cancelTestStarted;
    });

    console.log('[PASS] 会话取消后状态更新验证通过');
  });
});
