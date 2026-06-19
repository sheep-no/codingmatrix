const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('Console error:', msg.text());
    }
  });
  
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(5000);
  
  console.log('Page title:', await page.title());
  
  // Get all input elements
  const inputs = await page.$$('input');
  console.log('Total inputs found:', inputs.length);
  for (const input of inputs) {
    const placeholder = await input.getAttribute('placeholder');
    const type = await input.getAttribute('type');
    console.log(`  Input: type=${type}, placeholder=${placeholder}`);
  }
  
  // Get all buttons
  const buttons = await page.$$('button');
  console.log('Total buttons found:', buttons.length);
  for (const btn of buttons) {
    const text = await btn.textContent();
    console.log(`  Button: "${text.trim()}"`);
  }
  
  // Take screenshot
  await page.screenshot({ path: '/tmp/login-page-debug.png', fullPage: true });
  console.log('Screenshot saved to /tmp/login-page-debug.png');
  
  await browser.close();
})();
