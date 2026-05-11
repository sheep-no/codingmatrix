const { chromium } = require('playwright');

const TEST_EMAIL = 'mr_yang@example.com';
const TEST_PASSWORD = '123456';
const BASE_URL = 'http://localhost:3001';

async function testLogin() {
  console.log('========================================');
  console.log('前端登录测试 (调试模式)');
  console.log('========================================\n');

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });

  const page = await context.newPage();

  // 收集所有控制台消息
  const logs = [];
  page.on('console', msg => {
    const text = msg.text();
    logs.push(`[${msg.type().toUpperCase()}] ${text}`);
    console.log(`[Console ${msg.type()}] ${text}`);
  });

  page.on('request', request => {
    if (request.url().includes('/api/')) {
      console.log(`\n>>> REQUEST: ${request.method()} ${request.url()}`);
      const headers = request.headers();
      console.log(`    Headers:`, JSON.stringify(headers, null, 2).substring(0, 500));
    }
  });

  page.on('response', response => {
    if (response.url().includes('/api/')) {
      console.log(`\n<<< RESPONSE: ${response.status()} ${response.url()}`);
    }
  });

  page.on('pageerror', error => {
    console.log(`\n[PAGE ERROR] ${error.message}`);
  });

  try {
    // 1. 打开首页
    console.log('1. 打开首页...');
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    console.log('   首页 DOM 已加载\n');

    // 2. 等待登录按钮
    console.log('2. 等待登录按钮...');
    await page.waitForSelector('.login-btn', { timeout: 10000 });
    console.log('   找到登录按钮\n');

    // 3. 点击登录按钮
    console.log('3. 点击登录按钮...');
    await page.click('.login-btn');
    console.log('   已点击\n');

    // 4. 等待登录表单
    console.log('4. 等待登录表单...');
    await page.waitForSelector('.login-form', { timeout: 5000 });
    console.log('   登录表单已显示\n');

    // 5. 填写登录信息
    console.log('5. 填写登录信息...');
    await page.fill('.login-form input[type="email"]', TEST_EMAIL);
    await page.fill('.login-form input[type="password"]', TEST_PASSWORD);
    console.log(`   邮箱: ${TEST_EMAIL}`);
    console.log(`   密码: ${TEST_PASSWORD}\n`);

    // 6. 在提交前设置断点来捕获请求
    console.log('6. 准备提交登录...\n');

    // 7. 提交登录
    console.log('7. 点击登录按钮...');
    const loginPromise = page.click('.login-form .form-actions button:last-child');

    // 等待一段时间看日志
    await page.waitForTimeout(3000);

    // 检查控制台日志
    console.log('\n========================================');
    console.log('控制台日志:');
    console.log('========================================');
    logs.forEach(log => {
      if (log.includes('error') || log.includes('Error') || log.includes('失败') || log.includes('失败') || log.includes('加密') || log.includes('login') || log.includes('登录')) {
        console.log(log);
      }
    });

    // 检查是否有错误状态的元素
    const errorMessage = await page.$('.error-message');
    if (errorMessage) {
      const errorText = await errorMessage.textContent();
      console.log(`\n错误消息: ${errorText}`);
    }

    // 检查是否登录成功
    const usernameElement = await page.$('.username');
    if (usernameElement) {
      const username = await usernameElement.textContent();
      console.log(`\n✅ 登录成功! 用户名: ${username}`);
    } else {
      console.log('\n❌ 登录未成功');
    }

    // 截图
    const screenshotPath = '/tmp/login-test-debug.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`\n截图已保存: ${screenshotPath}`);

  } catch (error) {
    console.error('\n测试异常:', error.message);

    const screenshotPath = '/tmp/login-test-error.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`错误截图已保存: ${screenshotPath}`);
  } finally {
    await browser.close();
    console.log('\n浏览器已关闭');
  }
}

// 运行测试
testLogin()
  .then(() => {
    console.log('\n测试完成');
    process.exit(0);
  })
  .catch(error => {
    console.error('测试失败:', error);
    process.exit(1);
  });
