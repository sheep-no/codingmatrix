const { chromium } = require('@playwright/test');

const CONFIG = {
    BASE_URL: 'http://localhost:3001',
    API_BASE: 'http://localhost:8080',
    TEST_EMAIL: 'mr_yang@example.com',
    TEST_PASSWORD: '12345678'
};

const TEST_QUESTIONS = [
    { type: 'general', question: '用一句话解释什么是 Python' },
    { type: 'code', question: '写一个 Python 函数计算 1+1' },
];

// 可用的模型
const MODEL = 'Qwen/Qwen2.5-7B-Instruct';

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function login(page) {
    await page.goto(CONFIG.BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await sleep(2000);
    
    await page.waitForSelector('.login-btn', { timeout: 10000 });
    await page.click('.login-btn');
    await sleep(500);
    
    await page.waitForSelector('.login-form input[type="email"]', { timeout: 5000 });
    await page.fill('.login-form input[type="email"]', CONFIG.TEST_EMAIL);
    await page.fill('.login-form input[type="password"]', CONFIG.TEST_PASSWORD);
    await page.click('.login-form .btn-login');
    await sleep(2000);
    
    await page.waitForSelector('.username, .user-info', { timeout: 15000 });
    const userInfo = await page.$('.username') || await page.$('.user-info');
    const username = userInfo ? await userInfo.textContent() : '未知用户';
    console.log(`   登录成功! 用户名: ${username}`);
    return username;
}

async function testChatStream(page, question, index) {
    console.log(`\n   测试 ${index + 1}: [${question.type}] "${question.question}"`);
    
    const results = {
        type: question.type,
        inputSuccess: false,
        sendSuccess: false,
        streamingStarted: false,
        responseReceived: false,
        responseLength: 0,
        success: false
    };

    const startTime = Date.now();

    // 监控网络请求
    const networkRequests = [];
    const networkResponses = [];
    page.on('request', req => {
        if (req.url().includes('/code') || req.url().includes('/api/v1')) {
            networkRequests.push({ url: req.url(), method: req.method() });
        }
    });
    page.on('response', resp => {
        if (resp.url().includes('/code') || resp.url().includes('/api/v1')) {
            networkResponses.push({ url: resp.url(), status: resp.status() });
        }
    });

    try {
        // 1. 输入问题
        const inputSelector = 'textarea, [placeholder*="输入"], [placeholder*="消息"], .chat-input';
        await page.waitForSelector(inputSelector, { timeout: 10000 });
        await page.click(inputSelector);
        await page.fill(inputSelector, question.question);
        results.inputSuccess = true;
        console.log('      ✓ 输入成功');

        // 2. 发送消息（使用 Ctrl+Enter）
        await page.keyboard.press('Control+Enter');
        results.sendSuccess = true;
        console.log('      ✓ 消息已发送 (Ctrl+Enter)');

        // 3. 等待网络请求
        await sleep(2000);
        console.log(`      📡 网络请求: ${networkRequests.length} 个`);
        networkRequests.forEach(req => {
            console.log(`         - ${req.method} ${req.url.substring(0, 80)}`);
        });

        // 4. 等待 AI 响应出现
        try {
            await page.waitForSelector('.message-ai .ai-response-content, .message-ai p, .message-ai pre', { timeout: 120000 });
            results.responseReceived = true;
            console.log('      ✓ AI 响应已出现');
        } catch (e) {
            console.log('      ✗ 等待 AI 响应超时 (120s)');
            console.log(`      📡 网络响应: ${networkResponses.length} 个`);
            networkResponses.forEach(resp => {
                console.log(`         - ${resp.status} ${resp.url.substring(0, 80)}`);
            });
        }

        // 5. 检查响应内容
        await sleep(2000);
        const messages = await page.$$('.message-ai');
        if (messages.length > 0) {
            const lastMsg = messages[messages.length - 1];
            const text = await lastMsg.innerText();
            results.responseLength = text.length;
            console.log(`      ✓ 响应长度: ${text.length} 字符`);
            
            // 检查代码块
            const codeBlocks = await lastMsg.$$('pre, code');
            if (codeBlocks.length > 0) {
                console.log(`      ✓ 代码块: ${codeBlocks.length} 个`);
            }
            
            // 检查流式动画是否已结束
            const streamingEl = await lastMsg.$('.streaming-placeholder, .streaming-circle');
            if (!streamingEl) {
                console.log('      ✓ 流式已完成');
            }
        }

        results.success = results.responseReceived && results.responseLength > 0;

    } catch (error) {
        console.log(`      ✗ 测试失败: ${error.message}`);
    }

    return results;
}

async function main() {
    console.log('========== AI Code 流式显示测试 ==========\n');

    const browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage({
        viewport: { width: 1280, height: 800 }
    });

    // 收集错误
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));

    try {
        // 1. 登录
        console.log('1. 登录系统...');
        await login(page);

        // 2. E2E 流式测试
        console.log('\n2. E2E 流式显示测试...');
        const e2eResults = [];
        for (let i = 0; i < TEST_QUESTIONS.length; i++) {
            const result = await testChatStream(page, TEST_QUESTIONS[i], i);
            e2eResults.push(result);
            await sleep(2000);
        }

        // 3. 总结
        console.log('\n========== 测试报告 ==========');
        
        let e2ePassed = 0;
        for (const r of e2eResults) {
            if (r.success) e2ePassed++;
            console.log(`  ${r.success ? '✓' : '✗'} [${r.type}] 响应: ${r.responseLength}字符`);
            if (r.inputSuccess) console.log(`    - 输入: 成功`);
            if (r.sendSuccess) console.log(`    - 发送: 成功`);
            if (!r.responseReceived) console.log(`    - 响应: 未收到`);
        }

        console.log(`\nE2E 测试: ${e2ePassed}/${e2eResults.length} 通过`);

        if (pageErrors.length > 0) {
            console.log(`\n页面错误: ${pageErrors.length} 个`);
            pageErrors.slice(0, 5).forEach((err, i) => {
                console.log(`  [${i + 1}] ${err.substring(0, 150)}`);
            });
        }

        // 截图
        const screenshotPath = `/tmp/aicode-final-${Date.now()}.png`;
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.log(`\n📸 最终截图: ${screenshotPath}`);

        console.log('\n====================================');

    } catch (error) {
        console.error('测试失败:', error.message);
        await page.screenshot({ path: '/tmp/aicode-test-error.png', fullPage: true });
    } finally {
        await browser.close();
    }
}

main().catch(console.error);
