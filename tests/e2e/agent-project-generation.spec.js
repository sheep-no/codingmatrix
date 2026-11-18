const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
// 该用例断言真实项目生成结果，必须提供 TEST_SILICONFLOW_API_KEY 才有意义
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

test.describe('Agent 项目生成测试 - 贪吃蛇网页版', () => {
  test.describe.configure({ project: 'chromium' });
  test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）');

  test('生成贪吃蛇网页版项目（单文件 HTML）', async ({ page }) => {
    test.setTimeout(1920000); // 32 分钟：2 CPU 环境下真实模型含决策等待与交叉验证，耗时不可控

    const timeline = [];
    const apiCalls = [];
    let startTime;

    // 监听所有 Agent 相关的网络请求
    page.on('request', (request) => {
      const url = request.url();
      if (url.includes('/api/v1/agent/')) {
        apiCalls.push({
          time: Date.now(),
          method: request.method(),
          url: url,
          postData: request.method() === 'POST' ? request.postDataJSON() : null
        });
      }
    });

    // 第一步：加密登录
    console.log('\n=== 步骤 1: 登录获取认证 ===');
    startTime = Date.now();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    const loginResult = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';

      const publicKeyResp = await fetch('/api/v1/public-key');
      const { public_key } = await publicKeyResp.json();

      const pemContents = public_key
        .replace('-----BEGIN PUBLIC KEY-----', '')
        .replace('-----END PUBLIC KEY-----', '')
        .replace(/\s/g, '');

      const binaryDer = atob(pemContents);
      const derArray = new Uint8Array(binaryDer.length);
      for (let i = 0; i < binaryDer.length; i++) {
        derArray[i] = binaryDer.charCodeAt(i);
      }

      const cryptoKey = await crypto.subtle.importKey(
        'spki', derArray.buffer,
        { name: 'RSA-OAEP', hash: 'SHA-256' },
        false, ['encrypt']
      );

      const aesKey = crypto.getRandomValues(new Uint8Array(32));
      const iv = crypto.getRandomValues(new Uint8Array(16));

      const aesCryptoKey = await crypto.subtle.importKey(
        'raw', aesKey, { name: 'AES-CBC' }, false, ['encrypt']
      );

      const plaintext = new TextEncoder().encode(JSON.stringify({ email, password }));
      const ciphertextBuffer = await crypto.subtle.encrypt(
        { name: 'AES-CBC', iv }, aesCryptoKey, plaintext
      );

      const combined = new Uint8Array(iv.length + ciphertextBuffer.byteLength);
      combined.set(iv, 0);
      combined.set(new Uint8Array(ciphertextBuffer), iv.length);

      function base64Encode(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
      }

      const encryptedData = base64Encode(combined.buffer);
      const encryptedKeyBuffer = await crypto.subtle.encrypt(
        { name: 'RSA-OAEP', hash: 'SHA-256' }, cryptoKey, aesKey
      );
      const encryptedKey = base64Encode(encryptedKeyBuffer);

      const loginResp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken || '',
        },
        body: JSON.stringify({ encrypted_data: encryptedData, encrypted_key: encryptedKey }),
      });

      if (loginResp.ok) {
        const data = await loginResp.json();
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('username', data.username);
        return { success: true, username: data.username };
      }
      return { success: false };
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    console.log('登录结果:', loginResult);
    timeline.push({ time: Date.now() - startTime, type: 'login_complete' });

    // 真实 Key 必须写入前端存储，请求体才能携带 api_key_token
    await syncRealApiKeys(page);

    // 第二步：生成会话 ID
    // 后端没有 POST /agent/sessions 建会话接口，前端也是本地生成会话 ID
    console.log('\n=== 步骤 2: 生成会话 ID ===');
    const sessionResult = { success: true, session_id: `e2e-snake-${Date.now()}` };

    console.log('会话创建结果:', sessionResult);
    timeline.push({ time: Date.now() - startTime, type: 'session_created', data: sessionResult });

    // 第三步：发送项目生成需求
    console.log('\n=== 步骤 3: 发送项目生成需求 ===');
    
    // 单文件需求：多文件+交叉验证会让真实生成时间不可控
    const requirement = `生成一个贪吃蛇网页版游戏，只有一个 index.html 文件。

功能要求：
- 方向键控制蛇的移动
- 食物随机生成，吃到后变长
- 撞墙或撞自己游戏结束
- 显示当前分数
- 开始和重新开始按钮`;

    // /agent/generate 是遗留端点，不支持用户 API Key；产品实际走 orchestrate/stream
    const projectResult = await page.evaluate(async ({ req, sessionId }) => {
      const token = localStorage.getItem('access_token');
      const storedKeys = JSON.parse(localStorage.getItem('codingmatrix_apikeys') || '[]');
      const apiKeyToken = storedKeys[0]?.token;

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1800000);

      try {
        const resp = await fetch('/api/v1/agent/orchestrate/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            requirement: req,
            enable_review: true,
            enable_validation: true,
            session_id: sessionId,
            api_key_token: apiKeyToken,
          }),
          signal: controller.signal
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          clearTimeout(timeoutId);
          return { success: false, error: err.detail?.message || err.detail || resp.statusText };
        }

        // 逐行解析 SSE，取 done 事件里的生成结果
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let doneEvent = null;
        let streamError = null;

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop() || '';
          for (const frame of frames) {
            const line = frame.split('\n').find(l => l.startsWith('data: '));
            if (!line) continue;
            const payload = line.slice(6).trim();
            if (payload === '[DONE]') continue;
            try {
              const parsed = JSON.parse(payload);
              if (parsed.type === 'done') doneEvent = parsed.data || {};
              if (parsed.type === 'error') streamError = parsed.data?.error || 'stream error';
            } catch {}
          }
        }
        clearTimeout(timeoutId);

        if (streamError) return { success: false, error: streamError };
        if (!doneEvent) return { success: false, error: '未收到 done 事件' };

        return {
          success: true,
          total_files: doneEvent.total_files_created || doneEvent.total_files || 0,
          output_dir: doneEvent.project_path || 'N/A',
          // 后端 done 事件的校验结果字段是 is_valid，不是 runnable
          validation_passed: doneEvent.validation?.is_valid || false,
          execution_time: doneEvent.execution_time || 0
        };
      } catch (error) {
        clearTimeout(timeoutId);
        return { success: false, error: error.message };
      }
    }, { req: requirement, sessionId: sessionResult.session_id });

    const projectDuration = Date.now() - startTime;
    console.log('\n=== 项目生成结果 ===');
    console.log(JSON.stringify(projectResult, null, 2));
    timeline.push({ time: projectDuration, type: 'project_generated', data: projectResult });

    // 第四步：收集统计信息
    console.log('\n=== 步骤 4: 收集统计信息 ===');
    const stats = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token');
      const resp = await fetch('/api/v1/agent/token-usage', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      return resp.ok ? await resp.json() : {};
    });

    console.log('Token 用量:', JSON.stringify(stats, null, 2));

    const endTime = Date.now();
    const totalDuration = endTime - startTime;

    // 输出完整的时间线
    console.log('\n========== 完整时间线 ==========');
    timeline.forEach((event, index) => {
      console.log(`${index + 1}. [+${event.time}ms] ${event.type}`);
      if (event.data) {
        if (event.data.total_files !== undefined) {
          console.log(`   生成文件数: ${event.data.total_files}`);
        }
        if (event.data.session_id) {
          console.log(`   会话 ID: ${event.data.session_id}`);
        }
      }
    });

    console.log('\n========== API 调用记录 ==========');
    apiCalls.forEach((call, index) => {
      console.log(`${index + 1}. ${call.method} ${new URL(call.url).pathname}`);
    });

    console.log('\n========== 性能汇总 ==========');
    console.log(`总耗时: ${totalDuration}ms (${(totalDuration / 1000).toFixed(1)}s)`);
    console.log(`API 调用次数: ${apiCalls.length}`);
    console.log(`项目生成成功: ${projectResult.success}`);
    if (projectResult.success) {
      console.log(`生成文件数: ${projectResult.total_files}`);
      console.log(`输出目录: ${projectResult.output_dir}`);
      console.log(`验证通过: ${projectResult.validation_passed}`);
    }

    // 断言
    expect(totalDuration).toBeGreaterThan(0);
    expect(apiCalls.length).toBeGreaterThan(0);
    expect(projectResult.error, '真实凭证下项目生成不应失败').toBeUndefined();
    expect(projectResult.success).toBe(true);
    expect(projectResult.total_files).toBeGreaterThan(0);
    expect(projectResult.output_dir).toBeDefined();
  });
});
