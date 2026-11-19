/**
 * 综合 E2E 测试 - 检测前端错误链接、响应错误、功能不全、后端空闲功能
 */

import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('综合诊断测试', () => {
  test.beforeEach(async ({ page, context }) => {
    // 监听所有网络请求和响应
    await context.route('**/*', (route) => route.continue());
    
    // 收集网络错误
    page.on('response', async (response) => {
      if (!response.ok()) {
        console.log(`网络错误: ${response.url()} - ${response.status()}`);
      }
    });

    page.on('pageerror', (error) => {
      console.log(`页面错误: ${error.message}`);
    });

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        console.log(`控制台错误: ${msg.text()}`);
      }
    });

    await apiLogin(page);
  });

  test('1. 检测前端错误链接', async ({ page }) => {
    const errorLinks = [];
    const visitedUrls = new Set();

    // 访问主要页面
    const mainPages = [
      '/',
      '/agent',
      '/workflow',
      '/ppt-generate',
      '/image-generate'
    ];

    for (const pageUrl of mainPages) {
      try {
        await page.goto(pageUrl);
        await page.waitForLoadState('networkidle', { timeout: 10000 });
        visitedUrls.add(pageUrl);

        // 检查页面上的所有链接
        const links = await page.$$eval('a[href], button[onclick], [role="link"]', (elements) => {
          return elements.map(el => {
            const href = el.getAttribute('href') || el.getAttribute('onclick') || el.getAttribute('data-href');
            const text = el.textContent?.trim() || el.getAttribute('aria-label') || '';
            return { href, text };
          }).filter(link => link.href);
        });

        // 测试可点击的链接
        for (const link of links) {
          const url = link.href;
          
          // 跳过外部链接和特殊链接
          if (url.startsWith('http') && !url.includes(window.location.origin)) continue;
          if (url.startsWith('javascript:')) continue;
          if (url === '#' || url === '') continue;

          if (!visitedUrls.has(url)) {
            try {
              const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
              if (response && response.status() >= 400) {
                errorLinks.push({
                  url,
                  status: response.status(),
                  text: link.text,
                  from: pageUrl
                });
              }
              await page.waitForTimeout(500);
              visitedUrls.add(url);
            } catch (error) {
              errorLinks.push({
                url,
                error: error.message,
                text: link.text,
                from: pageUrl
              });
            }
          }
        }
      } catch (error) {
        console.log(`访问页面失败: ${pageUrl} - ${error.message}`);
      }
    }

    console.log(`检测到 ${errorLinks.length} 个错误链接:`);
    errorLinks.forEach(link => {
      console.log(`  - ${link.text} -> ${link.url} (${link.status || link.error}) from ${link.from}`);
    });

    // 记录测试结果
    if (errorLinks.length > 0) {
      test.info().annotations.push({ 
        type: 'error-links', 
        description: JSON.stringify(errorLinks, null, 2) 
      });
    }

    expect(errorLinks.length).toBe(0);
  });

  test('2. 检测前端 API 响应错误', async ({ page }) => {
    const apiErrors = [];

    // 监听所有 API 请求
    page.on('response', async (response) => {
      const url = response.url();

      // 只关注 API 请求
      if (url.includes('/api/')) {
        const status = response.status();
        // 401/403 属于鉴权预期分支，404 也可能是可选的模型上下文等探测
        if (status >= 500) {
          try {
            const body = await response.text().catch(() => '');
            apiErrors.push({
              url,
              status,
              method: response.request().method(),
              error: body.substring(0, 200)
            });
          } catch (error) {
            apiErrors.push({
              url,
              status,
              method: response.request().method(),
              error: '无法读取响应体'
            });
          }
        }
      }
    });

    // 访问 Agent 页面并触发常见操作
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // 检查 /agent 页面实际依赖的 API 端点
    const apiEndpoints = [
      '/api/v1/user/profile',
      '/api/v1/agent/sessions',
      '/api/v1/agent/apikeys',
      '/api/v1/skills/list',
      '/api/v1/agent/host/sessions'
    ];

    for (const endpoint of apiEndpoints) {
      try {
        const response = await page.request.get(endpoint);
        if (response.status() >= 500) {
          apiErrors.push({
            url: endpoint,
            status: response.status(),
            method: 'GET',
            error: 'API 端点不可用'
          });
        }
      } catch (error) {
        apiErrors.push({
          url: endpoint,
          error: error.message,
          method: 'GET'
        });
      }
    }

    console.log(`检测到 ${apiErrors.length} 个 API 响应错误:`);
    apiErrors.forEach(err => {
      console.log(`  - ${err.method} ${err.url} -> ${err.status || err.error}`);
    });

    if (apiErrors.length > 0) {
      test.info().annotations.push({ 
        type: 'api-errors', 
        description: JSON.stringify(apiErrors, null, 2) 
      });
    }

    // 关注服务端故障，鉴权/参数类 4xx 由各自的用例覆盖
    expect(apiErrors.length).toBe(0);
  });

  test('3. 检测前端功能完整性 - Agent 页面', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    const missingFeatures = [];

    // 检查当前 Agent 工作台必需的 UI 元素
    const requiredElements = [
      { selector: '.agent-topbar', name: '顶部状态栏' },
      { selector: '.agent-sidebar', name: '会话侧栏' },
      { selector: '[data-testid="agent-prompt-input"]', name: '项目需求输入框' },
      { selector: 'button[aria-label="发送需求"]', name: '发送按钮' },
      { selector: '.agent-workspace', name: '工作区' },
      { selector: '.agent-file-panel', name: '项目产物面板' }
    ];

    for (const element of requiredElements) {
      const isVisible = await page.locator(element.selector).first().isVisible().catch(() => false);
      if (!isVisible) {
        missingFeatures.push(element.name);
      }
    }

    console.log(`缺失的功能: ${missingFeatures.join(', ') || '无'}`);

    if (missingFeatures.length > 0) {
      test.info().annotations.push({ 
        type: 'missing-features', 
        description: JSON.stringify(missingFeatures, null, 2) 
      });
    }

    expect(missingFeatures).toEqual([]);
  });

  test('4. 检测后端空闲/未使用功能', async ({ page, request }) => {
    const token = await page.evaluate(
      () => sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    );
    const headers = { Accept: 'application/json', Authorization: `Bearer ${token}` };

    // 获取后端 API 端点列表（按当前路由表核对）
    const backendEndpoints = [
      // Agent 相关
      { endpoint: '/api/v1/agent/sessions', method: 'GET', category: 'agent' },
      { endpoint: '/api/v1/agent/performance', method: 'GET', category: 'agent' },
      { endpoint: '/api/v1/agent/token-usage', method: 'GET', category: 'agent' },
      { endpoint: '/api/v1/agent/knowledge', method: 'GET', category: 'agent' },
      { endpoint: '/api/v1/agent/apikeys', method: 'GET', category: 'agent' },
      { endpoint: '/api/v1/agent/host/sessions', method: 'GET', category: 'agent' },
      { endpoint: '/api/v1/agent/saved', method: 'GET', category: 'agent' },

      // 管理员
      { endpoint: '/api/v2/admin/config', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/Controller/admin/stats', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/Controller/admin/memory', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/Controller/admin/rate-limit', method: 'GET', category: 'admin' },

      // 用户
      { endpoint: '/api/v1/user/profile', method: 'GET', category: 'user' },
      { endpoint: '/api/v2/Controller/users', method: 'GET', category: 'user' },

      // Skills
      { endpoint: '/api/v1/skills/list', method: 'GET', category: 'skills' },
      { endpoint: '/api/v1/skills/categories', method: 'GET', category: 'skills' },

      // 模型
      { endpoint: '/api/v1/models/agent-config', method: 'GET', category: 'model' },
      { endpoint: '/api/v1/aicloud/models', method: 'GET', category: 'model' },
    ];

    const unusedEndpoints = [];
    const errorEndpoints = [];

    // 检查每个端点的状态
    for (const ep of backendEndpoints) {
      try {
        const response = await request.get(ep.endpoint, {
          headers,
          timeout: 5000
        });

        if (response.status() >= 500) {
          errorEndpoints.push({
            ...ep,
            status: response.status(),
            error: 'HTTP Error'
          });
        }
      } catch (error) {
        // 端点不存在或无法访问可能是正常的，这里我们只记录
        unusedEndpoints.push({
          ...ep,
          error: error.message
        });
      }
    }

    console.log(`检测到 ${errorEndpoints.length} 个端点错误:`);
    errorEndpoints.forEach(ep => {
      console.log(`  - ${ep.method} ${ep.endpoint} -> ${ep.status} (${ep.category})`);
    });

    console.log(`检测到 ${unusedEndpoints.length} 个可能未使用的端点:`);
    unusedEndpoints.forEach(ep => {
      console.log(`  - ${ep.method} ${ep.endpoint} (${ep.category})`);
    });

    // 按类别统计
    const byCategory = {};
    backendEndpoints.forEach(ep => {
      if (!byCategory[ep.category]) {
        byCategory[ep.category] = { total: 0, errors: 0, unused: 0 };
      }
      byCategory[ep.category].total++;
    });

    errorEndpoints.forEach(ep => {
      byCategory[ep.category].errors++;
    });

    unusedEndpoints.forEach(ep => {
      byCategory[ep.category].unused++;
    });

    console.log('端点统计:');
    Object.entries(byCategory).forEach(([category, stats]) => {
      console.log(`  ${category}: ${stats.total} 总计, ${stats.errors} 错误, ${stats.unused} 未使用`);
    });

    if (errorEndpoints.length > 0 || unusedEndpoints.length > 0) {
      test.info().annotations.push({ 
        type: 'backend-status', 
        description: JSON.stringify({
          errorEndpoints,
          unusedEndpoints,
          byCategory
        }, null, 2) 
      });
    }

    // 期望没有严重错误（500 错误）
    const severeErrors = errorEndpoints.filter(ep => ep.status >= 500);
    expect(severeErrors.length).toBe(0);
  });

  test('5. 检测资源加载错误', async ({ page }) => {
    const resourceErrors = [];

    page.on('response', async (response) => {
      const url = response.url();
      const status = response.status();

      // 关注静态资源
      if (url.match(/\.(js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf)$/)) {
        if (status >= 400) {
          resourceErrors.push({
            url,
            status,
            type: url.split('.').pop()
          });
        }
      }
    });

    // 访问主要页面
    const pages = ['/', '/agent', '/admin'];
    for (const pageUrl of pages) {
      try {
        await page.goto(pageUrl);
        await page.waitForLoadState('networkidle', { timeout: 10000 });
      } catch (error) {
        console.log(`访问页面失败: ${pageUrl}`);
      }
    }

    console.log(`检测到 ${resourceErrors.length} 个资源加载错误:`);
    resourceErrors.forEach(err => {
      console.log(`  - ${err.url} (${err.type}) -> ${err.status}`);
    });

    if (resourceErrors.length > 0) {
      test.info().annotations.push({ 
        type: 'resource-errors', 
        description: JSON.stringify(resourceErrors, null, 2) 
      });
    }

    expect(resourceErrors.length).toBe(0);
  });

  test('6. 检测控制台错误', async ({ page }) => {
    const consoleErrors = [];
    const consoleWarnings = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push({
          text: msg.text(),
          location: msg.location()
        });
      } else if (msg.type() === 'warning') {
        consoleWarnings.push({
          text: msg.text(),
          location: msg.location()
        });
      }
    });

    // 访问主要页面
    const pages = ['/', '/agent', '/ppt-generate', '/image-generate'];
    for (const pageUrl of pages) {
      try {
        await page.goto(pageUrl);
        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(2000); // 等待可能的错误出现
      } catch (error) {
        console.log(`访问页面失败: ${pageUrl}`);
      }
    }

    console.log(`检测到 ${consoleErrors.length} 个控制台错误:`);
    consoleErrors.forEach(err => {
      console.log(`  - ${err.text} at ${err.location?.url || 'unknown'}:${err.location?.lineNumber || '?'}`);
    });

    console.log(`检测到 ${consoleWarnings.length} 个控制台警告:`);
    consoleWarnings.slice(0, 10).forEach(err => {
      console.log(`  - ${err.text}`);
    });

    if (consoleErrors.length > 0) {
      test.info().annotations.push({ 
        type: 'console-errors', 
        description: JSON.stringify(consoleErrors, null, 2) 
      });
    }

    // 允许部分警告，但不允许错误
    expect(consoleErrors.length).toBe(0);
  });
});
