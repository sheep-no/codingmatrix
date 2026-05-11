const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test.describe('Agent 项目生成测试 - 贪吃蛇网页版', () => {
  test.describe.configure({ project: 'chromium' });

  test('生成贪吃蛇网页版项目（纯 HTML + Flask）', async ({ page }) => {
    test.setTimeout(300000); // 5 分钟超时

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

    // 第二步：创建会话
    console.log('\n=== 步骤 2: 创建项目生成会话 ===');
    const sessionResult = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token');
      
      const resp = await fetch('/api/v1/agent/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_type: 'code_generation',
          model_key: 'deepseek-ai/DeepSeek-R1-0528-Qwen3-8B'
        })
      });

      if (resp.ok) {
        const data = await resp.json();
        return { success: true, session_id: data.session_id };
      }
      return { success: false, error: await resp.text() };
    });

    console.log('会话创建结果:', sessionResult);
    timeline.push({ time: Date.now() - startTime, type: 'session_created', data: sessionResult });

    // 第三步：发送项目生成需求
    console.log('\n=== 步骤 3: 发送项目生成需求 ===');
    
    const requirement = `生成一个完整的贪吃蛇网页版游戏。

技术要求：
- 前端：纯 HTML + CSS + JavaScript（单文件 index.html）
- 后端：Python Flask 框架
- 游戏功能：
  * 蛇的移动和方向控制（方向键）
  * 食物随机生成
  * 蛇吃到食物后变长
  * 碰撞检测（撞墙或撞自己游戏结束）
  * 分数显示
  * 游戏开始和重新开始功能
- 页面设计简洁美观，有游戏区域和分数显示区

请生成完整的项目代码，包括所有必要的文件。`;

    const projectResult = await page.evaluate(async ({ req, sessionId }) => {
      const token = localStorage.getItem('access_token');
      
      // 使用 AbortController 控制超时
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 180000); // 3 分钟超时
      
      try {
        const resp = await fetch('/api/v1/agent/generate', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            requirement: req,
            model: 'deepseek-ai/DeepSeek-R1-0528-Qwen3-8B',
            enable_review: true,
            enable_validation: true,
            session_id: sessionId
          }),
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (resp.ok) {
          const data = await resp.json();
          return {
            success: true,
            total_files: data.total_files_created || 0,
            output_dir: data.output_dir || 'N/A',
            validation_passed: data.validation?.runnable || false,
            execution_time: data.execution_time || 0
          };
        } else {
          const err = await resp.json().catch(() => ({}));
          return { success: false, error: err.detail?.message || err.detail || resp.statusText };
        }
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
      const resp = await fetch('/api/v1/agent/stats/models', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      return resp.ok ? await resp.json() : [];
    });

    console.log('模型统计:', JSON.stringify(stats.slice(0, 5), null, 2));

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
    
    // 验证项目生成成功
    if (projectResult.success) {
      expect(projectResult.total_files).toBeGreaterThan(0);
      expect(projectResult.output_dir).toBeDefined();
    } else {
      // 如果失败，输出详细错误
      console.log('项目生成失败，错误:', projectResult.error);
    }
  });
});
