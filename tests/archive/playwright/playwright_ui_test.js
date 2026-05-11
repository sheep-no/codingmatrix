/**
 * UI 改进视觉测试
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

async function runTest() {
    console.log('=== UI 改进视觉测试 ===');
    console.log(`目标 URL: ${BASE_URL}`);
    
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    
    try {
        // 导航到页面
        await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(3000);
        
        // 截图完整左侧边栏
        const sidebar = await page.$('#leftlist');
        if (sidebar) {
            await sidebar.screenshot({ path: 'test_output/sidebar-ui-updated.png' });
            console.log('已保存侧边栏截图到 test_output/sidebar-ui-updated.png');
        }
        
        // 点击工具集按钮展开菜单
        const toolkitBtn = await page.$('#toolkit');
        if (toolkitBtn) {
            await toolkitBtn.click();
            await page.waitForTimeout(1000);
            
            // 截图展开的工具菜单
            await page.screenshot({ path: 'test_output/toolkit-menu-updated.png' });
            console.log('已保存工具菜单截图到 test_output/toolkit-menu-updated.png');
        }
        
    } catch (error) {
        console.error('测试执行错误:', error.message);
    } finally {
        await browser.close();
    }
    
    console.log('\n=== 测试完成 ===');
}

runTest().catch(console.error);
