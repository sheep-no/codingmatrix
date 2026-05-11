/**
 * 按钮样式详细调试
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

async function runTest() {
    console.log('=== 按钮样式详细调试 ===');
    
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    
    try {
        await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(3000);
        
        const buttonStyles = await page.evaluate(() => {
            const newSpeak = document.getElementById('newSpeak');
            const toolkit = document.getElementById('toolkit');
            
            function getDetailedStyles(el) {
                const computed = getComputedStyle(el);
                return {
                    height: el.getBoundingClientRect().height,
                    display: computed.display,
                    padding: computed.padding,
                    paddingTop: computed.paddingTop,
                    paddingBottom: computed.paddingBottom,
                    paddingLeft: computed.paddingLeft,
                    paddingRight: computed.paddingRight,
                    lineHeight: computed.lineHeight,
                    fontSize: computed.fontSize,
                    minHeight: computed.minHeight,
                    boxSizing: computed.boxSizing
                };
            }
            
            return {
                newSpeak: newSpeak ? getDetailedStyles(newSpeak) : null,
                toolkit: toolkit ? getDetailedStyles(toolkit) : null
            };
        });
        
        console.log('\n新建会话按钮:');
        console.log(JSON.stringify(buttonStyles.newSpeak, null, 2));
        
        console.log('\n工具集按钮:');
        console.log(JSON.stringify(buttonStyles.toolkit, null, 2));
        
        // 截图
        await page.screenshot({ path: 'test_output/buttons-debug.png', fullPage: true });
        
    } catch (error) {
        console.error('错误:', error.message);
    } finally {
        await browser.close();
    }
}

runTest().catch(console.error);
