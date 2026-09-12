import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth';

async function openAgentWorkspace(page) {
  await page.goto('/agent', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.agent-page')).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('textbox', { name: '项目需求' })).toBeVisible({ timeout: 10000 });
}

test.describe('Agent UI 轻量测试', () => {

  test('登录后进入 Agent 页面，验证 UI 元素', async ({ page }) => {
    const { ok } = await apiLogin(page, 'http://127.0.0.1:8000');
    expect(ok).toBeTruthy();

    await openAgentWorkspace(page);
    await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible();
  });

  test('输入需求后点击生成，验证 SSE 流开始', async ({ page }) => {
    await apiLogin(page, 'http://127.0.0.1:8000');

    await openAgentWorkspace(page);

    const prompt = page.getByRole('textbox', { name: '项目需求' });
    await prompt.fill('创建一个 hello.py 打印 hello world');

    const sendBtn = page.getByRole('button', { name: '发送需求' });
    await expect(sendBtn).toBeEnabled();
    await sendBtn.click();

    await expect(page.getByRole('button', { name: '停止生成' })).toBeVisible({ timeout: 15000 });
  });

  test('验证 API 健康检查和认证', async ({ page }) => {
    // 直接测试 API 端点
    const healthResp = await page.request.get('http://127.0.0.1:8000/api/v1/health');
    expect(healthResp.ok()).toBeTruthy();
    const health = await healthResp.json();
    expect(health.status).toBe('healthy');
    console.log(`[PASS] API 健康检查通过, 版本: ${health.version}`);

    // 测试认证端点
    const csrfResp = await page.request.get('http://127.0.0.1:8000/api/v1/csrf-token');
    expect(csrfResp.ok()).toBeTruthy();
    const csrf = await csrfResp.json();
    expect(csrf.csrf_token).toBeTruthy();
    console.log('[PASS] CSRF Token 获取正常');
  });
});
