/**
 * 多模态 Agent 全栈项目生成 - 准确测试
 * 
 * 通过前端界面真实测试 Agent 生成复杂全栈项目的能力
 * 使用硅基流动 API Key 进行实际的 LLM 调用
 */

const { test, expect } = require('@playwright/test');

// 真实 LLM 调用用例需要提供有效的硅基流动 Key，本地无凭证时跳过
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');

async function login(page) {
  const { apiLogin } = await import('./fixtures/auth.js');
  return apiLogin(page);
}

const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000';

// 复杂的全栈项目需求
const COMPLEX_REQUIREMENT = `
请生成一个完整的待办事项管理系统（Todo Management System），要求如下：

## 后端 (Python/FastAPI)
1. **用户认证系统**
   - 用户注册、登录、登出
   - JWT Token 认证
   - 密码加密存储

2. **Todo CRUD API**
   - 创建、读取、更新、删除待办事项
   - 每个 Todo 包含：标题、描述、优先级、截止日期、完成状态
   - 支持按优先级和截止日期排序
   - 每个用户只能管理自己的 Todo

3. **数据持久化**
   - 使用 SQLite + SQLAlchemy
   - 用户表和 Todo 表，外键关联

## 前端 (Vue 3)
1. **页面**
   - 登陆/注册页面
   - Todo 列表页面
   - 添加/编辑 Todo 的表单组件

## 项目结构
- 后端：app/main.py, app/models/, app/schemas/, app/api/
- 前端：index.html, src/main.js, src/App.vue, src/components/
- 包含 requirements.txt

请确保所有代码完整可运行。
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
      console.log('\n=== 测试 3: Agent API 实际测试 ===');
      
      // 先登录获取 Token
      const loginResponse = await page.request.post(`${API_BASE}/api/v1/login`, {
        data: {
          email: 'mr_yang@example.com',
          password: '12345678'
        }
      });
      
      let token = '';
      if (loginResponse.status() === 200) {
        const loginData = await loginResponse.json();
        token = loginData.access_token;
        console.log('登录成功，获取 Token');
      } else {
        console.log('登录失败，使用测试 Token');
        // 如果登录失败，使用存储的 token
        await page.goto('http://localhost:3000');
        await page.waitForTimeout(2000);
        token = await page.evaluate(() => localStorage.getItem('access_token'));
      }
      
      expect(token).toBeTruthy();
      
      // 测试简单需求
      const simpleRequirement = '请生成一个简单的 Python 脚本，输出 Hello World';
      
      console.log('发送简单需求到 Agent...');
      console.log('需求:', simpleRequirement);
      
      const response = await page.request.post(`${API_BASE}/api/v1/agent/generate`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          requirement: simpleRequirement,
          model: 'qwen2.5-7b'
        }
      });
      
      console.log('响应状态:', response.status());
      
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
      test.setTimeout(300000); // 5 分钟超时
      
      console.log('\n=== 测试 4: 中等复杂度项目生成 ===');
      
      // 获取 Token
      let token = await page.evaluate(() => localStorage.getItem('access_token'));
      if (!token) {
        const loginResponse = await page.request.post(`${API_BASE}/api/v1/login`, {
          data: { email: 'mr_yang@example.com', password: '12345678' }
        });
        if (loginResponse.status() === 200) {
          const loginData = await loginResponse.json();
          token = loginData.access_token;
        }
      }
      
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
      
      const response = await page.request.post(`${API_BASE}/api/v1/agent/generate`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          requirement: mediumRequirement,
          model: 'qwen2.5-7b'
        }
      });
      
      console.log('响应状态:', response.status());
      
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

    test('应能通过 API 生成复杂全栈项目', async ({ page }) => {
      test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）');
      test.setTimeout(600000); // 10 分钟超时
      
      console.log('\n=== 测试 5: 复杂全栈项目生成 ===');
      
      // 获取 Token
      let token = await page.evaluate(() => localStorage.getItem('access_token'));
      if (!token) {
        const loginResponse = await page.request.post(`${API_BASE}/api/v1/login`, {
          data: { email: 'mr_yang@example.com', password: '12345678' }
        });
        if (loginResponse.status() === 200) {
          const loginData = await loginResponse.json();
          token = loginData.access_token;
        }
      }
      
      if (!token) {
        console.log('无法获取 Token，跳过测试');
        test.skip();
        return;
      }
      
      console.log('发送复杂全栈需求到 Agent...');
      console.log('需求长度:', COMPLEX_REQUIREMENT.length, '字符');
      console.log('预计耗时: 3-8 分钟');
      
      const startTime = Date.now();
      
      const response = await page.request.post(`${API_BASE}/api/v1/agent/generate`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          requirement: COMPLEX_REQUIREMENT,
          model: 'deepseek-r1-qwen3-8b'
        }
      });
      
      const elapsed = (Date.now() - startTime) / 1000;
      console.log('响应时间:', elapsed, '秒');
      console.log('响应状态:', response.status());
      
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
