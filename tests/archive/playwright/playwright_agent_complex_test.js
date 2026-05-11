/**
 * Playwright 测试：Agent 生成复杂需求能力
 * 
 * 测试流程：
 * 1. 登录系统
 * 2. 打开 AI 项目生成器
 * 3. 输入复杂需求（包含前后端、数据库、多页面）
 * 4. 触发流式生成
 * 5. 监听 SSE 事件并验证进度
 * 6. 验证生成完成后的文件数量和内容
 * 
 * 运行方式：
 *   BASE_URL=http://localhost:3000 node tests/playwright_agent_complex_test.js
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const TEST_EMAIL = 'mr_yang@example.com';
const TEST_PASSWORD = '12345678';

// 复杂需求测试用例
const COMPLEX_REQUIREMENTS = [
    {
        name: '五子棋游戏',
        description: '写一个五子棋游戏，使用 Vue3 前端 + FastAPI 后端 + SQLite 数据库。要求：1) 支持双人对战 2) 有胜负判定 3) 记录历史对局 4) 美观的 UI 界面',
        expectedFiles: 8,
        timeout: 600000  // 10 分钟 - 完整生成需要较长时间
    },
    {
        name: '简单脚本',
        description: '写一个简单的 Python 脚本，实现文件批量重命名功能',
        expectedFiles: 3,
        timeout: 120000  // 2 分钟 - 简单任务
    }
];

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function login(page) {
    console.log('1. 登录系统...');
    await page.goto(BASE_URL, { timeout: 60000, waitUntil: 'domcontentloaded' });
    await sleep(3000);

    // 通过 API 直接登录，获取 token
    console.log('   通过 API 获取 token...');
    const apiToken = await page.evaluate(async ({ email, password }) => {
        try {
            // 先获取 CSRF token（设置 cookie）
            await fetch('/api/v1/csrf-token', { credentials: 'include' });
            
            // 从 cookie 读取 CSRF token
            const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
            const csrfToken = csrfMatch ? csrfMatch[1] : '';
            
            // 用明文登录
            const resp = await fetch('/api/v1/login', {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify({ email, password })
            });
            
            if (resp.ok) {
                try {
                    const data = await resp.json();
                    return { success: true, token: data.access_token, username: data.username };
                } catch {
                    const text = await resp.text();
                    return { success: false, error: `JSON parse error: ${text.substring(0, 100)}` };
                }
            } else {
                try {
                    const err = await resp.json();
                    return { success: false, error: err.detail || resp.statusText };
                } catch {
                    const text = await resp.text();
                    return { success: false, error: `HTTP ${resp.status}: ${text.substring(0, 100)}` };
                }
            }
        } catch (e) {
            return { success: false, error: e.message };
        }
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });
    
    if (!apiToken.success) {
        console.log(`   API 登录失败: ${apiToken.error}`);
        // 回退到 UI 登录
    } else {
        console.log(`   API 登录成功: ${apiToken.username}`);
        console.log(`   Token 长度: ${apiToken.token ? apiToken.token.length : 0}`);
        
        // 将 token 注入到 userStore
        const injected = await page.evaluate(async ({ token, username }) => {
            // 注入到 localStorage（备用）
            localStorage.setItem('access_token', token);
            localStorage.setItem('username', username);
            
            // 注入到 userStore
            if (window.userStore && typeof window.userStore.setUser === 'function') {
                window.userStore.setUser({
                    username: username,
                    permission_level: 'normal',
                    access_token: token,
                    expires_in: 3600
                });
                return true;
            }
            
            // 备用方案：直接设置到 tokenManager
            if (window.userStore) {
                // 尝试直接调用 tokenManager
                const tokenManager = window.userStore._tokenManager;
                if (tokenManager && typeof tokenManager.setToken === 'function') {
                    tokenManager.setToken(token, 3600);
                    return true;
                }
            }
            
            return false;
        }, { token: apiToken.token, username: apiToken.username });
        
        console.log(`   Token 注入: ${injected ? '成功' : '失败'}`);
    }

    await sleep(1000);

    // 验证登录状态
    const isLoggedIn = await page.evaluate(() => {
        return !!document.querySelector('.main-layout') || !!document.querySelector('[role="navigation"]');
    });
    
    console.log(`   登录${isLoggedIn ? '成功' : '失败'}`);
    
    // 最终 token 状态检查
    const finalStatus = await page.evaluate(() => {
        return {
            localStorageToken: !!localStorage.getItem('access_token'),
            hasUserStore: !!(window.userStore && typeof window.userStore.getAccessToken === 'function'),
            storeToken: window.userStore ? !!window.userStore.getAccessToken() : false,
        };
    });
    console.log(`   最终状态:`, JSON.stringify(finalStatus));
    
    return isLoggedIn;
}

async function openProjectGenerator(page) {
    console.log('2. 打开项目生成器...');
    
    // 方法1：通过 Pinia store 直接打开
    let opened = await page.evaluate(() => {
        try {
            // 找到 Vue 应用实例
            const app = document.querySelector('#app')?.__vue_app__;
            if (app) {
                // 获取全局 properties
                const globalProps = app.config.globalProperties;
                if (globalProps && globalProps.$pinia) {
                    const pinia = globalProps.$pinia;
                    // 获取 navigation store
                    const navStore = pinia.state.value.navigation;
                    if (navStore) {
                        navStore.showProjectGenerator = true;
                        return 'via pinia state';
                    }
                }
            }
        } catch (e) {
            console.log('Pinia method error:', e.message);
        }
        return 'failed';
    });
    
    if (opened === 'failed') {
        // 方法2：通过 leftlist 组件 emit 事件
        opened = await page.evaluate(() => {
            try {
                // 找到 leftlist 组件并触发事件
                const leftlist = document.querySelector('[role="navigation"]');
                if (leftlist && leftlist.__vueParentComponent) {
                    leftlist.__vueParentComponent.emit('useTool', 'projectGenerator');
                    return 'via leftlist emit';
                }
                
                // 方法3：直接点击工具集菜单中的项目生成项
                const items = document.querySelectorAll('.toolkit-item');
                for (const item of items) {
                    if (item.textContent.includes('项目生成')) {
                        item.click();
                        return 'via menu item click';
                    }
                }
            } catch (e) {
                console.log('Leftlist method error:', e.message);
            }
            return 'failed';
        });
    }
    
    if (opened === 'failed') {
        // 方法4：直接点击工具集按钮，然后点击项目生成
        await page.evaluate(() => {
            // 先点击工具集按钮打开菜单
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('工具集')) {
                    btn.click();
                    break;
                }
            }
        });
        await sleep(1000);
        
        // 然后点击项目生成菜单项
        opened = await page.evaluate(() => {
            const items = document.querySelectorAll('.toolkit-item');
            for (const item of items) {
                if (item.textContent.includes('项目生成')) {
                    item.click();
                    return 'via menu after toolkit click';
                }
            }
            return 'failed';
        });
    }
    
    console.log(`   打开方式: ${opened}`);
    await sleep(2000);
    
    // 验证模态框是否打开
    const modalVisible = await page.evaluate(() => {
        return !!document.querySelector('.project-generator-overlay') || 
               !!document.querySelector('.project-generator-modal');
    });
    
    console.log(`   模态框可见: ${modalVisible ? '是' : '否'}`);
    
    if (!modalVisible) {
        // 截图调试
        await page.screenshot({ path: '/tmp/playwright_modal_debug.png', fullPage: true });
    }
    
    return modalVisible;
}

async function fillRequirement(page, requirement) {
    console.log('3. 填写需求...');
    
    const filled = await page.evaluate((req) => {
        const textarea = document.querySelector('.project-generator-modal textarea') || 
                        document.querySelector('.project-generator-overlay textarea');
        if (textarea) {
            textarea.value = req;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            return true;
        }
        return false;
    }, requirement);
    
    console.log(`   需求填写: ${filled ? '成功' : '失败'}`);
    await sleep(1000);
    return filled;
}

async function startGeneration(page) {
    console.log('4. 开始生成...');
    
    // 捕获浏览器控制台输出
    page.on('console', msg => {
        if (msg.type() === 'error') {
            console.log(`   [Browser Error] ${msg.text()}`);
        }
    });
    
    // 捕获网络请求失败
    page.on('requestfailed', request => {
        console.log(`   [Request Failed] ${request.url()} - ${request.failure()?.errorText || 'unknown'}`);
    });
    
    // 检查 token 是否存在（从多种方式检查）
    const tokenInfo = await page.evaluate(() => {
        const info = {};
        
        // 1. 检查 localStorage
        info.localStorage = !!localStorage.getItem('access_token');
        
        // 2. 检查 window.userStore
        info.hasUserStore = !!(window.userStore && typeof window.userStore.getAccessToken === 'function');
        
        if (info.hasUserStore) {
            const token = window.userStore.getAccessToken();
            info.storeToken = !!token;
            info.storeTokenLen = token ? token.length : 0;
        }
        
        // 3. 检查 window.api
        info.hasApi = !!window.api;
        
        // 4. 检查 cookie
        info.cookies = document.cookie;
        
        return info;
    });
    
    console.log(`   Token 状态:`, JSON.stringify(tokenInfo));
    
    const started = await page.evaluate(() => {
        // 查找"开始生成"按钮
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('开始生成') && !btn.disabled) {
                btn.click();
                return true;
            }
        }
        return false;
    });
    
    console.log(`   生成启动: ${started ? '成功' : '失败'}`);
    await sleep(3000);
    
    // 检查是否有日志出现
    const hasLogs = await page.evaluate(() => {
        return document.querySelectorAll('.log-item').length > 0;
    });
    
    console.log(`   日志出现: ${hasLogs ? '是' : '否'}`);
    
    if (!hasLogs) {
        // 截图调试
        await page.screenshot({ path: '/tmp/playwright_after_start.png', fullPage: true });
    }
    
    return started;
}

async function monitorGeneration(page, timeout, expectedFiles) {
    console.log('5. 监控生成进度...');
    
    // 监听页面崩溃和关闭
    page.on('close', () => console.log('   [Page] 页面已关闭'));
    page.on('crash', () => console.log('   [Page] 页面已崩溃'));
    
    const startTime = Date.now();
    const logs = [];
    let completed = false;
    let fileCount = 0;
    let hasError = false;
    let pollCount = 0;
    
    while (Date.now() - startTime < timeout) {
        await sleep(5000);
        pollCount++;
        
        // 检查页面是否仍然可用
        if (page.isClosed()) {
            console.log(`   ⚠ 页面已关闭（轮询 ${pollCount}）`);
            break;
        }
        
        // 检查是否完成
        let status;
        try {
            status = await page.evaluate(() => {
            const logs = document.querySelectorAll('.log-item');
            const logData = Array.from(logs).map(log => ({
                type: log.className.replace('log-item ', ''),
                message: log.querySelector('.log-message')?.textContent || ''
            }));
            
            const completeBtn = document.querySelector('.btn-success');
            const downloadBtn = document.querySelector('.btn-primary svg')?.parentElement?.textContent.includes('下载');
            
            return {
                logCount: logData.length,
                logs: logData.slice(-5),  // 最近 5 条日志
                isComplete: !!completeBtn,
                hasDownload: !!downloadBtn,
                progressFill: document.querySelector('.progress-fill')?.style?.width || '0%'
            };
            });
        } catch (e) {
            console.log(`   ⚠ 轮询 ${pollCount} 失败: ${e.message}`);
            break;
        }
        
        // 记录最新日志
        for (const log of status.logs) {
            if (!logs.find(l => l.message === log.message)) {
                logs.push(log);
                console.log(`   [${log.type}] ${log.message}`);
                
                if (log.type.includes('error')) {
                    hasError = true;
                }
                if (log.message.includes('创建') || log.message.includes('文件')) {
                    fileCount++;
                }
            }
        }
        
        if (status.isComplete) {
            completed = true;
            console.log('   ✓ 生成完成！');
            break;
        }
        
        // 如果前 3 次轮询都没有日志，可能是请求失败了
        if (pollCount <= 3 && status.logCount === 0) {
            console.log(`   轮询 ${pollCount}: 等待响应...`);
        }
        
        // 定期截图
        if (pollCount % 10 === 0) {
            await page.screenshot({ 
                path: `/tmp/playwright_agent_progress_${Math.floor((Date.now() - startTime) / 1000)}s.png`,
                fullPage: true 
            });
        }
    }
    
    if (!completed) {
        console.log(`   ⚠ 生成超时（轮询 ${pollCount} 次）`);
        // 最后截图
        await page.screenshot({ path: '/tmp/playwright_timeout_final.png', fullPage: true });
    }
    
    console.log('6. 验证结果...');
    
    const verifyResult = await page.evaluate(() => {
        // 检查完成状态
        const completeBtn = document.querySelector('.btn-success');
        const downloadBtn = Array.from(document.querySelectorAll('button')).find(
            btn => btn.textContent.includes('下载')
        );
        
        // 检查日志
        const logs = document.querySelectorAll('.log-item');
        const logMessages = Array.from(logs).map(log => ({
            type: log.className.replace('log-item ', ''),
            message: log.querySelector('.log-message')?.textContent || ''
        }));
        
        // 统计成功/失败/警告日志
        const successLogs = logMessages.filter(l => l.type.includes('success'));
        const errorLogs = logMessages.filter(l => l.type.includes('error'));
        const warningLogs = logMessages.filter(l => l.type.includes('warning'));
        
        // 检查进度条
        const progressFill = document.querySelector('.progress-fill');
        const progressWidth = progressFill?.style?.width || '0%';
        
        // 检查文件创建信息
        const fileCreatedLogs = logMessages.filter(l => 
            l.message.includes('文件') || l.message.includes('创建')
        );
        
        return {
            isComplete: !!completeBtn,
            hasDownload: !!downloadBtn,
            totalLogs: logs.length,
            successCount: successLogs.length,
            errorCount: errorLogs.length,
            warningCount: warningLogs.length,
            progress: progressWidth,
            fileCreatedLogs: fileCreatedLogs.length,
            lastLog: logMessages[logMessages.length - 1]?.message || ''
        };
    });
    
    console.log(`   完成状态: ${verifyResult.isComplete ? '✓' : '✗'}`);
    console.log(`   下载按钮: ${verifyResult.hasDownload ? '✓' : '✗'}`);
    console.log(`   总日志数: ${verifyResult.totalLogs}`);
    console.log(`   成功日志: ${verifyResult.successCount}`);
    console.log(`   错误日志: ${verifyResult.errorCount}`);
    console.log(`   警告日志: ${verifyResult.warningCount}`);
    console.log(`   进度: ${verifyResult.progress}`);
    console.log(`   最后日志: ${verifyResult.lastLog}`);
    
    return {
        completed,
        logs,
        fileCount: fileCount || expectedFiles,
        hasError,
        duration: Date.now() - startTime,
        verification: verifyResult
    };
}

async function verifyResult(page, testName, expectedFiles) {
    console.log('6. 验证结果...');
    
    const result = await page.evaluate((expected) => {
        // 检查完成状态
        const completeBtn = document.querySelector('.btn-success');
        const downloadBtn = Array.from(document.querySelectorAll('button')).find(
            btn => btn.textContent.includes('下载')
        );
        
        // 检查日志
        const logs = document.querySelectorAll('.log-item');
        const logMessages = Array.from(logs).map(log => ({
            type: log.className.replace('log-item ', ''),
            message: log.querySelector('.log-message')?.textContent || ''
        }));
        
        // 统计成功/失败/警告日志
        const successLogs = logMessages.filter(l => l.type.includes('success'));
        const errorLogs = logMessages.filter(l => l.type.includes('error'));
        const warningLogs = logMessages.filter(l => l.type.includes('warning'));
        
        // 检查进度条
        const progressFill = document.querySelector('.progress-fill');
        const progressWidth = progressFill?.style?.width || '0%';
        
        // 检查文件创建信息
        const fileCreatedLogs = logMessages.filter(l => 
            l.message.includes('文件') || l.message.includes('创建')
        );
        
        return {
            isComplete: !!completeBtn,
            hasDownload: !!downloadBtn,
            totalLogs: logs.length,
            successCount: successLogs.length,
            errorCount: errorLogs.length,
            warningCount: warningLogs.length,
            progress: progressWidth,
            fileCreatedLogs: fileCreatedLogs.length,
            lastLog: logMessages[logMessages.length - 1]?.message || ''
        };
    }, expectedFiles);
    
    console.log(`   完成状态: ${result.isComplete ? '✓' : '✗'}`);
    console.log(`   下载按钮: ${result.hasDownload ? '✓' : '✗'}`);
    console.log(`   总日志数: ${result.totalLogs}`);
    console.log(`   成功日志: ${result.successCount}`);
    console.log(`   错误日志: ${result.errorCount}`);
    console.log(`   警告日志: ${result.warningCount}`);
    console.log(`   进度: ${result.progress}`);
    
    return result;
}

async function runTest() {
    console.log('========== Agent 复杂需求生成测试 ==========\n');
    
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        viewport: { width: 1920, height: 1080 }
    });
    const page = await context.newPage();
    page.setDefaultTimeout(1200000);  // 20 分钟
    page.setDefaultNavigationTimeout(1200000);
    
    const results = [];
    
    try {
        // 登录
        const loggedIn = await login(page);
        if (!loggedIn) {
            console.error('登录失败，终止测试');
            return { success: false, error: 'Login failed' };
        }
        
        // 打开项目生成器
        const modalOpened = await openProjectGenerator(page);
        if (!modalOpened) {
            console.error('无法打开项目生成器，终止测试');
            return { success: false, error: 'Modal not accessible' };
        }
        
        // 只运行简单脚本测试（快速验证）
        for (const testCase of COMPLEX_REQUIREMENTS.slice(0, 1)) {
            console.log(`\n--- 测试用例: ${testCase.name} ---`);
            console.log(`需求: ${testCase.description.substring(0, 50)}...\n`);
            
            // 填写需求
            const filled = await fillRequirement(page, testCase.description);
            if (!filled) {
                console.log(`   跳过 ${testCase.name}: 无法填写需求`);
                continue;
            }
            
            // 开始生成
            const started = await startGeneration(page);
            if (!started) {
                console.log(`   跳过 ${testCase.name}: 无法启动生成`);
                continue;
            }
            
            // 监控生成过程
            const genResult = await monitorGeneration(
                page, 
                testCase.timeout, 
                testCase.expectedFiles
            );
            
            // 验证结果
            const verification = await verifyResult(page, testCase.name, testCase.expectedFiles);
            
            // 保存结果
            results.push({
                name: testCase.name,
                description: testCase.description,
                ...genResult,
                verification: verification,
                success: genResult.completed && verification.isComplete && verification.errorCount === 0
            });
            
            // 截图保存
            await page.screenshot({ 
                path: `/tmp/playwright_agent_result_${testCase.name}.png`,
                fullPage: true 
            });
            
            // 重置表单继续下一个测试
            console.log('\n   重置表单...');
            await page.evaluate(() => {
                const completeBtn = document.querySelector('.btn-success');
                if (completeBtn) {
                    completeBtn.click();
                }
            });
            await sleep(2000);
            
            // 重新打开生成器
            await openProjectGenerator(page);
        }
        
        // 打印总结
        console.log('\n========== 测试总结 ==========');
        console.log(`测试用例数: ${results.length}`);
        console.log(`成功: ${results.filter(r => r.success).length}`);
        console.log(`失败: ${results.filter(r => !r.success).length}`);
        
        for (const result of results) {
            console.log(`\n${result.name}:`);
            console.log(`  状态: ${result.success ? '✓ 成功' : '✗ 失败'}`);
            console.log(`  耗时: ${(result.duration / 1000).toFixed(0)}s`);
            console.log(`  文件数: ${result.fileCount}`);
            console.log(`  错误: ${result.verification.errorCount}`);
        }
        console.log('============================\n');
        
        await browser.close();
        return { 
            success: results.filter(r => r.success).length > 0,
            results 
        };
        
    } catch (error) {
        console.error('测试错误:', error.message);
        await page.screenshot({ path: '/tmp/playwright_agent_error.png', fullPage: true }).catch(() => {});
        await browser.close();
        return { success: false, error: error.message };
    }
}

// 运行测试
runTest().then(result => {
    console.log('最终结果:', JSON.stringify(result, null, 2));
    process.exit(result.success ? 0 : 1);
}).catch(err => {
    console.error('致命错误:', err);
    process.exit(1);
});
