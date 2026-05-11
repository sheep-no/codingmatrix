/**
 * 工具项高度调试测试
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

async function runTest() {
    console.log('=== 工具项高度调试测试 ===');
    console.log(`目标 URL: ${BASE_URL}`);
    
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    
    try {
        await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(3000);
        
        // 点击工具集按钮展开菜单
        await page.click('#toolkit');
        await page.waitForTimeout(1000);
        
        // 截图当前状态
        await page.screenshot({ path: 'test_output/toolkit-height-check.png' });
        
        // 检查各个元素的实际高度
        const heightInfo = await page.evaluate(() => {
            const results = {};
            
            // 检查菜单容器
            const menu = document.querySelector('.toolkit-menu');
            if (menu) {
                const rect = menu.getBoundingClientRect();
                const computed = getComputedStyle(menu);
                results.menu = {
                    height: rect.height,
                    offsetHeight: menu.offsetHeight,
                    display: computed.display,
                    flexShrink: computed.flexShrink,
                    padding: computed.padding
                };
            }
            
            // 检查每个工具项
            const items = document.querySelectorAll('.toolkit-item');
            results.items = [];
            items.forEach((item, index) => {
                const rect = item.getBoundingClientRect();
                const computed = getComputedStyle(item);
                results.items.push({
                    index,
                    text: item.querySelector('span')?.textContent || '',
                    height: rect.height,
                    offsetHeight: item.offsetHeight,
                    minHeight: computed.minHeight,
                    padding: computed.padding,
                    display: computed.display,
                    alignItems: computed.alignItems,
                    flexShrink: computed.flexShrink,
                    lineHeight: computed.lineHeight
                });
            });
            
            // 检查按钮高度
            const newSpeak = document.getElementById('newSpeak');
            const toolkitBtn = document.getElementById('toolkit');
            
            if (newSpeak) {
                const rect = newSpeak.getBoundingClientRect();
                const computed = getComputedStyle(newSpeak);
                results.newSpeakBtn = { 
                    height: rect.height,
                    display: computed.display,
                    padding: computed.padding,
                    fontSize: computed.fontSize
                };
            }
            
            if (toolkitBtn) {
                const rect = toolkitBtn.getBoundingClientRect();
                const computed = getComputedStyle(toolkitBtn);
                results.toolkitBtn = { 
                    height: rect.height,
                    display: computed.display,
                    padding: computed.padding,
                    fontSize: computed.fontSize
                };
            }
            
            return results;
        });
        
        console.log('\n=== 高度检查结果 ===');
        console.log('新建会话按钮高度:', heightInfo.newSpeakBtn?.height);
        if (heightInfo.newSpeakBtn) {
            console.log('  display:', heightInfo.newSpeakBtn.display);
            console.log('  padding:', heightInfo.newSpeakBtn.padding);
            console.log('  font-size:', heightInfo.newSpeakBtn.fontSize);
        }
        
        console.log('工具集按钮高度:', heightInfo.toolkitBtn?.height);
        if (heightInfo.toolkitBtn) {
            console.log('  display:', heightInfo.toolkitBtn.display);
            console.log('  padding:', heightInfo.toolkitBtn.padding);
            console.log('  font-size:', heightInfo.toolkitBtn.fontSize);
        }
        
        if (heightInfo.menu) {
            console.log('\n菜单容器:');
            console.log('  高度:', heightInfo.menu.height);
            console.log('  display:', heightInfo.menu.display);
            console.log('  flex-shrink:', heightInfo.menu.flexShrink);
            console.log('  padding:', heightInfo.menu.padding);
        }
        
        console.log('\n工具项:');
        heightInfo.items?.forEach(item => {
            console.log(`  [${item.index}] "${item.text}": ${item.height}px (padding: ${item.padding})`);
        });
        
    } catch (error) {
        console.error('测试执行错误:', error.message);
    } finally {
        await browser.close();
    }
    
    console.log('\n=== 测试完成 ===');
}

runTest().catch(console.error);
