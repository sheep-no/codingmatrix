/**
 * 方案 2 和方案 3 实战测试 - 简化版
 * 
 * 测试场景：
 * 1. 创建一个 session（博客系统）
 * 2. 用方案 3（search_sessions）验证语义匹配
 * 3. 用方案 2（auto-resolve）验证"继续"语义
 */

const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';

// 真实模型生成长流程，仅在提供 TEST_SILICONFLOW_API_KEY 时启用
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

test.describe('智能会话匹配实战测试', () => {
  test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）')

  test('方案 2 + 方案 3：继续功能智能匹配', async ({ page }) => {
    // 首轮生成实测可达 10 分钟，继续流程还需一轮，预算按 30 分钟设置
    test.setTimeout(1800000);

    // ========== 1. 登录 ==========
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);

    const loginResult = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';
      const resp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ email, password }),
      });
      if (!resp.ok) return { success: false, error: await resp.text() };
      return { success: true, data: await resp.json() };
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    expect(loginResult.success).toBe(true);
    const token = loginResult.data.access_token;

    await page.evaluate((token) => {
      const expiry = Date.now() + 30 * 60 * 1000;
      sessionStorage.setItem('_token', token);
      sessionStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('access_token', token);
      localStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('username', 'admin');
      localStorage.setItem('email', 'mr_yang@example.com');
      localStorage.setItem('permission_level', 'superadmin');
    }, token);
    await syncRealApiKeys(page);

    // ========== 2. 方案 3 测试：search_sessions API ==========
    console.log('\n===== 方案 3：search_sessions API 测试 =====');

    // 直接用已有历史会话测试匹配，避免创建无人消费的流式任务
    const apiResults = await page.evaluate(async (token) => {
      try {
        const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
        const csrfToken = csrfMatch ? csrfMatch[1] : '';
        const headers = { 
          'Content-Type': 'application/json', 
          'Authorization': `Bearer ${token}`,
          'X-CSRF-Token': csrfToken
        };

        const listResp = await fetch('/api/v1/agent/sessions?limit=50', { headers });
        const listData = await listResp.json();
        const sessions = (listData.sessions || []).filter(s => s.status === 'completed');

        // 评分需要用户 Key，否则后端会回退到未配置的默认 provider 并静默给 0 分
        const storedKeys = JSON.parse(localStorage.getItem('codingmatrix_apikeys') || '[]');
        const apiKeyToken = storedKeys[0]?.token;

        // 搜索历史需求中的既有主题
        const searchBlog = await fetch('/api/v1/agent/search_sessions', {
          method: 'POST', headers,
          body: JSON.stringify({ query: 'Python 脚本 Hello World', limit: 5, api_key_token: apiKeyToken })
        });
        const blogResult = await searchBlog.json();

        const searchShop = await fetch('/api/v1/agent/search_sessions', {
          method: 'POST', headers,
          body: JSON.stringify({ query: 'Vue 计数器 前端', limit: 5, api_key_token: apiKeyToken })
        });
        const shopResult = await searchShop.json();

        return {
          completedCount: sessions.length,
          hasApiKeyToken: Boolean(apiKeyToken),
          blogMatches: blogResult.matches || [],
          shopMatches: shopResult.matches || [],
          blogCount: blogResult.matches?.length || 0,
          shopCount: shopResult.matches?.length || 0
        };
      } catch (e) {
        return { error: e.message };
      }
    }, token);

    console.log(`已完成会话: ${apiResults.completedCount} 个`);
    console.log(`请求携带用户 Key: ${apiResults.hasApiKeyToken}`);
    console.log(`搜索"Python 脚本 Hello World": ${apiResults.blogCount} 个匹配`);
    console.log(`搜索"Vue 计数器 前端": ${apiResults.shopCount} 个匹配`);
    
    if (apiResults.blogMatches.length > 0) {
      console.log(`博客最高分: ${apiResults.blogMatches[0]?.relevance_score || 0} - ${apiResults.blogMatches[0]?.requirement_preview?.slice(0, 50)}...`);
    }
    if (apiResults.shopMatches.length > 0) {
      console.log(`电商最高分: ${apiResults.shopMatches[0]?.relevance_score || 0} - ${apiResults.shopMatches[0]?.requirement_preview?.slice(0, 50)}...`);
    }

    // 验证方案 3 正常工作：历史会话存在且接口返回匹配列表
    expect(apiResults.error).toBeUndefined();
    expect(apiResults.completedCount || 0).toBeGreaterThanOrEqual(1);
    expect(apiResults.blogCount || 0).toBeGreaterThanOrEqual(1);
    expect(apiResults.shopCount || 0).toBeGreaterThanOrEqual(1);
    expect(apiResults.hasApiKeyToken).toBe(true);
    // 有真实 Key 时评分必须生效，不能全部是 0
    const topScores = [
      apiResults.blogMatches[0]?.relevance_score || 0,
      apiResults.shopMatches[0]?.relevance_score || 0,
    ];
    expect(Math.max(...topScores)).toBeGreaterThan(0);
    console.log('方案 3 API 测试通过');

    // ========== 3. 方案 2 测试：智能继续 ==========
    console.log('\n===== 方案 2：智能继续测试 =====');

    // 进入 Agent 页面
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);

    // 确保 API Key 已加载
    await page.evaluate(() => {
      try {
        const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
        if (pinia) {
          let store = pinia._s?.get('apikey');
          if (store) store.loadFromStorage();
        }
      } catch (e) {}
    });
    await page.waitForTimeout(500);

    // 输入需求并生成
    const textarea = page.locator('textarea.prompt-textarea');
    await expect(textarea).toBeVisible({ timeout: 10000 });

    const generateBtn = page.locator('button[aria-label="发送需求"]');
    const stopBtn = page.locator('button[aria-label="停止生成"]');

    // 记录当前流式请求的会话 ID，完成判定以后端状态为准
    let currentSessionId = null;
    page.on('request', req => {
      if (req.url().includes('/agent/orchestrate/stream')) {
        try {
          currentSessionId = req.postDataJSON().session_id || currentSessionId;
        } catch {}
      }
    });

    const readToken = () => page.evaluate(
      () => localStorage.getItem('access_token') || sessionStorage.getItem('_token')
    );

    // 轮询后端会话状态，直到本轮生成真正结束
    const waitForSessionDone = async (sessionId, timeoutMs = 600000) => {
      if (!sessionId) {
        const running = await page.evaluate(async (token) => {
          const resp = await fetch('/api/v1/agent/sessions?limit=10', {
            headers: { Authorization: `Bearer ${token}` },
          });
          const data = await resp.json();
          const active = (data.sessions || []).filter(s => s.status === 'running');
          return active[0]?.session_id || null;
        }, await readToken());
        sessionId = running;
      }
      if (!sessionId) throw new Error('无法确定当前会话 ID');

      const deadline = Date.now() + timeoutMs;
      let lastStatus = null;
      while (Date.now() < deadline) {
        const status = await page.evaluate(async ({ sid, token }) => {
          const resp = await fetch(`/api/v1/agent/sessions/${sid}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!resp.ok) return { status: 'unknown', http: resp.status };
          return await resp.json();
        }, { sid: sessionId, token: await readToken() });

        // 新建会话可能稍后才落库，404 先重试而不是当作已结束
        if (status.status && status.status !== 'unknown') {
          lastStatus = status.status;
        }
        if (lastStatus && lastStatus !== 'running') {
          console.log(`[wait] 会话 ${sessionId} 结束: ${status.status}`);
          return status;
        }
        await page.waitForTimeout(3000);
      }
      throw new Error(`会话 ${sessionId} 在 ${timeoutMs}ms 内未结束（最后状态: ${lastStatus || 'unknown'}）`);
    };

    // 确认可能出现的决策卡片，确保发送按钮可用
    const confirmDecision = async () => {
      const confirmBtn = page.locator('.decision-card .btn-decision-primary');
      if (await confirmBtn.first().isVisible({ timeout: 1500 }).catch(() => false)) {
        const useDefault = page.locator('.decision-card .btn-decision-secondary');
        if (await useDefault.first().isVisible({ timeout: 1000 }).catch(() => false)) {
          await useDefault.first().click();
        }
        await confirmBtn.first().click();
        await page.waitForTimeout(1000);
      }
    };

    // 填入需求并发送，确保按钮真正可用后再点击
    const sendPrompt = async (text) => {
      await confirmDecision();
      for (let attempt = 0; attempt < 20; attempt++) {
        await textarea.fill(text);
        await page.waitForTimeout(300);
        if (await generateBtn.isEnabled().catch(() => false)) {
          await generateBtn.click();
          return true;
        }
        await confirmDecision();
      }
      throw new Error(`发送按钮始终不可用: ${text}`);
    };

    // 用已验证可在数分钟内完成的单文件需求，避免多文件+交叉验证导致生成时间不可控
    await sendPrompt('创建一个 Hello World 的 Python 脚本，只有一个 main.py');
    console.log('[Session] 点击生成');

    // 等待首轮生成真正结束
    await stopBtn.waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
    await waitForSessionDone(currentSessionId);
    await page.waitForTimeout(2000);

    const firstFiles = await page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item .file-name');
      return Array.from(fileItems).map(el => el.textContent?.trim()).filter(Boolean);
    });
    console.log(`[Session] 完成：生成了 ${firstFiles?.length || 0} 个文件`);
    console.log(`  文件: ${(firstFiles || []).join(', ')}`);

    // 测试"继续"功能
    console.log('\n[继续] 测试继续功能...');
    await sendPrompt('继续，加一个打印当前日期的函数');
    await stopBtn.waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
    await waitForSessionDone(currentSessionId);
    await page.waitForTimeout(2000);

    const resumeFiles = await page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item .file-name');
      return Array.from(fileItems).map(el => el.textContent?.trim()).filter(Boolean);
    });
    console.log(`[继续] 完成：生成了 ${resumeFiles?.length || 0} 个文件`);
    console.log(`  文件: ${(resumeFiles || []).join(', ')}`);

    // ========== 4. 输出结果 ==========
    console.log('\n===== 测试结果汇总 =====');
    console.log(`方案 3 API - 博客匹配: ${apiResults.blogCount} 个`);
    console.log(`方案 3 API - 电商匹配: ${apiResults.shopCount} 个`);
    console.log(`初始 Session: ${firstFiles?.length || 0} 个文件`);
    console.log(`继续 Session: ${resumeFiles?.length || 0} 个文件`);
    console.log('========================\n');

    // 验证
    expect(firstFiles?.length || 0).toBeGreaterThan(0);
    expect(resumeFiles?.length || 0).toBeGreaterThan(0);
  });
});
