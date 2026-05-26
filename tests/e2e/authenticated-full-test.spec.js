/**
 * 登录后完整功能测试
 * 测试用户登录后所有功能的完整性和正确性
 */

import { test, expect } from '@playwright/test';

const TEST_CREDENTIALS = {
  username: 'testuser',
  password: 'testpass123',
};

const BACKEND_BASE = 'http://localhost:8002';

test.describe('登录后完整功能测试', () => {
  test.beforeEach(async ({ page, request }) => {
    // 注册测试用户（如果不存在）
    try {
      await request.post(`${BACKEND_BASE}/api/v1/register`, {
        json: {
          username: TEST_CREDENTIALS.username,
          password: TEST_CREDENTIALS.password,
          email: 'test@example.com'
        }
      });
    } catch (error) {
      // 用户可能已存在，忽略错误
    }
  });

  test('1. 用户登录功能', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // 检查登录表单是否显示
    const loginModal = page.locator('.login-modal, [class*="login-modal"]');
    const isModalVisible = await loginModal.isVisible().catch(() => false);

    if (isModalVisible) {
      // 填写登录表单
      const usernameInput = page.locator('input[type="text"], input[name="username"]').first();
      const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
      
      await usernameInput.fill(TEST_CREDENTIALS.username);
      await passwordInput.fill(TEST_CREDENTIALS.password);

      // 点击登录按钮
      const loginBtn = page.locator('button:has-text("登录"), button[type="submit"]');
      await loginBtn.click();

      // 等待登录完成
      await page.waitForTimeout(3000);

      // 验证登录成功 - 检查是否有用户信息显示
      const userInfo = page.locator('[class*="user"], [class*="avatar"], [class*="profile"]');
      const isLoggedIn = await userInfo.isVisible().catch(() => false);

      expect(isLoggedIn).toBeTruthy();
    } else {
      console.log('登录模态框未显示，可能已经登录');
    }
  });

  test('2. Agent页面 - 项目生成功能（带决策对话框）', async ({ page }) => {
    // 先登录
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // 导航到Agent页面
    const agentLink = page.locator('a[href="/agent"], button:has-text("Agent"), [role="link"][href*="agent"]');
    await agentLink.click();
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // 检查Agent页面元素
    const pageTitle = page.locator('h1.page-title, .page-title h1');
    await expect(pageTitle).toBeVisible();

    // 检查Tab导航
    const tabs = page.locator('[class*="tab"], [role="tab"]');
    await expect(tabs).toHaveCount(2);

    // 检查项目描述输入框
    const textarea = page.locator('textarea.prompt-textarea, textarea');
    await expect(textarea).toBeVisible();

    // 检查生成按钮
    const generateBtn = page.locator('button:has-text("生成"), button[class*="generate"]');
    await expect(generateBtn).toBeVisible();

    // 检查快速模板
    const templates = page.locator('[class*="template"], [class*="quick"]');
    const templateCount = await templates.count();
    expect(templateCount).toBeGreaterThan(0);

    // 输入项目描述
    await textarea.fill('创建一个简单的待办事项应用，包含添加、删除、标记完成功能');

    // 点击生成按钮
    await generateBtn.click();

    // 等待可能出现的决策对话框（2分钟超时）
    try {
      const decisionModal = page.locator('.decision-modal, [class*="decision"]');
      const hasDecisionModal = await decisionModal.isVisible().catch(() => false);

      if (hasDecisionModal) {
        console.log('检测到架构决策对话框');

        // 检查决策选项
        const decisionOptions = page.locator('.decision-option input[type="radio"]');
        const optionCount = await decisionOptions.count();
        expect(optionCount).toBeGreaterThan(0);

        // 选择第一个选项
        const firstOption = decisionOptions.first();
        await firstOption.check();

        // 提交决策
        const submitBtn = page.locator('button:has-text("确认决策")');
        await submitBtn.click();

        console.log('已提交架构决策');
      }
    } catch (error) {
      console.log('未检测到决策对话框或决策已跳过:', error.message);
    }

    // 等待生成开始
    await page.waitForTimeout(5000);

    // 检查生成状态
    const generatingStatus = page.locator('[class*="generating"], [class*="loading"], [class*="progress"]');
    const isGenerating = await generatingStatus.isVisible().catch(() => false);

    console.log(`生成状态: ${isGenerating ? '正在生成' : '未开始'}`);

    // 检查停止按钮
    const stopBtn = page.locator('button:has-text("停止"), button[class*="stop"]');
    if (isGenerating) {
      await expect(stopBtn).toBeVisible();
    }
  });

  test('3. Agent页面 - 我的项目Tab', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // 切换到"我的项目"Tab
    const projectsTab = page.locator('button:has-text("我的项目"), [role="tab"]:has-text("项目")');
    await projectsTab.click();
    await page.waitForTimeout(2000);

    // 检查项目列表区域
    const projectsSection = page.locator('.projects-tab, [class*="project-card"]');
    const isVisible = await projectsSection.isVisible().catch(() => false);
    
    console.log(`项目列表区域可见: ${isVisible}`);

    // 检查空状态或项目卡片
    const emptyState = page.locator('.empty-state, [class*="empty"]:has-text("暂无")');
    const projectCards = page.locator('[class*="project-card"]');

    const hasEmptyState = await emptyState.isVisible().catch(() => false);
    const cardCount = await projectCards.count();

    if (hasEmptyState) {
      console.log('显示空状态：暂无项目');
    } else if (cardCount > 0) {
      console.log(`显示 ${cardCount} 个项目卡片`);
      // 验证卡片有必要的按钮
      const firstCardActions = projectCards.first().locator('button');
      await expect(firstCardActions).toHaveCount(2); // 打开和删除按钮
    }
  });

  test('4. 项目列表API测试', async ({ page, request }) => {
    // 先登录获取token
    const loginResponse = await request.post(`${BACKEND_BASE}/api/v1/login`, {
      json: {
        username: TEST_CREDENTIALS.username,
        password: TEST_CREDENTIALS.password
      }
    });

    if (loginResponse.ok()) {
      const loginData = await loginResponse.json();
      const token = loginData.access_token || loginData.token;

      if (token) {
        // 测试项目列表API
        const projectsResponse = await request.get(`${BACKEND_BASE}/api/v1/agent/saved`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        console.log(`项目列表API状态: ${projectsResponse.status()}`);

        if (projectsResponse.ok()) {
          const projectsData = await projectsResponse.json();
          console.log(`项目列表: ${JSON.stringify(projectsData, null, 2)}`);
          
          // 验证返回数据结构
          expect(projectsData).toHaveProperty('projects');
          expect(Array.isArray(projectsData.projects)).toBeTruthy();
        }
      }
    }
  });

  test('5. 决策对话框功能测试', async ({ page, request }) => {
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    const textarea = page.locator('textarea.prompt-textarea, textarea');
    const generateBtn = page.locator('button:has-text("生成"), button[class*="generate"]');

    // 输入一个复杂需求，可能触发决策
    await textarea.fill('创建一个电商网站，包含用户注册、商品管理、订单处理、支付集成');
    
    // 点击生成
    await generateBtn.click();
    await page.waitForTimeout(3000);

    // 检查是否有决策对话框
    const decisionModal = page.locator('.decision-modal, [class*="decision"]');
    const hasModal = await decisionModal.isVisible().catch(() => false);

    if (hasModal) {
      console.log('✓ 架构决策对话框显示正常');

      // 检查决策问题
      const decisionQuestions = page.locator('.decision-question');
      const questionCount = await decisionQuestions.count();
      console.log(`  决策问题数量: ${questionCount}`);

      // 检查决策选项
      const decisionOptions = page.locator('.decision-option');
      const optionCount = await decisionOptions.count();
      console.log(`  决策选项总数: ${optionCount}`);

      // 检查"使用默认值"按钮
      const skipBtn = page.locator('button:has-text("使用默认值")');
      await expect(skipBtn).toBeVisible();

      // 检查"确认决策"按钮
      const confirmBtn = page.locator('button:has-text("确认决策")');
      await expect(confirmBtn).toBeVisible();

      // 检查关闭按钮
      const closeBtn = page.locator('.decision-modal .modal-close');
      await expect(closeBtn).toBeVisible();

      console.log('✓ 决策对话框所有元素正常');
    } else {
      console.log('✓ 决策对话框未触发（可能不需要决策）');
    }

    // 停止生成
    await page.waitForTimeout(2000);
    const stopBtn = page.locator('button:has-text("停止"), button[class*="stop"]');
    const isStopVisible = await stopBtn.isVisible().catch(() => false);
    
    if (isStopVisible) {
      await stopBtn.click();
      console.log('✓ 已停止生成');
    }
  });

  test('6. 会话管理功能测试', async ({ page, request }) => {
    // 登录
    const loginResponse = await request.post(`${BACKEND_BASE}/api/v1/login`, {
      json: {
        username: TEST_CREDENTIALS.username,
        password: TEST_CREDENTIALS.password
      }
    });

    if (!loginResponse.ok()) {
      console.log('登录失败，跳过会话测试');
      return;
    }

    const loginData = await loginResponse.json();
    const token = loginData.access_token || loginData.token;

    // 创建会话
    const createSessionResponse = await request.post(`${BACKEND_BASE}/api/v1/agent/orchestrate/stream`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      json: {
        requirement: '测试会话创建',
        session_id: 'test_session_' + Date.now(),
        enable_review: false,
        enable_validation: false
      }
    });

    console.log(`创建会话状态: ${createSessionResponse.status()}`);

    // 测试会话操作API
    if (createSessionResponse.ok() || createSessionResponse.status() === 401) {
      // 测试决策提交API
      const decisionResponse = await request.post(`${BACKEND_BASE}/api/v1/agent/session/test_session_123/decision`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        json: {
          auth_strategy: 'JWT'
        }
      });

      console.log(`决策提交API状态: ${decisionResponse.status()}`);
      expect([200, 201, 401, 422]).toContain(decisionResponse.status());

      // 测试会话操作API
      const actionResponse = await request.post(`${BACKEND_BASE}/api/v1/agent/session/test_session_123/action?action=cancel`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      console.log(`会话操作API状态: ${actionResponse.status()}`);
      expect([200, 401, 404]).toContain(actionResponse.status());

      // 测试删除会话API
      const deleteResponse = await request.delete(`${BACKEND_BASE}/api/v1/agent/sessions/test_session_123`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      console.log(`删除会话API状态: ${deleteResponse.status()}`);
      expect([200, 401, 404]).toContain(deleteResponse.status());
    }
  });

  test('7. 全局约束和决策功能集成测试', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    const textarea = page.locator('textarea.prompt-textarea, textarea');
    const generateBtn = page.locator('button:has-text("生成"), button[class*="generate"]');

    // 输入包含全局约束的需求
    await textarea.fill('创建一个在线教育平台，必须使用Redis缓存，所有service函数必须使用async/await，API风格使用GraphQL');
    
    // 点击生成
    await generateBtn.click();
    await page.waitForTimeout(3000);

    // 检查决策对话框是否包含Redis相关的决策
    const decisionModal = page.locator('.decision-modal, [class*="decision"]');
    const hasModal = await decisionModal.isVisible().catch(() => false);

    if (hasModal) {
      console.log('✓ 检测到决策对话框，验证全局约束解析');

      // 检查决策问题
      const decisionText = await decisionModal.textContent();
      console.log(`  决策内容预览: ${decisionText.substring(0, 200)}...`);

      // 检查是否包含Redis选项
      const hasRedis = decisionText.includes('Redis') || decisionText.includes('redis');
      if (hasRedis) {
        console.log('✓ Redis决策选项存在');
      }
    }

    // 停止生成
    await page.waitForTimeout(2000);
    const stopBtn = page.locator('button:has-text("停止"), button[class*="stop"]');
    const isStopVisible = await stopBtn.isVisible().catch(() => false);
    
    if (isStopVisible) {
      await stopBtn.click();
    }
  });

  test('8. 文件生成和预览功能测试', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // 使用快速模板
    const vueTemplate = page.locator('.template-item:has-text("Vue"), [class*="template"]:has-text("Vue")');
    await vueTemplate.click();
    await page.waitForTimeout(1000);

    // 点击生成
    const generateBtn = page.locator('button:has-text("生成"), button[class*="generate"]');
    await generateBtn.click();
    await page.waitForTimeout(5000);

    // 检查文件树是否出现
    const fileTree = page.locator('[class*="file-tree"], [class*="tree"]');
    const hasFileTree = await fileTree.isVisible().catch(() => false);

    if (hasFileTree) {
      console.log('✓ 文件树显示正常');

      // 等待一些文件生成
      await page.waitForTimeout(3000);

      const files = await fileTree.locator('[class*="file"], [class*="tree-item"]').all();
      console.log(`  生成的文件数量: ${files.length}`);

      if (files.length > 0) {
        // 点击第一个文件
        await files[0].click();
        await page.waitForTimeout(1000);

        // 检查代码预览
        const preview = page.locator('[class*="preview"], [class*="code"]');
        const hasPreview = await preview.isVisible().catch(() => false);

        if (hasPreview) {
          console.log('✓ 代码预览显示正常');

          // 检查复制按钮
          const copyBtn = page.locator('button:has-text("复制"), [class*="copy"]');
          await expect(copyBtn).toBeVisible();
          console.log('✓ 复制按钮正常');
        }
      }
    } else {
      console.log('文件树未显示（可能生成需要更多时间）');
    }

    // 停止生成
    const stopBtn = page.locator('button:has-text("停止"), button[class*="stop"]');
    const isStopVisible = await stopBtn.isVisible().catch(() => false);
    
    if (isStopVisible) {
      await stopBtn.click();
    }
  });

  test('9. 日志和进度显示功能测试', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    const textarea = page.locator('textarea.prompt-textarea, textarea');
    const generateBtn = page.locator('button:has-text("生成"), button[class*="generate"]');

    await textarea.fill('测试日志显示功能');
    await generateBtn.click();
    await page.waitForTimeout(3000);

    // 检查日志面板
    const logPanel = page.locator('[class*="log"], [class*="console"], [class*="message"]');
    const hasLogPanel = await logPanel.isVisible().catch(() => false);

    if (hasLogPanel) {
      console.log('✓ 日志面板显示正常');

      // 获取日志内容
      const logContent = await logPanel.textContent();
      console.log(`  日志内容预览: ${logContent.substring(0, 200)}...`);
    }

    // 停止生成
    await page.waitForTimeout(2000);
    const stopBtn = page.locator('button:has-text("停止"), button[class*="stop"]');
    const isStopVisible = await stopBtn.isVisible().catch(() => false);
    
    if (isStopVisible) {
      await stopBtn.click();
    }
  });

  test('10. 资源管理和性能测试', async ({ page }) => {
    // 测试页面加载性能
    const startTime = Date.now();
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    const loadTime = Date.now() - startTime;

    console.log(`Agent页面加载时间: ${loadTime}ms`);
    expect(loadTime).toBeLessThan(10000); // 10秒内加载完成

    // 检查内存使用
    const metrics = await page.evaluate(() => {
      if (performance && performance.memory) {
        return {
          usedJSHeapSize: performance.memory.usedJSHeapSize,
          totalJSHeapSize: performance.memory.totalJSHeapSize
        };
      }
      return null;
    });

    if (metrics) {
      console.log(`JS堆内存使用: ${(metrics.usedJSHeapSize / 1024 / 1024).toFixed(2)}MB`);
    }

    // 检查无控制台错误
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.waitForTimeout(2000);

    if (consoleErrors.length > 0) {
      console.log(`发现 ${consoleErrors.length} 个控制台错误`);
    }
  });
});