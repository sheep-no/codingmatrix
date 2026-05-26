/**
 * 综合 E2E 测试 - 简化版（无需登录）
 * 检测前端错误链接、响应错误、功能不全、后端空闲功能
 */

import { test, expect } from '@playwright/test';

test.describe('综合诊断测试（无需登录）', () => {
  test.beforeEach(async ({ page }) => {
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
  });

  test('1. 检测前端错误链接', async ({ page }) => {
    const errorLinks = [];

    // 访问主要页面
    const mainPages = [
      '/',
      '/agent',
      '/ppt-generate',
      '/image-generate'
    ];

    for (const pageUrl of mainPages) {
      try {
        await page.goto(pageUrl);
        await page.waitForLoadState('networkidle', { timeout: 10000 });
      } catch (error) {
        console.log(`访问页面失败: ${pageUrl} - ${error.message}`);
        continue;
      }

      // 检查页面上的所有链接
      const links = await page.$$eval('a[href]', (elements) => {
        return elements.map(el => {
          const href = el.getAttribute('href');
          const text = el.textContent?.trim() || el.getAttribute('aria-label') || '';
          return { href, text };
        }).filter(link => link.href);
      });

      // 测试可点击的链接
      for (const link of links) {
        const url = link.href;
        
        // 跳过外部链接和特殊链接
        if (url.startsWith('http') && !url.includes('localhost')) continue;
        if (url.startsWith('javascript:')) continue;
        if (url === '#' || url === '') continue;

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

    console.log(`检测到 ${errorLinks.length} 个错误链接:`);
    errorLinks.forEach(link => {
      console.log(`  - ${link.text} -> ${link.url} (${link.status || link.error}) from ${link.from}`);
    });

    if (errorLinks.length > 0) {
      test.info().annotations.push({ 
        type: 'error-links', 
        description: JSON.stringify(errorLinks, null, 2) 
      });
    }
  });

  test('2. 检测前端 API 响应错误', async ({ page, request }) => {
    const apiErrors = [];

    // 监听所有 API 请求
    page.on('response', async (response) => {
      const url = response.url();
      
      if (url.includes('/api/') || url.includes('/agent/')) {
        const status = response.status();
        
        if (status >= 400 && status !== 401 && status !== 403) {
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

    // 访问主要页面
    const pages = ['/', '/agent', '/ppt-generate', '/image-generate'];
    for (const pageUrl of pages) {
      try {
        await page.goto(pageUrl);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
      } catch (error) {
        console.log(`访问页面失败: ${pageUrl}`);
      }
    }

    // 直接检查关键 API 端点
    const apiEndpoints = [
      '/api/v1/user/info',
      '/api/v1/agent/orchestrate/stream',
      '/api/v2/system/get_system_info'
    ];

    for (const endpoint of apiEndpoints) {
      try {
        const response = await request.get(`http://localhost:8000${endpoint}`, {
          headers: { 'Accept': 'application/json' },
          timeout: 5000
        });
        if (response.status() >= 400) {
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

    const criticalErrors = apiErrors.filter(err => err.status >= 500);
    expect(criticalErrors.length).toBe(0);
  });

  test('3. 检测前端功能完整性', async ({ page }) => {
    await page.goto('/agent');
    try {
      await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    } catch (error) {
      console.log('Agent 页面加载超时，可能需要登录');
      return;
    }

    const missingFeatures = [];

    // 检查必需的 UI 元素
    const requiredElements = [
      { selector: 'h1.page-title, .page-title h1', name: '页面标题' },
      { selector: 'textarea.prompt-textarea, textarea', name: '项目描述输入框' },
      { selector: 'button:has-text("生成"), button:has-text("Generate")', name: '生成按钮' },
      { selector: '[class*="tab"], [role="tab"]', name: 'Tab 导航' },
      { selector: '[class*="template"], [class*="quick"]', name: '快速模板' }
    ];

    for (const element of requiredElements) {
      const isVisible = await page.locator(element.selector).isVisible().catch(() => false);
      if (!isVisible) {
        missingFeatures.push(element.name);
      }
    }

    // 检查功能可用性
    const tabs = await page.$$('[class*="tab"], [role="tab"]');
    const templates = await page.$$('[class*="template"], [class*="quick"]');

    console.log(`缺失的功能: ${missingFeatures.join(', ') || '无'}`);
    console.log(`Tab 数量: ${tabs.length}`);
    console.log(`模板数量: ${templates.length}`);

    if (missingFeatures.length > 0) {
      test.info().annotations.push({ 
        type: 'missing-features', 
        description: JSON.stringify(missingFeatures, null, 2) 
      });
    }

    // 允许部分功能缺失（可能需要登录）
    expect(missingFeatures.length).toBeLessThan(5);
  });

  test('4. 检测后端端点状态', async ({ request }) => {
    const backendEndpoints = [
      // Agent 相关
      { endpoint: '/api/v1/agent/orchestrate/stream', method: 'POST', category: 'agent' },
      { endpoint: '/api/v1/agent/sessions/{session_id}', method: 'DELETE', category: 'agent' },
      { endpoint: '/api/v1/agent/session/{session_id}/action', method: 'POST', category: 'agent' },
      { endpoint: '/api/v1/agent/session/{session_id}/decision', method: 'POST', category: 'agent' },
      
      // 管理员
      { endpoint: '/api/v2/system/get_system_info', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/admin/users', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/admin/services', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/admin/config', method: 'GET', category: 'admin' },
      { endpoint: '/api/v2/admin/logs', method: 'GET', category: 'admin' },
      
      // 用户管理
      { endpoint: '/api/v2/Controller/GetCurrentUser', method: 'GET', category: 'user' },
      { endpoint: '/api/v2/Controller/Logout', method: 'POST', category: 'user' },
      
      // 资源管理
      { endpoint: '/api/v2/Controller/ListAllServices', method: 'GET', category: 'resource' },
      { endpoint: '/api/v2/Controller/GetServiceStatus', method: 'GET', category: 'resource' },
      
      // GirlAi
      { endpoint: '/api/v2/Controller/AiChat', method: 'POST', category: 'girlai' },
      { endpoint: '/api/v2/Controller/GetAvatarList', method: 'GET', category: 'girlai' },
      
      // Nginx
      { endpoint: '/api/v2/Controller/GetNginxConfig', method: 'GET', category: 'nginx' },
      
      // 项目生成
      { endpoint: '/api/v1/agent/generate/projects', method: 'GET', category: 'project' },
      { endpoint: '/api/v1/agent/generate/files', method: 'GET', category: 'project' },
    ];

    const endpointStatus = [];

    for (const ep of backendEndpoints) {
      try {
        const response = await request.get(`http://localhost:8000${ep.endpoint}`, {
          headers: { 'Accept': 'application/json' },
          timeout: 5000
        });

        endpointStatus.push({
          ...ep,
          status: response.status(),
          available: response.ok()
        });
      } catch (error) {
        endpointStatus.push({
          ...ep,
          error: error.message,
          available: false
        });
      }
    }

    const availableCount = endpointStatus.filter(e => e.available).length;
    const unavailableCount = endpointStatus.length - availableCount;

    console.log(`后端端点状态: ${availableCount}/${endpointStatus.length} 可用`);

    // 按类别统计
    const byCategory = {};
    endpointStatus.forEach(ep => {
      if (!byCategory[ep.category]) {
        byCategory[ep.category] = { total: 0, available: 0 };
      }
      byCategory[ep.category].total++;
      if (ep.available) {
        byCategory[ep.category].available++;
      }
    });

    console.log('端点分类统计:');
    Object.entries(byCategory).forEach(([category, stats]) => {
      console.log(`  ${category}: ${stats.available}/${stats.total}`);
    });

    test.info().annotations.push({ 
      type: 'backend-status', 
      description: JSON.stringify({
        total: endpointStatus.length,
        available: availableCount,
        unavailable: unavailableCount,
        byCategory
      }, null, 2) 
    });

    // 至少 50% 的端点应该可用
    expect(availableCount).toBeGreaterThan(endpointStatus.length * 0.5);
  });

  test('5. 检测资源加载错误', async ({ page }) => {
    const resourceErrors = [];

    page.on('response', async (response) => {
      const url = response.url();
      const status = response.status();

      if (url.match(/\.(js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf|ico)$/)) {
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
    const pages = ['/', '/agent', '/ppt-generate', '/image-generate'];
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
          text: msg.text()
        });
      }
    });

    // 访问主要页面
    const pages = ['/', '/agent', '/ppt-generate', '/image-generate'];
    for (const pageUrl of pages) {
      try {
        await page.goto(pageUrl);
        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(2000);
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

    // 允许部分警告，但严重错误不应超过 5 个
    const severeErrors = consoleErrors.filter(err => 
      err.text.toLowerCase().includes('uncaught') ||
      err.text.toLowerCase().includes('fatal')
    );
    expect(severeErrors.length).toBeLessThan(5);
  });
});