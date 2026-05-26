import { test, expect } from '@playwright/test';

test('Agent 接口 401/500 错误诊断', async ({ page }) => {
  const failedRequests = [];

  page.on('response', async response => {
    const status = response.status();
    const url = response.url();
    
    if ((status === 401 || status === 500) && url.includes('/api/')) {
      let body = '';
      try {
        body = await response.text();
      } catch {}
      
      const requestHeaders = response.request().headers();
      failedRequests.push({
        url,
        status,
        method: response.request().method(),
        hasAuth: !!requestHeaders['authorization'],
        hasCsrf: !!requestHeaders['x-csrf-token'],
        body: body.substring(0, 500),
      });
    }
  });

  // 步骤 1: 先访问主页设置 localStorage
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  
  // 获取 token
  const loginResponse = await page.request.post('/api/v1/login', {
    data: { email: 'test@test.com', password: 'Test123456!' },
  });
  const loginData = await loginResponse.json();
  const token = loginData.access_token;

  // 设置 token 到 localStorage
  await page.evaluate((tok) => {
    localStorage.setItem('access_token', tok);
    localStorage.setItem('username', 'test');
    localStorage.setItem('email', 'test@test.com');
    localStorage.setItem('permission_level', 'normal');
  }, token);

  // 步骤 2: 导航到 Agent 页面
  await page.goto('/agent', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  // 获取页面完整 HTML
  const html = await page.content();
  console.log('=== 页面 HTML ===');
  console.log(html.substring(0, 2000));
  console.log('...');

  // 检查 #app 内容
  const appContent = await page.locator('#app').innerHTML().catch(() => '');
  console.log('\n=== #app 内容 ===');
  console.log(appContent.substring(0, 1000));
});
