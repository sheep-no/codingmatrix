const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test.describe('Agent 项目生成 SSE 进度显示测试', () => {
  test.describe.configure({ project: 'chromium' });

  test('通过 UI 触发项目生成并验证 SSE 进度事件', async ({ page }) => {
    test.setTimeout(600000); // 10 分钟超时

    const timeline = [];
    const sseEvents = [];
    let startTime;

    // 拦截 SSE 流式响应
    page.on('response', async (response) => {
      const url = response.url();
      if (url.includes('/orchestrate/stream')) {
        const status = response.status();
        timeline.push({ time: Date.now() - startTime, type: 'sse_response', status });
        console.log(`\n[SSE] 响应状态: ${status}`);

        // 尝试读取流式内容
        try {
          const body = await response.text();
          const lines = body.split('\n').filter(l => l.startsWith('data: '));
          for (const line of lines) {
            try {
              const data = JSON.parse(line.substring(6));
              sseEvents.push({
                time: Date.now() - startTime,
                type: data.type,
                data: data.data || {}
              });
            } catch (e) {
              // 忽略解析错误
            }
          }
        } catch (e) {
          console.log('[SSE] 无法读取响应体（流式传输中）');
        }
      }
    });

    // 监听控制台日志
    page.on('console', (msg) => {
      if (msg.text().includes('解析流数据失败')) {
        console.log('[WARN]', msg.text());
      }
    });

    // ========== 步骤 1: 登录 ==========
    console.log('\n=== 步骤 1: 登录 ===');
    startTime = Date.now();
    await page.goto(BASE_URL);
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
    expect(loginResult.success).toBe(true);
    timeline.push({ time: Date.now() - startTime, type: 'login_complete' });

    // ========== 步骤 2: 打开项目生成对话框 ==========
    console.log('\n=== 步骤 2: 打开项目生成对话框 ===');

    // 尝试多种方式打开项目生成器
    // 方式 1: 查找"项目生成"按钮或标签
    const projectButtons = await page.$$('text=项目生成');
    if (projectButtons.length > 0) {
      await projectButtons[0].click();
      await page.waitForTimeout(1000);
    }

    // 方式 2: 通过 AI Agent 组件的 Project tab
    const agentPanel = await page.$('.agent-panel');
    if (agentPanel) {
      const projectTab = await page.$('button:has-text("项目生成")');
      if (projectTab) {
        await projectTab.click();
        await page.waitForTimeout(500);
      }
    }

    // 方式 3: 直接通过 evaluate 调用组件方法
    await page.evaluate(() => {
      // 尝试触发 ProjectGenerator 组件
      const event = new CustomEvent('open-project-generator');
      window.dispatchEvent(event);
    });

    await page.waitForTimeout(1000);

    // 检查对话框是否可见
    const dialogVisible = await page.evaluate(() => {
      const overlay = document.querySelector('.project-generator-overlay');
      return overlay && overlay.offsetParent !== null;
    });

    console.log('项目生成对话框可见:', dialogVisible);

    if (!dialogVisible) {
      console.log('对话框未显示，尝试直接在页面上查找输入框');
      // 查找页面上的需求输入区域
      const hasProjectInput = await page.$('textarea[placeholder*="项目"]');
      if (hasProjectInput) {
        console.log('找到项目输入框，使用 AiAgent 的 generateProject 方法');
        // 使用 AiAgent 组件的 generateProject 方法（非 SSE 路径）
        // 但我们需要测试 SSE，所以直接调用 API
      }
    }

    timeline.push({ time: Date.now() - startTime, type: 'dialog_opened', visible: dialogVisible });

    // ========== 步骤 3: 直接调用 SSE API 进行测试 ==========
    console.log('\n=== 步骤 3: 调用 SSE API ===');

    const requirement = `生成一个简单的计算器网页。

技术要求：
- 纯 HTML + CSS + JavaScript（单文件）
- 支持加减乘除基本运算
- 界面简洁美观`;

    const sseResult = await page.evaluate(async ({ req }) => {
      const token = localStorage.getItem('access_token');
      const events = [];

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 分钟超时

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
            enable_error_recovery: true,
            enable_memory: true,
            incremental: false,
            require_approval: false
          }),
          signal: controller.signal
        });

        if (!resp.ok) {
          clearTimeout(timeoutId);
          const err = await resp.json().catch(() => ({}));
          return {
            success: false,
            error: err.detail?.message || err.detail || resp.statusText,
            events: []
          };
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.substring(6));
                events.push({
                  type: data.type,
                  data: data.data || {},
                  timestamp: Date.now()
                });

                // 如果遇到 done 或 error，提前结束
                if (data.type === 'done' || data.type === 'error') {
                  clearTimeout(timeoutId);
                  return {
                    success: data.type === 'done',
                    events: events,
                    finalData: data.data
                  };
                }
              } catch (e) {
                // 忽略解析错误
              }
            }
          }
        }

        clearTimeout(timeoutId);
        return {
          success: true,
          events: events,
          finalData: null
        };
      } catch (error) {
        clearTimeout(timeoutId);
        return {
          success: false,
          error: error.message,
          events: events
        };
      }
    }, { req: requirement });

    timeline.push({ time: Date.now() - startTime, type: 'sse_call_complete' });

    // ========== 步骤 4: 分析结果 ==========
    console.log('\n========== SSE 事件分析 ==========');
    console.log(`SSE 调用成功: ${sseResult.success}`);
    console.log(`接收事件数: ${sseResult.events.length}`);

    if (!sseResult.success) {
      console.log(`错误: ${sseResult.error}`);
    }

    // 按类型分组统计
    const eventTypes = {};
    for (const event of sseResult.events) {
      eventTypes[event.type] = (eventTypes[event.type] || 0) + 1;
    }

    console.log('\n事件类型分布:');
    for (const [type, count] of Object.entries(eventTypes)) {
      console.log(`  ${type}: ${count} 次`);
    }

    // 显示关键事件时间线
    console.log('\n关键事件时间线:');
    const keyEvents = sseResult.events.filter(e =>
      ['progress', 'done', 'error', 'cache_hit', 'cache_loaded'].includes(e.type)
    );
    for (const event of keyEvents.slice(0, 20)) {
      const data = event.data;
      let detail = '';
      if (event.type === 'progress') {
        detail = `${data.step} (${data.current}/${data.total})`;
        if (data.file_path) detail += ` - ${data.file_path}`;
      } else if (event.type === 'done') {
        detail = `文件数: ${data.total_files_created || 0}, 目录: ${data.output_dir || 'N/A'}`;
      } else if (event.type === 'error') {
        detail = data.error || data.message || '';
      }
      console.log(`  [${event.type}] ${detail}`);
    }

    // 验证结果
    console.log('\n========== 断言验证 ==========');

    // 验证至少收到一些事件
    expect(sseResult.events.length).toBeGreaterThan(0);

    // 验证有 progress 事件
    const hasProgress = sseResult.events.some(e => e.type === 'progress');
    console.log(`包含 progress 事件: ${hasProgress}`);
    expect(hasProgress).toBe(true);

    // 验证最终成功或失败原因
    if (sseResult.success) {
      console.log('项目生成成功!');
      if (sseResult.finalData) {
        console.log(`  输出目录: ${sseResult.finalData.output_dir || 'N/A'}`);
        console.log(`  文件数: ${sseResult.finalData.total_files_created || 0}`);
      }
    } else {
      console.log(`项目生成失败: ${sseResult.error}`);
    }

    // 输出完整时间线
    console.log('\n========== 完整时间线 ==========');
    timeline.forEach((event, index) => {
      console.log(`${index + 1}. [+${event.time}ms] ${event.type}`);
    });

    console.log(`\n总耗时: ${Date.now() - startTime}ms (${((Date.now() - startTime) / 1000).toFixed(1)}s)`);
  });
});
