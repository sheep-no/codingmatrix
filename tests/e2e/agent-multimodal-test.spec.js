const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test.describe('多模态 Agent 性能和流程跟踪测试', () => {
  test.describe.configure({ project: 'chromium' });

  test('发送复杂需求并完整跟踪 Agent 流程', async ({ page }) => {
    test.setTimeout(180000); // 设置 3 分钟超时
    
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

    page.on('response', async (response) => {
      const url = response.url();
      if (url.includes('/api/v1/agent/')) {
        const duration = Date.now() - startTime;
        timeline.push({
          time: duration,
          type: 'response',
          url: url,
          status: response.status()
        });
      }
    });

    // 第一步：登录
    console.log('\n=== 步骤 1: 登录获取认证 ===');
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await page.evaluate(async ({ email, password }) => {
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

    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // 第二步：测试流式响应模式
    console.log('\n=== 步骤 2: 测试流式响应模式 ===');
    
    startTime = Date.now();
    const streamTask = `请解释什么是 Python 装饰器，并给出一个实用的例子`;

    const streamResult = await page.evaluate(async (task) => {
      const token = localStorage.getItem('access_token');
      const events = [];
      
      // 创建超时控制
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 90000); // 90 秒超时
      
      try {
        const resp = await fetch('/api/v1/agent/process/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            task: task,
            prefer_fast: false
          }),
          signal: controller.signal
        });

        if (!resp.ok) {
          clearTimeout(timeoutId);
          return { success: false, error: await resp.text() };
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let eventCount = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                eventCount++;
                events.push({
                  type: data.type,
                  timestamp: Date.now(),
                  data: data.data
                });
              } catch (e) {
                // 忽略解析错误
              }
            }
          }
        }

        clearTimeout(timeoutId);
        return {
          success: true,
          event_count: eventCount,
          events: events.slice(0, 15) // 返回前 15 个事件
        };
      } catch (error) {
        clearTimeout(timeoutId);
        return {
          success: false,
          error: error.message,
          event_count: events.length,
          events: events.slice(0, 10)
        };
      }
    }, streamTask);

    const streamDuration = Date.now() - startTime;
    console.log('流式响应结果:', JSON.stringify(streamResult, null, 2));
    console.log(`流式处理耗时: ${streamDuration}ms`);

    timeline.push({ time: streamDuration, type: 'stream_complete', data: streamResult });

    // 第三步：测试标准模式（非流式）
    console.log('\n=== 步骤 3: 测试标准模式 ===');
    
    const standardTask = `Python 中列表和元组有什么区别？`;

    const standardStartTime = Date.now();
    const standardResult = await page.evaluate(async (task) => {
      const token = localStorage.getItem('access_token');
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000);
      
      try {
        const resp = await fetch('/api/v1/agent/process', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            task: task,
            prefer_fast: true
          }),
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (resp.ok) {
          const data = await resp.json();
          return {
            success: true,
            task_type: data.task_type,
            model_used: data.model_used,
            steps: data.steps,
            has_results: !!data.results
          };
        } else {
          const err = await resp.json().catch(() => ({}));
          return { success: false, error: err.detail || resp.statusText };
        }
      } catch (error) {
        clearTimeout(timeoutId);
        return { success: false, error: error.message };
      }
    }, standardTask);

    const standardDuration = Date.now() - standardStartTime;
    console.log('标准模式结果:', JSON.stringify(standardResult, null, 2));
    console.log(`标准模式耗时: ${standardDuration}ms`);

    timeline.push({ time: standardDuration, type: 'standard_complete', data: standardResult });

    // 第四步：收集统计信息
    console.log('\n=== 步骤 4: 收集统计信息 ===');
    
    const stats = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token');
      
      const resp = await fetch('/api/v1/agent/stats/models', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (resp.ok) {
        return await resp.json();
      }
      return [];
    });

    console.log('模型统计:', JSON.stringify(stats.slice(0, 3), null, 2)); // 只显示前 3 个

    const endTime = Date.now();
    const totalDuration = endTime - startTime;

    // 输出完整的时间线
    console.log('\n========== 完整时间线 ==========');
    timeline.forEach((event, index) => {
      console.log(`${index + 1}. [+${event.time}ms] ${event.type}`);
      if (event.data && event.data.event_count !== undefined) {
        console.log(`   事件数: ${event.data.event_count}`);
      }
      if (event.data && event.data.model_used) {
        console.log(`   使用模型: ${event.data.model_used}`);
      }
    });

    console.log('\n========== API 调用记录 ==========');
    apiCalls.forEach((call, index) => {
      console.log(`${index + 1}. ${call.method} ${new URL(call.url).pathname}`);
      if (call.postData && call.postData.task) {
        console.log(`   任务: ${call.postData.task.substring(0, 80)}...`);
      }
    });

    console.log('\n========== 性能汇总 ==========');
    console.log(`总耗时: ${totalDuration}ms`);
    console.log(`API 调用次数: ${apiCalls.length}`);
    console.log(`时间线事件数: ${timeline.length}`);
    console.log(`流式响应事件: ${streamResult.event_count || 0}`);
    console.log(`标准模式成功: ${standardResult.success}`);
    console.log(`模型统计记录: ${stats.length}`);

    // 断言
    expect(totalDuration).toBeGreaterThan(0);
    expect(apiCalls.length).toBeGreaterThan(0);
    
    // 流式测试验证：至少收到 task_routed 和 model_selected 事件
    expect(streamResult.event_count).toBeGreaterThanOrEqual(2);
    
    // 验证事件类型
    const eventTypes = streamResult.events?.map(e => e.type) || [];
    expect(eventTypes).toContain('task_routed');
    expect(eventTypes).toContain('model_selected');
  });
});
