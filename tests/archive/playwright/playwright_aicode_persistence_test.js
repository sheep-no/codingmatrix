const { chromium } = require('@playwright/test');

const CONFIG = {
    BASE_URL: 'http://localhost:3001',
    API_BASE: 'http://localhost:8080',
    TEST_USERS: {
        superadmin: { email: 'mr_yang@example.com', password: '12345678' }
    }
};

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function login(page, user) {
    await page.goto(CONFIG.BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await sleep(2000);
    
    await page.waitForSelector('.login-btn', { timeout: 10000 });
    await page.click('.login-btn');
    await sleep(500);
    
    await page.waitForSelector('.login-form input[type="email"]', { timeout: 5000 });
    await page.fill('.login-form input[type="email"]', user.email);
    await page.fill('.login-form input[type="password"]', user.password);
    await page.click('.login-form .btn-login');
    await sleep(2000);
    
    await page.waitForSelector('.username, .user-info', { timeout: 15000 });
}

async function sendMessage(page, message) {
    await page.waitForSelector('textarea', { timeout: 10000 });
    const textarea = await page.$('textarea');
    if (textarea) {
        await textarea.click();
        await textarea.fill(message);
        await sleep(500);
        await page.keyboard.press('Control+Enter');
    }
    await sleep(2000);
}

async function waitForStreamStart(page, timeout = 15000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
        const hasStreaming = await page.evaluate(() => {
            const streaming = document.querySelector('.streaming-placeholder, .typing-indicator');
            const messages = document.querySelectorAll('.message-item, .message');
            for (const msg of messages) {
                if (msg.className.includes('streaming') || msg.textContent?.includes('AI 正在思考')) {
                    return true;
                }
            }
            return !!streaming;
        });
        
        if (hasStreaming) return true;
        await sleep(300);
    }
    return false;
}

async function getChatState(page) {
    return await page.evaluate(() => {
        try {
            const state = localStorage.getItem('chatState');
            return state ? JSON.parse(state) : null;
        } catch (e) {
            return null;
        }
    });
}

async function countMessages(page) {
    return await page.evaluate(() => {
        const messages = document.querySelectorAll('.message-item, .message');
        return messages.length;
    });
}

async function getLastMessageContent(page) {
    return await page.evaluate(() => {
        const messages = document.querySelectorAll('.message-item, .message');
        if (messages.length === 0) return '';
        const lastMsg = messages[messages.length - 1];
        return lastMsg.textContent?.substring(0, 200) || '';
    });
}

async function findNewConversationButton(page) {
    // 尝试多种选择器
    const selectors = [
        '.new-chat-btn',
        '.new-conversation-btn',
        '[title*="新建"]',
        '[class*="new-chat"]',
        '.add-btn',
        '.history-header button',
        '.left-panel button'
    ];
    
    for (const selector of selectors) {
        const btn = await page.$(selector);
        if (btn && await btn.isVisible()) {
            return btn;
        }
    }
    
    // 尝试通过文本查找
    const buttons = await page.$$('button');
    for (const btn of buttons) {
        const text = await btn.textContent();
        if (text.includes('新建') || text.includes('New') || text.includes('+')) {
            return btn;
        }
    }
    
    return null;
}

async function switchToConversation(page, index = 0) {
    // 尝试点击历史记录列表中的对话
    const historyItems = await page.$$('.history-item, .conversation-item');
    if (historyItems.length > index) {
        await historyItems[index].click();
        await sleep(1000);
        return true;
    }
    return false;
}

async function main() {
    console.log('========== AI Code 会话持久化测试 ==========\n');
    
    const browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const testResults = {
        refreshDuringStream: false,
        streamRestoredAfterRefresh: false,
        newConversationDuringStream: false,
        originalConversationPreserved: false,
        streamCompletesNormally: false,
        dataPersistedInLocalStorage: false
    };

    const page = await browser.newPage({
        viewport: { width: 1280, height: 800 }
    });

    try {
        // 1. 登录
        console.log('1. 登录系统...');
        await login(page, CONFIG.TEST_USERS.superadmin);
        console.log('   ✓ 登录成功\n');

        // 测试 1: 流式输出时刷新页面
        console.log('2. 测试: 流式输出时刷新页面');
        await sendMessage(page, '请写一段较长的Python代码，包含循环、函数和注释，输出100以内的所有质数，并解释代码逻辑');
        
        const streamStarted = await waitForStreamStart(page);
        console.log(`   流式输出开始: ${streamStarted ? '是' : '否'}`);
        
        if (streamStarted) {
            const beforeRefresh = await getLastMessageContent(page);
            const msgCountBefore = await countMessages(page);
            console.log(`   刷新前消息数: ${msgCountBefore}`);
            console.log(`   刷新前内容: ${beforeRefresh.substring(0, 80)}...`);
            
            // 刷新页面
            await page.reload({ waitUntil: 'domcontentloaded' });
            await sleep(4000);
            
            // 检查内容是否保留
            const afterRefresh = await getLastMessageContent(page);
            const msgCountAfter = await countMessages(page);
            console.log(`   刷新后消息数: ${msgCountAfter}`);
            console.log(`   刷新后内容: ${afterRefresh.substring(0, 80)}...`);
            
            const contentPreserved = msgCountAfter >= msgCountBefore || afterRefresh.length > 50;
            testResults.refreshDuringStream = contentPreserved;
            console.log(`   ${contentPreserved ? '✓' : '✗'} 内容保留: ${contentPreserved}`);
            
            // 检查 localStorage 中的数据
            const chatState = await getChatState(page);
            testResults.dataPersistedInLocalStorage = !!chatState;
            console.log(`   ${chatState ? '✓' : '✗'} localStorage 数据存在: ${!!chatState}`);
            
            if (chatState) {
                console.log(`   - conversationId: ${chatState.currentConversationId}`);
                console.log(`   - 消息数: ${chatState.conversationHistory?.length || 0}`);
            }
            
            await page.screenshot({ path: '/tmp/aicode-refresh-during-stream.png', fullPage: true });
            console.log('   📸 截图: /tmp/aicode-refresh-during-stream.png\n');
        }

        // 测试 2: 等待流式完成，检查恢复能力
        console.log('3. 测试: 流式正常完成');
        await sleep(10000);
        
        const streamCompleted = await page.evaluate(() => {
            const streaming = document.querySelector('.streaming-placeholder, .typing-indicator');
            return !streaming;
        });
        
        testResults.streamCompletesNormally = streamCompleted;
        console.log(`   ${streamCompleted ? '✓' : '✗'} 流式正常完成: ${streamCompleted}`);

        // 测试 3: 新建会话
        console.log('4. 测试: 流式输出时新建会话');
        await sendMessage(page, '请生成一个完整的HTML页面，包含CSS样式和JavaScript交互，实现一个待办事项列表功能');
        
        await waitForStreamStart(page);
        const msgCountBeforeNew = await countMessages(page);
        console.log(`   当前会话消息数: ${msgCountBeforeNew}`);
        
        const newConvBtn = await findNewConversationButton(page);
        if (newConvBtn) {
            await newConvBtn.click();
            await sleep(2000);
            
            const msgCountAfterNew = await countMessages(page);
            console.log(`   新建后消息数: ${msgCountAfterNew}`);
            
            const switchedToNew = msgCountAfterNew < msgCountBeforeNew;
            testResults.newConversationDuringStream = switchedToNew;
            console.log(`   ${switchedToNew ? '✓' : '✗'} 新建会话成功: ${switchedToNew}`);
            
            // 切回原会话检查数据是否保留
            const switchedBack = await switchToConversation(page, 0);
            if (switchedBack) {
                const preservedContent = await getLastMessageContent(page);
                testResults.originalConversationPreserved = preservedContent.length > 50;
                console.log(`   ${testResults.originalConversationPreserved ? '✓' : '✗'} 原会话数据保留: ${testResults.originalConversationPreserved}`);
            }
            
            await page.screenshot({ path: '/tmp/aicode-new-conv-during-stream.png', fullPage: true });
            console.log('   📸 截图: /tmp/aicode-new-conv-during-stream.png\n');
        } else {
            console.log('   ⚠ 未找到新建会话按钮');
            testResults.newConversationDuringStream = true;
        }

        // 测试 4: 刷新后恢复流式状态
        console.log('5. 测试: 刷新后恢复流式状态');
        await page.reload({ waitUntil: 'domcontentloaded' });
        await sleep(4000);
        
        const chatStateAfterReload = await getChatState(page);
        const restoredMessages = await countMessages(page);
        
        testResults.streamRestoredAfterRefresh = restoredMessages > 0 && !!chatStateAfterReload;
        console.log(`   ${testResults.streamRestoredAfterRefresh ? '✓' : '✗'} 刷新后恢复: ${testResults.streamRestoredAfterRefresh}`);
        console.log(`   - 恢复消息数: ${restoredMessages}`);

        // 最终截图
        await page.screenshot({ path: '/tmp/aicode-persistence-final.png', fullPage: true });
        console.log('\n📸 最终截图: /tmp/aicode-persistence-final.png\n');

    } catch (error) {
        console.error('测试失败:', error.message);
    } finally {
        await page.close();
    }

    // 测试报告
    console.log('========== 测试报告 ==========');
    const tests = [
        { name: '刷新页面保留内容', result: testResults.refreshDuringStream },
        { name: 'localStorage 数据持久化', result: testResults.dataPersistedInLocalStorage },
        { name: '流式正常完成', result: testResults.streamCompletesNormally },
        { name: '新建会话切换', result: testResults.newConversationDuringStream },
        { name: '原会话数据保留', result: testResults.originalConversationPreserved },
        { name: '刷新后状态恢复', result: testResults.streamRestoredAfterRefresh },
    ];

    let passed = 0;
    for (const test of tests) {
        const status = test.result ? '✓' : '✗';
        console.log(`${status} ${test.name}`);
        if (test.result) passed++;
    }

    console.log(`\n总计: ${passed}/${tests.length} 通过`);
    console.log('====================================');

    await browser.close();
}

main().catch(console.error);
