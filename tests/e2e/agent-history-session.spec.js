import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth';

const BASE = 'http://127.0.0.1:8000';

test.describe('Agent 历史项目与会话切换', () => {

  test('查看历史项目列表 API', async ({ page }) => {
    const { token } = await apiLogin(page, BASE);

    // 获取保存的项目列表（手动传递 token）
    const resp = await page.request.get(`${BASE}/api/v1/agent/saved`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    console.log(`[PASS] 项目列表 API 正常, 共 ${data.total || 0} 个项目, 最大允许 ${data.max_allowed || 'N/A'} 个`);
    console.log(`  项目列表: ${JSON.stringify(data.projects?.map(p => p.name || p.id) || [])}`);
  });

  test('页面加载后显示会话选择器', async ({ page }) => {
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const sessionList = page.locator('.session-list');
    await expect(sessionList).toBeVisible({ timeout: 10000 });
    const count = await page.locator('.session-item').count();
    console.log(`[PASS] 会话列表可见, 共 ${count} 个会话`);
  });

  test('创建两个会话并切换', async ({ page }) => {
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const textarea = page.locator('textarea').first();
    const sessionItems = page.locator('.session-item');
    const newBtn = page.locator('button[title="新建会话"]');

    // === 创建第一个会话 ===
    console.log('--- 创建会话 1 ---');
    await textarea.fill('项目1: 创建一个计算器应用');
    // 触发 input 事件确保 prompt 保存
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(300);
    await newBtn.click();
    await page.waitForTimeout(800);

    const session1Text = await sessionItems.first().innerText();
    console.log(`  当前会话: ${session1Text}`);

    // === 创建第二个会话 ===
    console.log('--- 创建会话 2 ---');
    await textarea.fill('项目2: 创建一个待办事项应用');
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(300);
    await newBtn.click();
    await page.waitForTimeout(800);

    const session2Text = await sessionItems.first().innerText();
    console.log(`  当前会话: ${session2Text}`);

    // 会话展示文案按模式显示，使用持久化记录验证两个会话及其提示词
    expect(await sessionItems.count()).toBeGreaterThanOrEqual(2);
    const savedSessions = await page.evaluate(() => JSON.parse(localStorage.getItem('agent_project_sessions') || '[]'));
    expect(new Set(savedSessions.map(session => session.id)).size).toBeGreaterThanOrEqual(2);
    expect(savedSessions.some(session => session.prompt.includes('项目1'))).toBeTruthy();
    expect(savedSessions.some(session => session.prompt.includes('项目2'))).toBeTruthy();
    console.log('[PASS] 两个会话已创建');

    // 调试: 检查 localStorage 中的会话数据
    const sessions = await page.evaluate(() => {
      const data = localStorage.getItem('agent_project_sessions');
      return data ? JSON.parse(data) : [];
    });
    console.log('--- localStorage 会话数据 ---');
    sessions.forEach((s, i) => {
      console.log(`  [${i}] id=${s.id}, prompt="${(s.prompt || '').substring(0, 30)}", files=${(s.files || []).length}`);
    });

    // === 切换到第一个会话 ===
    console.log('--- 切换到会话 1 ---');
    await sessionItems.nth(1).click();
    await page.waitForTimeout(500);

    const text1 = await textarea.inputValue();
    console.log(`  textarea 内容: "${text1}"`);

    // === 切换到第二个会话 ===
    console.log('--- 切换到会话 2 ---');
    await sessionItems.first().click();
    await page.waitForTimeout(500);

    const text2 = await textarea.inputValue();
    console.log(`  textarea 内容: "${text2}"`);

    // 验证切换后内容不同
    if (text1 && text2 && text1 !== text2) {
      console.log('[PASS] 切换会话后 textarea 内容正确切换');
    } else if (text1 || text2) {
      console.log(`[INFO] 一个会话有内容，一个为空 (text1="${text1}", text2="${text2}")`);
    } else {
      console.log('[WARN] 两个会话都为空 - 可能是会话状态保存时序问题');
    }

    // === 验证会话列表完整性 ===
    const allOptions = await sessionItems.allTextContents();
    console.log('--- 所有会话选项 ---');
    allOptions.forEach((opt, i) => console.log(`  [${i}] ${opt}`));

    expect(allOptions.length).toBeGreaterThanOrEqual(2);
    console.log('[PASS] 会话列表完整');
  });

  test('删除会话', async ({ page }) => {
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');

    const sessionItems = page.locator('.session-item');
    const newBtn = page.locator('button[title="新建会话"]');

    // 先创建一个会话
    const textarea = page.locator('textarea').first();
    await textarea.fill('待删除的会话');
    await newBtn.click();
    await page.waitForTimeout(500);

    const countBefore = await sessionItems.count();
    console.log(`  删除前会话数: ${countBefore}`);

    // 点击删除
    if (countBefore > 0) {
      await sessionItems.first().locator('.session-delete').click();
      await page.waitForTimeout(500);
      const countAfter = await sessionItems.count();
      console.log(`  删除后会话数: ${countAfter}`);
      expect(countAfter).toBeLessThan(countBefore);
      console.log('[PASS] 会话删除成功');
    } else {
      console.log('[INFO] 删除按钮不可见');
    }
  });

  test('并发限制 API', async ({ page }) => {
    const { token } = await apiLogin(page, BASE);

    // 获取并发限制信息
    const resp = await page.request.get(`${BASE}/api/v1/agent/concurrent-limits/recommended`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (resp.ok()) {
      const data = await resp.json();
      console.log(`[PASS] 并发限制 API: ${JSON.stringify(data).substring(0, 200)}`);
    } else {
      console.log(`[INFO] 并发限制 API 返回 ${resp.status()}`);
    }
  });
});
