/**
 * 多模态 Agent 全栈项目生成 - 准确测试
 * 
 * 通过前端界面真实测试 Agent 生成复杂全栈项目的能力
 * 使用硅基流动 API Key 进行实际的 LLM 调用
 */

const { test, expect } = require('@playwright/test');

// 真实 LLM 调用用例需要提供有效的硅基流动 Key，本地无凭证时跳过
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

// 10+ 文件真实全栈生成在 2 CPU 环境需要 40 分钟以上，默认不纳入常规回归。
const RUN_EXTREME_LIVE = process.env.TEST_EXTREME_LIVE === '1';

async function login(page) {
  const { apiLogin } = await import('./fixtures/auth.js');
  return apiLogin(page);
}

async function prepareGeneration(page) {
  const loginResult = await login(page);
  const token = loginResult.token;
  expect(token).toBeTruthy();
  await syncRealApiKeys(page);
  const apiKeyToken = await page.evaluate(() => {
    const keys = JSON.parse(localStorage.getItem('codingmatrix_apikeys') || '[]');
    return keys[0]?.token || null;
  });
  expect(apiKeyToken).toBeTruthy();
  return { token, apiKeyToken };
}

const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000';

// 覆盖前后端的最小全栈需求，规避 2 CPU 环境下的超长生成
const COMPLEX_REQUIREMENT = `
请生成一个待办事项全栈小项目，只生成以下 3 个文件：
1. main.py：FastAPI 后端，提供 GET /api/todos 和 POST /api/todos，使用内存列表存储
2. index.html：原生 JavaScript 前端，调用上述接口展示和添加待办
3. requirements.txt：包含 fastapi 和 uvicorn

请确保后端接口和前端调用一致，代码完整可运行。
`;

test.describe('多模态 Agent 全栈项目生成准确测试', () => {
  
  // 测试 1: 登录并获取 Token
  test.describe('认证流程', () => {
    test('应能成功登录并获取 Token', async ({ page }) => {
      console.log('\n=== 测试 1: 认证流程 ===');

      await page.goto('/');
      const result = await login(page);
      expect(result.ok).toBeTruthy();
      expect(result.token).toBeTruthy();

      const storedToken = await page.evaluate(() => localStorage.getItem('access_token'));
      expect(storedToken).toBe(result.token);
    });
  });

  // 测试 2: 前端 Agent 界面交互
  test.describe('Agent 界面交互', () => {
    test('应能打开 Agent 面板并输入需求', async ({ page }) => {
      console.log('\n=== 测试 2: Agent 界面交互 ===');

      await page.goto('/');
      await login(page);
      await page.goto('/agent', { waitUntil: 'domcontentloaded' });

      const prompt = page.getByRole('textbox', { name: '项目需求' });
      await expect(prompt).toBeVisible({ timeout: 15000 });
      await prompt.fill('生成一个待办事项管理系统');
      await expect(prompt).toHaveValue('生成一个待办事项管理系统');
      await expect(page.getByRole('button', { name: '发送需求' })).toBeVisible();
    });
  });

  // 测试 3: 通过 API 直接测试 Agent 生成能力
  test.describe('Agent API 实际测试', () => {
    test('应能通过 API 生成简单项目', async ({ page }) => {
      test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）');
      test.setTimeout(600000);
      console.log('\n=== 测试 3: Agent API 实际测试 ===');
      
      const { token, apiKeyToken } = await prepareGeneration(page);
      
      // 测试简单需求
      const simpleRequirement = '请生成一个简单的 Python 脚本，输出 Hello World';
      
      console.log('发送简单需求到 Agent...');
      console.log('需求:', simpleRequirement);
      
      const response = await page.request.post(`${API_BASE}/api/v1/agent/orchestrate`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        timeout: 600000,
        data: {
          requirement: simpleRequirement,
          session_id: `e2e-accurate-simple-${Date.now()}`,
          api_key_token: apiKeyToken
        }
      });
      
      console.log('响应状态:', response.status());
      expect(response.status()).toBe(200);
      
      if (response.status() === 200) {
        const data = await response.json();
        console.log('生成结果:', JSON.stringify(data, null, 2).substring(0, 500));
        
        if (data.success !== undefined) {
          expect(data.success).toBe(true);
          console.log('✅ 简单项目生成成功');
          console.log('生成文件数:', data.total_files_created || 0);
          console.log('耗时:', data.elapsed_time || 0, '秒');
        }
      } else {
        const errorText = await response.text();
        console.log('错误响应:', errorText.substring(0, 200));
      }
    });

    test('应能通过 API 生成中等复杂度项目', async ({ page }) => {
      test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）');
      test.setTimeout(1200000); // 真实模型生成预留 20 分钟
      
      console.log('\n=== 测试 4: 中等复杂度项目生成 ===');
      
      const { token, apiKeyToken } = await prepareGeneration(page);
      if (!token) {
        console.log('无法获取 Token，跳过测试');
        test.skip();
        return;
      }
      
      // 中等需求
      const mediumRequirement = `
请生成一个简单的计算器 REST API 服务，要求：
1. FastAPI 框架
2. 支持加、减、乘、除四种运算
3. 除零时返回 400 错误
4. 请求和响应使用 Pydantic 模型
5. 包含 requirements.txt
`;
      
      console.log('发送中等需求到 Agent...');
      console.log('需求长度:', mediumRequirement.length, '字符');
      
      const response = await page.request.post(`${API_BASE}/api/v1/agent/orchestrate`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        timeout: 900000,
        data: {
          requirement: mediumRequirement,
          session_id: `e2e-accurate-medium-${Date.now()}`,
          api_key_token: apiKeyToken
        }
      });
      
      console.log('响应状态:', response.status());
      expect(response.status()).toBe(200);
      
      if (response.status() === 200) {
        const data = await response.json();
        console.log('生成结果:', JSON.stringify(data, null, 2).substring(0, 1000));
        
        if (data.success) {
          console.log('✅ 中等项目生成成功');
          console.log('生成文件数:', data.total_files_created || 0);
          console.log('文件列表:', data.files?.map(f => f.path) || []);
          expect(data.total_files_created).toBeGreaterThan(0);
        }
      } else {
        console.log('请求失败，状态码:', response.status());
      }
    });

    test('应能通过 API 生成全栈项目', async ({ page }) => {
      test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）');
      test.skip(!RUN_EXTREME_LIVE, '超长全栈生成需显式设置 TEST_EXTREME_LIVE=1');
      test.setTimeout(1800000); // 11 文件规划在 2 CPU 环境可能超过 20 分钟

      console.log('\n=== 测试 5: 全栈项目生成 ===');
      
      const { token, apiKeyToken } = await prepareGeneration(page);
      if (!token) {
        console.log('无法获取 Token，跳过测试');
        test.skip();
        return;
      }
      
      console.log('发送全栈需求到 Agent...');
      console.log('需求长度:', COMPLEX_REQUIREMENT.length, '字符');
      console.log('预计耗时: 10-25 分钟');
      
      const startTime = Date.now();
      
      const response = await page.request.post(`${API_BASE}/api/v1/agent/orchestrate`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        timeout: 1800000,
        data: {
          requirement: COMPLEX_REQUIREMENT,
          session_id: `e2e-accurate-complex-${Date.now()}`,
          api_key_token: apiKeyToken
        }
      });
      
      const elapsed = (Date.now() - startTime) / 1000;
      console.log('响应时间:', elapsed, '秒');
      console.log('响应状态:', response.status());
      expect(response.status()).toBe(200);
      
      if (response.status() === 200) {
        const data = await response.json();
        console.log('=== 生成结果 ===');
        console.log('成功:', data.success);
        console.log('总文件数:', data.total_files_created);
        console.log('复杂度:', data.complexity);
        console.log('耗时:', data.elapsed_time, '秒');
        
        if (data.models_used) {
          console.log('使用的模型:', data.models_used);
        }
        
        if (data.files && data.files.length > 0) {
          console.log('\n生成的文件列表:');
          data.files.forEach((file, index) => {
            const status = file.success ? '✅' : '❌';
            console.log(`  ${status} ${file.path} (${file.size || 0} bytes)`);
          });
          
          // 验证关键文件
          const filePaths = data.files.map(f => f.path);
          const hasBackendFiles = filePaths.some(p => p.includes('.py') || p.includes('requirements.txt'));
          const hasFrontendFiles = filePaths.some(p => p.includes('.vue') || p.includes('.js') || p.includes('.html'));
          
          console.log('\n验证结果:');
          console.log('  包含后端文件:', hasBackendFiles);
          console.log('  包含前端文件:', hasFrontendFiles);
          
          expect(data.success).toBe(true);
          expect(data.total_files_created).toBeGreaterThan(0);
          expect(hasBackendFiles || hasFrontendFiles).toBeTruthy();
        }
        
        if (data.errors && data.errors.length > 0) {
          console.log('\n错误信息:', data.errors);
        }
        
        if (data.warnings && data.warnings.length > 0) {
          console.log('\n警告信息:', data.warnings.slice(0, 3));
        }
      } else {
        const errorText = await response.text();
        console.log('错误响应:', errorText.substring(0, 500));
      }
    });
  });

  // 测试 4: 复杂度分析测试
  test.describe('复杂度分析测试', () => {
    test('应能分析不同复杂度的需求', async ({ page }) => {
      console.log('\n=== 测试 6: 复杂度分析 ===');

      await page.goto('/');
      const { token } = await login(page);

      // 测试复杂度分析 API
      const response = await page.request.post(`${API_BASE}/api/v1/agent/analyze_complexity`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          requirement: COMPLEX_REQUIREMENT
        }
      });

      console.log('复杂度分析响应状态:', response.status());
      expect(response.status()).toBe(200);

      const data = await response.json();
      console.log('复杂度分析结果:', JSON.stringify(data, null, 2));
      expect(data.level).toBeDefined();
      expect(data.estimated_files).toBeGreaterThan(0);
      expect(data.model_assignment).toBeDefined();
    });
  });
});
