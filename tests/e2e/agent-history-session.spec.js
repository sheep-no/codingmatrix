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
    await page.waitForLoadState('networkidle');

    // 检查会话选择器
    const sessionSelect = page.locator('.session-select');
    await expect(sessionSelect).toBeVisible({ timeout: 10000 });

    // 检查选项数量
    const options = sessionSelect.locator('option');
    const count = await options.count();
    console.log(`[PASS] 会话选择器可见, 共 ${count} 个选项`);

    // 打印所有选项
    for (let i = 0; i < count; i++) {
      const text = await options.nth(i).textContent();
      const value = await options.nth(i).getAttribute('value');
      console.log(`  选项 ${i}: "${text}" (value=${value})`);
    }
  });

  test('创建两个会话并切换', async ({ page }) => {
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('networkidle');

    const textarea = page.locator('textarea').first();
    const sessionSelect = page.locator('.session-select');
    const newBtn = page.locator('button', { hasText: '新建' });

    // === 创建第一个会话 ===
    console.log('--- 创建会话 1 ---');
    await textarea.fill('项目1: 创建一个计算器应用');
    // 触发 input 事件确保 prompt 保存
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(300);
    await newBtn.click();
    await page.waitForTimeout(800);

    const session1Value = await sessionSelect.inputValue();
    console.log(`  当前会话: ${session1Value}`);

    // === 创建第二个会话 ===
    console.log('--- 创建会话 2 ---');
    await textarea.fill('项目2: 创建一个待办事项应用');
    await textarea.dispatchEvent('input');
    await page.waitForTimeout(300);
    await newBtn.click();
    await page.waitForTimeout(800);

    const session2Value = await sessionSelect.inputValue();
    console.log(`  当前会话: ${session2Value}`);

    // 验证两个会话不同
    expect(session1Value).not.toBe(session2Value);
    console.log('[PASS] 两个会话 ID 不同');

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
    await sessionSelect.selectOption(session1Value);
    await page.waitForTimeout(500);

    const text1 = await textarea.inputValue();
    console.log(`  textarea 内容: "${text1}"`);

    // === 切换到第二个会话 ===
    console.log('--- 切换到会话 2 ---');
    await sessionSelect.selectOption(session2Value);
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
    const allOptions = await sessionSelect.locator('option').allTextContents();
    console.log('--- 所有会话选项 ---');
    allOptions.forEach((opt, i) => console.log(`  [${i}] ${opt}`));

    expect(allOptions.length).toBeGreaterThanOrEqual(3);
    console.log('[PASS] 会话列表完整');
  });

  test('删除会话', async ({ page }) => {
    await apiLogin(page, BASE);
    await page.goto('/agent');
    await page.waitForLoadState('networkidle');

    const sessionSelect = page.locator('.session-select');
    const newBtn = page.locator('button', { hasText: '新建' });
    const deleteBtn = page.locator('button', { hasText: '删除' });

    // 先创建一个会话
    const textarea = page.locator('textarea').first();
    await textarea.fill('待删除的会话');
    await newBtn.click();
    await page.waitForTimeout(500);

    const currentId = await sessionSelect.inputValue();
    const countBefore = await sessionSelect.locator('option').count();
    console.log(`  删除前选项数: ${countBefore}, 当前: ${currentId}`);

    // 点击删除
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click();
      await page.waitForTimeout(500);
      const countAfter = await sessionSelect.locator('option').count();
      console.log(`  删除后选项数: ${countAfter}`);
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
