const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  
  // Click login button
  await page.click('button:has-text("登录")');
  await page.waitForTimeout(2000);
  
  // Try different selectors
  console.log('=== Testing different selectors ===');
  
  // Try by type
  const emailByType = await page.$('input[type="email"]');
  console.log('Email by type:', !!emailByType);
  
  // Try by placeholder with exact match
  const emailByPlaceholder = await page.$('input[placeholder="请输入邮箱地址"]');
  console.log('Email by placeholder exact:', !!emailByPlaceholder);
  
  // Try by placeholder with contains
  const emailByPlaceholderContains = await page.$('input[placeholder*="邮箱"]');
  console.log('Email by placeholder contains:', !!emailByPlaceholderContains);
  
  // Try by class or id
  const allInputs = await page.$$('input');
  console.log('Total inputs:', allInputs.length);
  
  for (let i = 0; i < allInputs.length; i++) {
    const input = allInputs[i];
    const type = await input.getAttribute('type');
    const placeholder = await input.getAttribute('placeholder');
    const id = await input.getAttribute('id');
    const name = await input.getAttribute('name');
    const className = await input.getAttribute('class');
    console.log(`Input ${i}: type=${type}, placeholder="${placeholder}", id=${id}, name=${name}, class=${className}`);
  }
  
  await browser.close();
})();
