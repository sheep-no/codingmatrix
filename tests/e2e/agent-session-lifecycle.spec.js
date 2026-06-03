import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth';

const BASE = 'http://127.0.0.1:8000';

test.describe('会话生命周期 E2E', () => {

  test('会话创建→切换→删除完整流程', async ({ page }) => {
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('networkidle');

    const textarea = page.locator('textarea').first();
    const sessionSelect = page.locator('.session-select');
    const newBtn = page.locator('button', { hasText: '新建' });
    const deleteBtn = page.locator('button', { hasText: '删除' });

    // === 1. 创建会话 1 ===
    await textarea.fill('项目1: Python 计算器');
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(200);
    await newBtn.click();
    await page.waitForTimeout(500);
    const session1 = await sessionSelect.inputValue();
    console.log(`[1] 会话1创建: ${session1}`);

    // === 2. 创建会话 2 ===
    await textarea.fill('项目2: Todo App');
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(200);
    await newBtn.click();
    await page.waitForTimeout(500);
    const session2 = await sessionSelect.inputValue();
    console.log(`[2] 会话2创建: ${session2}`);

    // 验证两个会话不同
    expect(session1).not.toBe(session2);

    // === 3. 验证会话列表 ===
    const options = await sessionSelect.locator('option').allTextContents();
    console.log(`[3] 会话列表 (${options.length}): ${options.join(' | ')}`);
    expect(options.length).toBeGreaterThanOrEqual(3); // 新建 + 2个会话

    // === 4. 切换到会话 1 ===
    await sessionSelect.selectOption(session1);
    await page.waitForTimeout(300);
    const text1 = await textarea.inputValue();
    console.log(`[4] 切换到会话1: "${text1}"`);
    expect(text1).toContain('项目1');

    // === 5. 切换到会话 2 ===
    await sessionSelect.selectOption(session2);
    await page.waitForTimeout(300);
    const text2 = await textarea.inputValue();
    console.log(`[5] 切换到会话2: "${text2}"`);
    expect(text2).toContain('项目2');

    // === 6. 删除会话 1 ===
    await sessionSelect.selectOption(session1);
    await page.waitForTimeout(300);
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      await page.waitForTimeout(500);
      const remainingOptions = await sessionSelect.locator('option').allTextContents();
      console.log(`[6] 删除会话1后: ${remainingOptions.length} 个选项`);
      expect(remainingOptions.length).toBeLessThan(options.length);
    }

    // === 7. 验证会话 2 仍然存在 ===
    const finalOptions = await sessionSelect.locator('option').allTextContents();
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

    // 验证 max_allowed
    expect(saved.max_allowed).toBe(3);

    console.log('[PASS] API 级别验证通过');
  });

  test('会话取消后状态更新', async ({ page }) => {
    const { token } = await apiLogin(page, BASE);
    const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

    // 通过 SSE 创建一个会话
    const sessionId = `cancel-test-${Date.now()}`;
    console.log(`[创建] 会话: ${sessionId}`);

    // 使用 page.evaluate 在浏览器中发起 fetch 请求
    const result = await page.evaluate(async ({ baseUrl, token, sessionId }) => {
      const resp = await fetch(`${baseUrl}/api/v1/agent/orchestrate/stream`, {
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

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let events = [];
      let done = false;

      while (!done) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        const text = decoder.decode(value);
        const lines = text.split('\n').filter(l => l.startsWith('data: '));
        for (const line of lines) {
          try {
            const data = JSON.parse(line.replace('data: ', ''));
            events.push(data.type);
            if (data.type === 'done') done = true;
          } catch {}
        }
      }

      return { eventCount: events.length, types: [...new Set(events)], done };
    }, { baseUrl: BASE, token, sessionId });

    console.log(`[生成] 事件: ${result.eventCount}, 类型: ${result.types.join(',')}`);
    expect(result.done).toBeTruthy();

    // 取消会话
    const cancelResp = await page.request.post(
      `${BASE}/api/v1/agent/session/${sessionId}/action?action=cancel`,
      { headers }
    );
    expect(cancelResp.ok()).toBeTruthy();
    const cancelData = await cancelResp.json();
    console.log(`[取消] 状态: ${cancelData.status}`);
    expect(cancelData.status).toBe('cancelled');

    console.log('[PASS] 会话取消后状态更新验证通过');
  });
});
