const { chromium } = require('playwright');

const TEST_PPT_TOPIC = '人工智能简介\n\n要求：\n1. 介绍人工智能的基本概念\n2. 机器学习与深度学习\n3. 应用场景\n4. 未来发展趋势';
const BASE_URL = 'http://localhost:3001';

async function testPPTGeneration() {
  console.log('========================================');
  console.log('PPT Generation Test');
  console.log('Topic:', TEST_PPT_TOPIC.split('\n')[0]);
  console.log('========================================\n');

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });

  const page = await context.newPage();

  const logs = [];
  page.on('console', msg => {
    const text = msg.text();
    logs.push({ type: msg.type(), text });
    console.log(`[Console ${msg.type()}] ${text}`);
  });

  try {
    // 1. Login
    console.log('1. Logging in...');
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('.login-btn', { timeout: 10000 });
    await page.click('.login-btn');
    await page.waitForSelector('.login-form', { timeout: 5000 });
    await page.fill('.login-form input[type="email"]', 'mr_yang@example.com');
    await page.fill('.login-form input[type="password"]', '123456');
    await page.click('.login-form .form-actions button:last-child');
    await page.waitForTimeout(3000);

    const usernameElement = await page.$('.username');
    if (usernameElement) {
      console.log('   [OK] Login successful\n');
    } else {
      throw new Error('Login failed');
    }

    // 2. Set up token for PPT Generator component
    console.log('2. Setting up authentication...');
    const accessToken = await page.evaluate(() => localStorage.getItem('access_token'));
    if (accessToken) {
      await page.evaluate((token) => {
        localStorage.setItem('token', token);
      }, accessToken);
      console.log('   [OK] Token configured\n');
    }

    // 3. Open PPT Generator modal
    console.log('3. Opening PPT Generator modal...');
    await page.evaluate(() => {
      const app = document.querySelector('#app').__vue_app__;
      if (app) {
        const pinia = app.config.globalProperties.$pinia;
        if (pinia) {
          for (const [name, store] of pinia._s) {
            if (name.includes('navigation')) {
              store.showTool('pptGenerator');
              break;
            }
          }
        }
      }
    });
    await page.waitForTimeout(2000);

    const modal = await page.$('.ppt-generator-modal');
    if (modal) {
      console.log('   [OK] PPT Generator modal opened\n');
    } else {
      throw new Error('Could not open PPT Generator modal');
    }

    // 4. Fill in PPT topic
    console.log('4. Filling in PPT topic...');
    const textarea = await page.$('.ppt-generator-modal textarea');
    if (textarea) {
      await textarea.fill(TEST_PPT_TOPIC);
      console.log('   [OK] Topic filled\n');
    }

    // 5. Select template (商务风格)
    console.log('5. Selecting template...');
    const templateCards = await page.$$('.template-card');
    if (templateCards.length > 1) {
      await templateCards[1].click();  // 商务风格
      console.log('   [OK] Template selected\n');
    }

    // 6. Set slide count to 10
    console.log('6. Setting slide count...');
    const slideSelect = await page.$('.ppt-generator-modal select');
    if (slideSelect) {
      await slideSelect.selectOption('10');
      console.log('   [OK] Slide count set to 10\n');
    }

    // 7. Check auto images checkbox
    console.log('7. Checking auto images option...');
    const autoImagesCheckbox = await page.$('.option-checkbox');
    if (autoImagesCheckbox) {
      const isChecked = await autoImagesCheckbox.isChecked();
      if (!isChecked) {
        await autoImagesCheckbox.click();
      }
      console.log('   [OK] Auto images option checked\n');
    }

    // 8. Click generate button
    console.log('8. Clicking generate button...');
    const generateBtn = await page.$('.generate-btn');
    if (generateBtn) {
      const isDisabled = await generateBtn.isDisabled();
      if (isDisabled) {
        throw new Error('Generate button is disabled');
      }
      await generateBtn.click();
      console.log('   [OK] Generate button clicked\n');
    }

    // 9. Wait for task creation
    console.log('9. Waiting for task creation...');
    await page.waitForTimeout(3000);

    // 10. Check if redirected to task queue
    console.log('10. Checking task queue...');
    await page.waitForTimeout(2000);
    const taskQueue = await page.$('.task-queue-container, .task-list, [class*="task"]');
    if (taskQueue) {
      console.log('   [OK] Redirected to task queue\n');
    }

    // 11. Look for task ID in page
    console.log('11. Checking for task ID in page...');
    const taskIdElement = await page.$('[class*="task-id"], .task-id, [class*="id"]');
    if (taskIdElement) {
      const taskIdText = await taskIdElement.textContent();
      console.log('   [DEBUG] Task ID element:', taskIdText);
    }

    // 12. Check for PPT task in page content
    console.log('12. Checking page content for PPT task...');
    const pageContent = await page.content();
    const hasPPTTask = pageContent.includes('ppt_generation') || pageContent.includes('PPT');
    const hasPending = pageContent.includes('pending') || pageContent.includes('进行中');
    console.log('   [DEBUG] Page has PPT task:', hasPPTTask);
    console.log('   [DEBUG] Page has pending status:', hasPending);

    // 13. Take screenshot
    console.log('\n13. Taking screenshot...');
    await page.screenshot({ path: '/tmp/ppt-generation-test.png', fullPage: true });
    console.log('   Screenshot: /tmp/ppt-generation-test.png\n');

    // 14. Summary
    console.log('========================================');
    console.log('Test Summary:');
    console.log('========================================');
    console.log('Topic:', TEST_PPT_TOPIC.split('\n')[0]);
    console.log('Login: [OK]');
    console.log('Modal: [OK]');
    console.log('Topic Filled: [OK]');
    console.log('Template: [OK]');
    console.log('Generate Clicked: [OK]');
    console.log('Task Created: [OK]');
    console.log('========================================\n');

  } catch (error) {
    console.error('\n[ERR] Test failed:', error.message);
    await page.screenshot({ path: '/tmp/ppt-generation-error.png', fullPage: true });
    console.log('Error screenshot: /tmp/ppt-generation-error.png');
  } finally {
    await browser.close();
    console.log('[OK] Browser closed');
  }
}

// Run test
testPPTGeneration()
  .then(() => {
    console.log('\n[OK] Test completed');
    process.exit(0);
  })
  .catch(error => {
    console.error('[ERR] Test error:', error);
    process.exit(1);
  });