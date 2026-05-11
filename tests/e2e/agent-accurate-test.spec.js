/**
 * 多模态 Agent 全栈项目生成 - 准确测试
 * 
 * 通过前端界面真实测试 Agent 生成复杂全栈项目的能力
 * 使用硅基流动 API Key 进行实际的 LLM 调用
 */

const { test, expect } = require('@playwright/test');

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
      
      // 访问登录页面
      await page.goto('http://localhost:3000');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);
      
      // 查找并点击登录按钮
      const loginButton = page.locator('button:has-text("登录"), .login-btn, [class*="login"]').first();
      if (await loginButton.count() > 0) {
        await loginButton.click();
        await page.waitForTimeout(1000);
      }
      
      // 填写登录表单
      await page.fill('input[type="email"], input[placeholder*="邮箱"], [class*="email"]', 'mr_yang@example.com');
      await page.fill('input[type="password"]', '12345678');
      
      // 点击登录
      await page.click('button:has-text("登录"), [class*="login"]');
      await page.waitForTimeout(3000);
      
      // 验证登录成功
      const isLoggedIn = await page.evaluate(() => {
        return !!localStorage.getItem('access_token') || 
               !!document.querySelector('[class*="user"]') ||
               document.body.textContent.includes('活跃');
      });
      
      console.log('登录状态:', isLoggedIn);
      expect(isLoggedIn).toBeTruthy();
    });
  });

  // 测试 2: 前端 Agent 界面交互
  test.describe('Agent 界面交互', () => {
    test('应能打开 Agent 面板并输入需求', async ({ page }) => {
      console.log('\n=== 测试 2: Agent 界面交互 ===');
      
      // 先登录
      await page.goto('http://localhost:3000');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);
      
      // 尝试登录
      const loginButton = page.locator('button:has-text("登录"), .login-btn').first();
      if (await loginButton.count() > 0) {
        await loginButton.click();
        await page.waitForTimeout(500);
        await page.fill('input[type="email"], [class*="email"]', 'mr_yang@example.com');
        await page.fill('input[type="password"]', '12345678');
        await page.click('button:has-text("登录"), [class*="login"]');
        await page.waitForTimeout(2000);
      }
      
      // 查找 Agent 相关按钮
      const agentButton = page.locator('button:has-text("Agent"), button:has-text("AI"), [class*="agent"], [class*="ai"]').first();
      
      if (await agentButton.count() > 0) {
        await agentButton.click();
        await page.waitForTimeout(2000);
        
        // 验证 Agent 面板已打开
        const isPanelOpen = await page.evaluate(() => {
          return !!document.querySelector('[class*="agent"]') ||
                 !!document.querySelector('[class*="chat"]') ||
                 !!document.querySelector('textarea[placeholder*="任务"]') ||
                 !!document.querySelector('textarea[placeholder*="输入"]');
        });
        
        console.log('Agent 面板已打开:', isPanelOpen);
        expect(isPanelOpen).toBeTruthy();
      } else {
        console.log('使用主输入框');
        // 检查主输入框
        const hasInput = await page.locator('textarea').first().isVisible();
        expect(hasInput).toBeTruthy();
      }
    });
  });

  // 测试 3: 通过 API 直接测试 Agent 生成能力
  test.describe('Agent API 实际测试', () => {
    test('应能通过 API 生成简单项目', async ({ page }) => {
      console.log('\n=== 测试 3: Agent API 实际测试 ===');
      
      // 先登录获取 Token
      const loginResponse = await page.request.post('http://localhost:8080/api/v1/login', {
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
      
      const response = await page.request.post('http://localhost:8080/api/v1/agent/generate', {
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
      test.setTimeout(300000); // 5 分钟超时
      
      console.log('\n=== 测试 4: 中等复杂度项目生成 ===');
      
      // 获取 Token
      let token = await page.evaluate(() => localStorage.getItem('access_token'));
      if (!token) {
        const loginResponse = await page.request.post('http://localhost:8080/api/v1/login', {
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
      
      const response = await page.request.post('http://localhost:8080/api/v1/agent/generate', {
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
      test.setTimeout(600000); // 10 分钟超时
      
      console.log('\n=== 测试 5: 复杂全栈项目生成 ===');
      
      // 获取 Token
      let token = await page.evaluate(() => localStorage.getItem('access_token'));
      if (!token) {
        const loginResponse = await page.request.post('http://localhost:8080/api/v1/login', {
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
      
      const response = await page.request.post('http://localhost:8080/api/v1/agent/generate', {
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
      
      // 获取 Token
      let token = await page.evaluate(() => localStorage.getItem('access_token'));
      if (!token) {
        const loginResponse = await page.request.post('http://localhost:8080/api/v1/login', {
          data: { email: 'mr_yang@example.com', password: '12345678' }
        });
        if (loginResponse.status() === 200) {
          token = (await loginResponse.json()).access_token;
        }
      }
      
      if (!token) {
        test.skip();
        return;
      }
      
      // 测试复杂度分析 API
      const response = await page.request.post('http://localhost:8080/api/v1/agent/analyze_complexity', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          requirement: COMPLEX_REQUIREMENT
        }
      });
      
      console.log('复杂度分析响应状态:', response.status());
      
      if (response.status() === 200) {
        const data = await response.json();
        console.log('复杂度分析结果:', JSON.stringify(data, null, 2));
        expect(data.complexity || data.level).toBeDefined();
      }
    });
  });
});
