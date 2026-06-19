const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  
  console.log('=== Before clicking login button ===');
  
  // Click login button
  const loginBtn = await page.$('button:has-text("登录")');
  if (loginBtn) {
    console.log('Login button found, clicking...');
    await loginBtn.click();
    await page.waitForTimeout(2000);
    
    console.log('=== After clicking login button ===');
    
    // Get all inputs again
    const inputs = await page.$$('input');
    console.log('Total inputs found:', inputs.length);
    for (const input of inputs) {
      const placeholder = await input.getAttribute('placeholder');
      const type = await input.getAttribute('type');
      console.log(`  Input: type=${type}, placeholder=${placeholder}`);
    }
    
    // Take screenshot
    await page.screenshot({ path: '/tmp/login-modal.png', fullPage: true });
    console.log('Screenshot saved to /tmp/login-modal.png');
  } else {
    console.log('Login button not found');
  }
  
  await browser.close();
})();
