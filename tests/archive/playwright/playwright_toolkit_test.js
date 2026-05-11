const { chromium } = require('@playwright/test');

const CONFIG = {
    BASE_URL: 'http://localhost:3001',
    API_BASE: 'http://localhost:8080',
    TEST_USERS: {
        superadmin: { email: 'mr_yang@example.com', password: '12345678', level: 'superadmin' },
        admin: { email: 'admin_test@example.com', password: '12345678', level: 'admin' },
        normal: { email: 'normal_user@example.com', password: '12345678', level: 'normal' }
    }
};

// 工具集菜单中定义的所有工具
const ALL_TOOLS = [
    { name: 'chartEditor', label: '图表编辑器', expected: 'all' },
    { name: 'nginxConfig', label: 'Nginx 配置', expected: 'all' },
    { name: 'dockerConfig', label: 'Docker 配置', expected: 'all' },
    { name: 'systemInfo', label: '系统检测', expected: 'all' },
    { name: 'admin', label: '管理员面板', expected: 'superadmin' },
    { name: 'virtualGirl', label: 'AI 虚拟姬', expected: 'all' },
    { name: 'fileManager', label: '文件管理', expected: 'all' },
    { name: 'pptGenerator', label: 'PPT 生成', expected: 'all' },
    { name: 'imageGenerator', label: 'AI 绘画', expected: 'all' },
    { name: 'projectGenerator', label: 'AI 项目生成', expected: 'all' },
    { name: 'ephemeralWorkflow', label: '临时工作流', expected: 'all' },
    { name: 'searchHistory', label: '搜索历史', expected: 'all' },
];

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function loginAsUser(page, user) {
    console.log(`   登录用户: ${user.email} (${user.level})`);
    
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
    const username = await page.textContent('.username') || await page.textContent('.user-info');
    console.log(`   ✓ 登录成功: ${username}`);
    
    const permissionLevel = await page.evaluate(() => localStorage.getItem('permission_level'));
    console.log(`   ✓ 权限级别: ${permissionLevel}`);
    
    return { username, permissionLevel };
}

async function testToolkitVisibility(page, userLevel) {
    console.log(`\n   测试工具集可见性 (${userLevel})...`);
    
    // 点击工具集按钮
    await page.waitForSelector('#toolkit', { timeout: 10000 });
    await page.click('#toolkit');
    await sleep(500);
    
    // 检查工具集菜单是否显示
    const menuVisible = await page.isVisible('.toolkit-menu');
    console.log(`   工具集菜单: ${menuVisible ? '可见 ✓' : '不可见 ✗'}`);
    
    if (!menuVisible) return { success: false, error: '菜单不可见', tools: {} };
    
    // 检查每个工具项的可见性
    const results = {};
    const items = await page.$$('.toolkit-item');
    
    for (const item of items) {
        const text = await item.textContent();
        const isVisible = await item.isVisible();
        const label = text.trim();
        
        // 找到对应的工具定义
        const toolDef = ALL_TOOLS.find(t => t.label === label);
        if (toolDef) {
            results[toolDef.name] = {
                found: true,
                visible: isVisible,
                label: label
            };
            console.log(`     ${isVisible ? '✓' : '✗'} ${label}`);
        } else if (label) {
            results[label] = {
                found: true,
                visible: isVisible,
                label: label,
                unknown: true
            };
            console.log(`     ? ${label} (未知工具)`);
        }
    }
    
    // 检查缺失的工具
    for (const tool of ALL_TOOLS) {
        if (!results[tool.name]) {
            results[tool.name] = {
                found: false,
                visible: false,
                label: tool.label
            };
            console.log(`     - 缺失: ${tool.label}`);
        }
    }
    
    // 验证权限控制
    const adminTool = results['admin'];
    if (userLevel === 'superadmin') {
        if (adminTool && adminTool.visible) {
            console.log(`   ✓ 超级用户可以看到管理员面板`);
        } else {
            console.log(`   ✗ 超级用户应该看到管理员面板`);
        }
    } else {
        if (adminTool && adminTool.visible) {
            console.log(`   ✗ 非超级用户不应该看到管理员面板`);
        } else {
            console.log(`   ✓ 非超级用户看不到管理员面板`);
        }
    }
    
    return { success: menuVisible, results };
}

async function closeAllOpenPanels(page) {
    // 关闭所有已打开的工具面板
    const overlaySelectors = [
        '.nginx-config-overlay .close-btn',
        '.docker-config-overlay .close-btn',
        '.chart-editor-overlay .close-btn',
        '.system-info-overlay .close-btn',
        '.virtual-girl-overlay .close-btn',
        '.file-manager-overlay .close-btn',
        '.ppt-generator-overlay .close-btn',
        '.image-generator-overlay .close-btn',
        '.project-generator-overlay .close-btn',
        '.ephemeral-workflow-overlay .close-btn',
        '.admin-panel-overlay .close-btn',
    ];
    
    for (const selector of overlaySelectors) {
        const btn = await page.$(selector);
        if (btn && await btn.isVisible()) {
            await btn.click();
            await sleep(200);
        }
    }
    
    // 额外尝试点击任何可见的 overlay 背景（避开 modal 内容区）
    const overlayBackgrounds = [
        '.nginx-config-overlay',
        '.docker-config-overlay',
        '.chart-editor-overlay',
    ];
    
    for (const selector of overlayBackgrounds) {
        const overlay = await page.$(selector);
        if (overlay && await overlay.isVisible()) {
            // 点击 overlay 的角落（避开 modal 内容）
            const box = await overlay.boundingBox();
            if (box) {
                await page.mouse.click(box.x + box.width - 10, box.y + 10);
                await sleep(300);
            }
        }
    }
    
    await sleep(500);
}

async function testToolkitClick(page, toolName, label) {
    console.log(`\n   测试点击: ${label} (${toolName})...`);
    
    try {
        // 先关闭所有已打开的面板
        await closeAllOpenPanels(page);
        
        // 确保工具集菜单是关闭状态
        const menuVisible = await page.isVisible('.toolkit-menu');
        if (menuVisible) {
            await page.click('#toolkit');
            await sleep(300);
        }
        
        // 重新打开工具集菜单
        await page.waitForSelector('#toolkit', { timeout: 10000 });
        await page.click('#toolkit');
        await sleep(500);
        
        // 等待菜单项渲染
        await page.waitForSelector('.toolkit-item', { timeout: 5000 });
        
        // 找到对应的工具项并点击
        const items = await page.$$('.toolkit-item');
        for (const item of items) {
            const text = await item.textContent();
            if (text.trim() === label) {
                await item.click();
                await sleep(1000);
                
                // 截图
                const screenshotPath = `/tmp/toolkit-${toolName}-${Date.now()}.png`;
                await page.screenshot({ path: screenshotPath, fullPage: false });
                console.log(`     📸 截图: ${screenshotPath}`);
                
                // 检查是否有对应的面板出现
                const bodyHTML = await page.innerHTML('body');
                const hasPanel = bodyHTML.includes('overlay') || bodyHTML.includes('modal') || bodyHTML.includes(label);
                
                console.log(`     ${hasPanel ? '✓' : '⚠'} 面板状态: ${hasPanel ? '已打开' : '无法确认'}`);
                
                return { success: true, hasPanel };
            }
        }
        
        console.log(`     ⚠ 工具项未找到`);
        return { success: false, error: '工具项未找到' };
        
    } catch (error) {
        console.log(`     ✗ 测试失败: ${error.message.substring(0, 80)}`);
        return { success: false, error: error.message };
    }
}

async function main() {
    console.log('========== 工具集按钮功能测试 ==========\n');
    
    const browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const testResults = {};

    for (const [userType, user] of Object.entries(CONFIG.TEST_USERS)) {
        console.log(`\n========== 测试用户类型: ${userType} ==========`);
        
        const page = await browser.newPage({
            viewport: { width: 1280, height: 800 }
        });

        try {
            // 1. 登录
            console.log('\n1. 登录系统...');
            const { username, permissionLevel } = await loginAsUser(page, user);

            // 2. 测试工具集可见性
            console.log('\n2. 工具集可见性测试...');
            const visibilityResults = await testToolkitVisibility(page, userType);
            testResults[userType] = {
                visibility: visibilityResults,
                tools: {}
            };

            // 3. 测试点击前3个工具
            console.log('\n3. 工具点击测试（前3个）...');
            const toolsToTest = ALL_TOOLS.slice(0, 3);
            for (const tool of toolsToTest) {
                if (tool.expected !== 'all' && userType !== tool.expected) {
                    console.log(`     ⊘ 跳过 ${tool.label} (仅 ${tool.expected})`);
                    continue;
                }
                
                const clickResult = await testToolkitClick(page, tool.name, tool.label);
                testResults[userType].tools[tool.name] = clickResult;
            }

            // 4. 截图保存
            const screenshotPath = `/tmp/toolkit-${userType}-final-${Date.now()}.png`;
            await page.screenshot({ path: screenshotPath, fullPage: true });
            console.log(`\n📸 最终截图: ${screenshotPath}`);

        } catch (error) {
            console.error('测试失败:', error.message);
            testResults[userType] = { error: error.message };
        } finally {
            await page.close();
        }
    }

    // 总结报告
    console.log('\n========== 测试报告 ==========');
    
    let totalToolsTested = 0;
    let totalToolsPassed = 0;
    
    for (const [userType, result] of Object.entries(testResults)) {
        console.log(`\n${userType}:`);
        if (result.error) {
            console.log(`  错误: ${result.error}`);
            continue;
        }
        
        const visibility = result.visibility;
        console.log(`  工具集菜单: ${visibility.success ? '✓ 可见' : '✗ 不可见'}`);
        
        // 统计可见的工具
        let visibleCount = 0;
        let totalTools = 0;
        
        for (const [toolName, toolResult] of Object.entries(visibility.results)) {
            if (!toolResult.unknown) {
                totalTools++;
                if (toolResult.visible) {
                    visibleCount++;
                }
            }
        }
        
        console.log(`  工具可见性: ${visibleCount}/${totalTools} 可见`);
        
        // 统计点击测试
        let clickPassed = 0;
        let clickTotal = 0;
        
        for (const [toolName, toolResult] of Object.entries(result.tools)) {
            clickTotal++;
            totalToolsTested++;
            if (toolResult.success) {
                clickPassed++;
                totalToolsPassed++;
            }
        }
        
        console.log(`  工具点击: ${clickPassed}/${clickTotal} 通过`);
    }
    
    console.log(`\n总计: ${totalToolsPassed}/${totalToolsTested} 通过`);

    console.log('\n====================================');

    await browser.close();
}

main().catch(console.error);
