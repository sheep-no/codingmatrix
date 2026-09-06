const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'GameAiE2ePass123!';

test.describe('游戏 AI PPT 生成端到端测试', () => {
  test('浏览器调用真实生成接口并验证领域化回退大纲', async ({ page }) => {
    test.setTimeout(180000);

    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('domcontentloaded');

    const result = await page.evaluate(async ({ password, topic }) => {
      const csrfResponse = await fetch('/api/v1/csrf-token', { credentials: 'include' });
      if (!csrfResponse.ok) return { ok: false, step: 'csrf', detail: await csrfResponse.text() };
      const csrfToken = document.cookie.match(/csrf_token=([^;]+)/)?.[1] || '';
      const email = `game-ai-e2e-${Date.now()}@example.com`;
      const registerResponse = await fetch('/api/v1/register', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ email, password, username: 'game-ai-e2e' }),
      });
      if (!registerResponse.ok) return { ok: false, step: 'register', detail: await registerResponse.text() };
      const registerData = await registerResponse.json();
      const token = registerData.access_token;
      const generateResponse = await fetch('/api/v1/pptx/generate', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt: topic,
          template: 'auto',
          slide_count: 16,
          output_format: 'pptx',
        }),
      });
      const body = await generateResponse.json();
      if (!generateResponse.ok) return { ok: false, step: 'generate', detail: body };

      const downloadResponse = await fetch(body.download_url, {
        credentials: 'include',
        headers: { Authorization: `Bearer ${token}` },
      });
      const buffer = await downloadResponse.arrayBuffer();
      return {
        ok: true,
        response: body,
        downloadStatus: downloadResponse.status,
        downloadBytes: buffer.byteLength,
      };
    }, {
      password: TEST_PASSWORD,
      topic: '论游戏在AI时代的发展方向',
    });

    expect(result.ok, JSON.stringify(result)).toBe(true);
    expect(result.response.status).toBe('completed');
    expect(result.response.slide_count).toBe(15);
    expect(result.response.slides).toHaveLength(15);
    expect(result.response.slides.map((slide) => slide.title).join(' ')).toContain('AI时代');
    expect(result.response.slides.map((slide) => JSON.stringify(slide)).join(' ')).toContain('NPC');
    expect(result.response.slides.map((slide) => JSON.stringify(slide)).join(' ')).toContain('UGC');
    expect(result.downloadStatus).toBe(200);
    expect(result.downloadBytes).toBeGreaterThan(10000);
  });
});
