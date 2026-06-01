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
const TEST_EMAIL = process.env.TEST_EMAIL || 'admin@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'admin123';

test.describe('智能会话匹配实战测试', () => {
  test('方案 2 + 方案 3：继续功能智能匹配', async ({ page }) => {
    test.setTimeout(600000);

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

    // 设置 mock API Key
    await page.evaluate((token) => {
      const expiry = Date.now() + 30 * 60 * 1000;
      sessionStorage.setItem('_token', token);
      sessionStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('access_token', token);
      localStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('username', 'admin');
      localStorage.setItem('email', 'admin@example.com');
      localStorage.setItem('permission_level', 'superadmin');
      localStorage.setItem('codingmatrix_apikeys', JSON.stringify([{
        token: 'test-siliconflow-token', provider: 'siliconflow',
        remark: 'Test Key', status: 'verified',
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        ttl_seconds: 86400, enabled: true,
      }]));
    }, token);

    // ========== 2. 方案 3 测试：search_sessions API ==========
    console.log('\n===== 方案 3：search_sessions API 测试 =====');

    // 先用 API 创建几个不同需求的 session，用于测试匹配
    const apiResults = await page.evaluate(async (token) => {
      try {
        const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
        const csrfToken = csrfMatch ? csrfMatch[1] : '';
        const headers = { 
          'Content-Type': 'application/json', 
          'Authorization': `Bearer ${token}`,
          'X-CSRF-Token': csrfToken
        };
        
        const sessions = [];
        
        // 创建 Session 1: 博客系统
        const create1 = await fetch('/api/v1/agent/orchestrate/stream', {
          method: 'POST', headers,
          body: JSON.stringify({
            requirement: '创建一个 Python Flask 博客系统，包含文章管理和用户评论',
            session_id: 'test-blog-session',
            spec_first: true
          })
        });
        
        // 创建 Session 2: 电商系统
        const create2 = await fetch('/api/v1/agent/orchestrate/stream', {
          method: 'POST', headers,
          body: JSON.stringify({
            requirement: '创建一个 Vue + Express 电商前端，包含商品列表和购物车',
            session_id: 'test-shop-session',
            spec_first: true
          })
        });

        // 搜索"博客"相关
        const searchBlog = await fetch('/api/v1/agent/search_sessions', {
          method: 'POST', headers,
          body: JSON.stringify({ query: '博客系统', limit: 5 })
        });
        const blogResult = await searchBlog.json();

        // 搜索"电商"相关
        const searchShop = await fetch('/api/v1/agent/search_sessions', {
          method: 'POST', headers,
          body: JSON.stringify({ query: '电商商品', limit: 5 })
        });
        const shopResult = await searchShop.json();

        return {
          blogMatches: blogResult.matches || [],
          shopMatches: shopResult.matches || [],
          blogCount: blogResult.matches?.length || 0,
          shopCount: shopResult.matches?.length || 0
        };
      } catch (e) {
        return { error: e.message };
      }
    }, token);

    console.log(`搜索"博客系统": ${apiResults.blogCount} 个匹配`);
    console.log(`搜索"电商商品": ${apiResults.shopCount} 个匹配`);
    
    if (apiResults.blogMatches.length > 0) {
      console.log(`博客最高分: ${apiResults.blogMatches[0]?.relevance_score || 0} - ${apiResults.blogMatches[0]?.requirement_preview?.slice(0, 50)}...`);
    }
    if (apiResults.shopMatches.length > 0) {
      console.log(`电商最高分: ${apiResults.shopMatches[0]?.relevance_score || 0} - ${apiResults.shopMatches[0]?.requirement_preview?.slice(0, 50)}...`);
    }

    // 验证方案 3 正常工作
    expect(apiResults.blogCount || 0).toBeGreaterThanOrEqual(1);
    expect(apiResults.shopCount || 0).toBeGreaterThanOrEqual(1);
    console.log('✓ 方案 3 API 测试通过');

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

    await textarea.fill('创建一个 HTML 个人主页，包含个人简介和联系方式');
    await page.waitForTimeout(500);

    const generateBtn = page.locator('.action-buttons .btn-primary');
    await expect(generateBtn).toBeEnabled({ timeout: 10000 });
    await generateBtn.click();
    console.log('[Session] 点击生成');

    // 等待生成完成
    const stopBtn = page.locator('.action-buttons .btn-danger');
    await stopBtn.waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
    await stopBtn.waitFor({ state: 'hidden', timeout: 300000 }).catch(() => {});
    await page.waitForTimeout(2000);

    const firstFiles = await page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item .file-name');
      return Array.from(fileItems).map(el => el.textContent?.trim()).filter(Boolean);
    });
    console.log(`[Session] 完成：生成了 ${firstFiles?.length || 0} 个文件`);
    console.log(`  文件: ${(firstFiles || []).join(', ')}`);

    // 测试"继续"功能
    console.log('\n[继续] 测试继续功能...');
    await textarea.fill('继续，加上一个作品展示部分');
    await page.waitForTimeout(500);
    await generateBtn.click();

    await stopBtn.waitFor({ state: 'visible', timeout: 30000 }).catch(() => {});
    await stopBtn.waitFor({ state: 'hidden', timeout: 300000 }).catch(() => {});
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
