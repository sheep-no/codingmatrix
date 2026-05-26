// @ts-check
const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';

test('Agent 页面 401/500 错误全面诊断', async ({ page, browser }) => {
  const errors401 = [];
  const errors500 = [];
  const allRequests = [];

  // 监听所有网络请求
  page.on('request', request => {
    allRequests.push({
      url: request.url(),
      method: request.method(),
      headers: request.headers(),
      postData: request.postData(),
      resourceType: request.resourceType(),
    });
  });

  // 监听所有响应，捕获 401 和 500 错误
  page.on('response', async response => {
    const status = response.status();
    const url = response.url();

    if (status === 401 || status === 500) {
      let body = '';
      try {
        body = await response.text();
      } catch (e) {
        body = '[无法读取响应体]';
      }

      const errorInfo = {
        url,
        status,
        statusText: response.statusText(),
        method: response.request().method(),
        requestHeaders: response.request().headers(),
        requestBody: response.request().postData(),
        responseHeaders: response.headers(),
        responseBody: body,
        timestamp: new Date().toISOString(),
      };

      if (status === 401) {
        errors401.push(errorInfo);
      } else {
        errors500.push(errorInfo);
      }
    }
  });

  // 捕获控制台错误
  const consoleErrors = [];
  page.on('pageerror', error => {
    consoleErrors.push(error.message);
  });

  console.log('\n========== 开始诊断 ==========\n');

  // ========== 步骤 1: 通过 API 登录获取 token ==========
  console.log('步骤 1: 通过 API 登录...');

  const loginResponse = await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
    data: {
      username: 'admin',
      password: 'admin123',
    },
  });

  const loginStatus = loginResponse.status();
  console.log(`登录响应状态: ${loginStatus}`);

  let token = '';
  let refreshToken = '';

  if (loginStatus === 200) {
    const loginData = await loginResponse.json();
    console.log('登录响应体:', JSON.stringify(loginData, null, 2));

    // 尝试多种可能的 token 字段名
    token = loginData.access_token || loginData.token || loginData.data?.access_token || loginData.data?.token || '';
    refreshToken = loginData.refresh_token || loginData.data?.refresh_token || '';

    if (!token) {
      console.log('警告: 登录成功但未找到 token 字段，可用字段:', Object.keys(loginData));
    } else {
      console.log('成功获取 token (前 20 字符):', token.substring(0, 20) + '...');
    }
  } else {
    const loginBody = await loginResponse.text();
    console.log('登录失败！响应体:', loginBody);
  }

  // ========== 步骤 2: 导航到 /agent 页面 ==========
  console.log('\n步骤 2: 导航到 /agent 页面...');

  // 在导航前设置 localStorage
  await page.goto(`${BASE_URL}/agent`, { waitUntil: 'domcontentloaded' });

  // 设置 token 到 localStorage
  if (token) {
    await page.evaluate(({ token, refreshToken }) => {
      localStorage.setItem('token', token);
      localStorage.setItem('refresh_token', refreshToken || '');
      localStorage.setItem('access_token', token);
    }, { token, refreshToken });
    console.log('Token 已设置到 localStorage');
  }

  // 刷新页面使 token 生效
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
  console.log('页面已刷新');

  // 等待页面基本加载
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(3000);

  // 打印当前 URL
  console.log('当前页面 URL:', page.url());

  // 检查页面标题
  const title = await page.title();
  console.log('页面标题:', title);

  // ========== 步骤 3: 检查页面元素 ==========
  console.log('\n步骤 3: 检查页面元素...');

  // 打印页面上的关键元素
  const bodyText = await page.locator('body').innerText();
  console.log('页面文本内容 (前 500 字符):', bodyText.substring(0, 500));

  // 检查是否有登录表单（说明未正确认证）
  const hasLoginForm = await page.locator('input[type="password"]').count() > 0;
  console.log('页面存在登录表单:', hasLoginForm);

  // 检查是否有错误提示
  const errorElements = await page.locator('[class*="error"], [class*="Error"], .ant-message-error, .el-message--error').count();
  console.log('页面错误提示元素数量:', errorElements);

  // ========== 步骤 4: 尝试点击生成按钮 ==========
  console.log('\n步骤 4: 尝试触发页面操作...');

  // 查找可能的生成/提交按钮
  const selectors = [
    'button:has-text("生成")',
    'button:has-text("提交")',
    'button:has-text("保存")',
    'button:has-text("Create")',
    'button:has-text("Submit")',
    'button:has-text("生成报告")',
    'button:has-text("运行")',
    'button.ant-btn-primary',
    'button.el-button--primary',
    '[data-testid="submit"]',
    '[data-testid="generate"]',
    'form button[type="submit"]',
    'button[type="submit"]',
  ];

  let clickedButton = false;
  for (const selector of selectors) {
    const btn = await page.locator(selector).first();
    if (await btn.count() > 0) {
      console.log(`找到按钮: ${selector}`);
      await btn.click({ timeout: 5000 });
      clickedButton = true;
      await page.waitForTimeout(5000);
      break;
    }
  }

  if (!clickedButton) {
    console.log('未找到可点击的按钮，列出页面上的所有按钮:');
    const buttons = await page.locator('button').all();
    for (const btn of buttons.slice(0, 10)) {
      const text = await btn.innerText();
      console.log(`  - 按钮: "${text.substring(0, 50)}"`);
    }
  }

  // 等待额外的网络请求完成
  await page.waitForTimeout(3000);

  // ========== 步骤 5: 使用 API 直接测试 Agent 端点 ==========
  console.log('\n步骤 5: 直接 API 测试...');

  const agentEndpoints = [
    '/api/v1/agent',
    '/api/v1/agents',
    '/api/v1/agent/list',
    '/api/v1/agent/status',
    '/api/agent',
    '/api/agents',
  ];

  for (const endpoint of agentEndpoints) {
    try {
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const apiResponse = await page.request.get(`${BASE_URL}${endpoint}`, {
        headers,
      });

      const apiStatus = apiResponse.status();
      console.log(`GET ${endpoint} -> ${apiStatus}`);

      if (apiStatus === 401 || apiStatus === 500) {
        const apiBody = await apiResponse.text();
        const errorInfo = {
          url: `${BASE_URL}${endpoint}`,
          status: apiStatus,
          method: 'GET',
          requestHeaders: headers,
          responseBody: apiBody,
        };
        if (apiStatus === 401) {
          errors401.push(errorInfo);
        } else {
          errors500.push(errorInfo);
        }
      }
    } catch (e) {
      console.log(`GET ${endpoint} -> 请求失败: ${e.message}`);
    }
  }

  // ========== 步骤 6: 输出诊断结果 ==========
  console.log('\n========== 诊断结果 ==========\n');

  console.log(`【401 未授权错误】共 ${errors401.length} 个`);
  for (const err of errors401) {
    console.log('\n--- 401 错误详情 ---');
    console.log(`URL: ${err.url}`);
    console.log(`方法: ${err.method}`);
    console.log(`请求头: ${JSON.stringify(err.requestHeaders || err.requestHeaders, null, 2)}`);
    if (err.requestBody) {
      console.log(`请求体: ${err.requestBody}`);
    }
    console.log(`响应头: ${JSON.stringify(err.responseHeaders, null, 2)}`);
    console.log(`响应体: ${err.responseBody}`);
    console.log(`时间戳: ${err.timestamp}`);
  }

  console.log(`\n【500 服务器错误】共 ${errors500.length} 个`);
  for (const err of errors500) {
    console.log('\n--- 500 错误详情 ---');
    console.log(`URL: ${err.url}`);
    console.log(`方法: ${err.method}`);
    console.log(`请求头: ${JSON.stringify(err.requestHeaders || err.requestHeaders, null, 2)}`);
    if (err.requestBody) {
      console.log(`请求体: ${err.requestBody}`);
    }
    console.log(`响应头: ${JSON.stringify(err.responseHeaders, null, 2)}`);
    console.log(`响应体: ${err.responseBody}`);
    console.log(`时间戳: ${err.timestamp}`);
  }

  console.log(`\n【控制台错误】共 ${consoleErrors.length} 个`);
  for (const err of consoleErrors) {
    console.log(`- ${err}`);
  }

  console.log(`\n【所有网络请求】共 ${allRequests.length} 个`);
  for (const req of allRequests) {
    if (req.resourceType !== 'image' && req.resourceType !== 'font' && req.resourceType !== 'stylesheet') {
      console.log(`${req.method} ${req.url} (${req.resourceType})`);
    }
  }

  // ========== 断言 ==========
  // 这些断用于标记测试失败，但不阻塞诊断输出
  if (errors401.length > 0) {
    console.log('\n⚠️  发现 401 错误，需要修复认证流程');
  }
  if (errors500.length > 0) {
    console.log('\n⚠️  发现 500 错误，需要检查后端逻辑');
  }

  console.log('\n========== 诊断完成 ==========\n');
});
