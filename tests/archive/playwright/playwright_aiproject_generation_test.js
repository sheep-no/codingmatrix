const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const TEST_EMAIL = 'mr_yang@example.com';
const TEST_PASSWORD = '123456';

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTest() {
    console.log('Starting AI Project Generation Test with Download...');
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        viewport: { width: 1920, height: 1080 }
    });
    const page = await context.newPage();

    try {
        // 1. 登录
        console.log('1. Logging in...');
        await page.goto(BASE_URL, { timeout: 60000, waitUntil: 'domcontentloaded' });
        await sleep(3000);

        const inputs = await page.$$('input');
        for (const input of inputs) {
            const type = await input.getAttribute('type');
            const placeholder = await input.getAttribute('placeholder') || '';
            if (type === 'email' || placeholder.includes('邮箱') || placeholder.includes('email')) {
                await input.fill(TEST_EMAIL);
            } else if (type === 'password') {
                await input.fill(TEST_PASSWORD);
            }
        }

        const buttons = await page.$$('button');
        for (const btn of buttons) {
            const text = await btn.textContent();
            if (text.includes('登录')) {
                await btn.click();
                break;
            }
        }

        await sleep(5000);
        console.log('   Login completed');

        // 2. 打开工具集
        console.log('2. Opening toolkit menu...');
        
        // 方法1：直接点击工具集按钮
        await page.evaluate(() => {
            // 找到工具集按钮并点击
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('工具集')) {
                    btn.click();
                    break;
                }
            }
        });
        await sleep(1500);
        await page.screenshot({ path: '/tmp/playwright_step2_menu.png', fullPage: true });

        // 3. 打印菜单内容
        console.log('3. Checking toolkit menu content...');
        const menuContent = await page.evaluate(() => {
            const toolkitMenu = document.querySelector('.toolkit-menu');
            if (toolkitMenu) {
                const items = toolkitMenu.querySelectorAll('.toolkit-item');
                return Array.from(items).map(item => item.textContent.trim().substring(0, 30));
            }
            return [];
        });
        console.log(`   Menu items: ${JSON.stringify(menuContent)}`);

        // 4. 点击 AI 项目生成 - 直接调用 store 方法
        console.log('4. Opening AI Project Generator...');
        
        // 直接调用 Vue 应用的 store 来打开模态框
        const opened = await page.evaluate(() => {
            // 尝试找到 Vue 应用实例
            const app = document.querySelector('#app').__vue_app__;
            if (app) {
                // 尝试获取 navigation store
                const pinia = app.config.globalProperties.$pinia;
                if (pinia) {
                    const stores = pinia.state.value;
                    console.log('Available stores:', Object.keys(stores));
                }
            }
            
            // 尝试直接调用 useNavigationStore
            try {
                const { useNavigationStore } = window.__VUE_APP__?.pinia || {};
                if (useNavigationStore) {
                    const store = useNavigationStore();
                    if (store.showTool) {
                        store.showTool('projectGenerator');
                        return 'via store.showTool';
                    }
                }
            } catch (e) {
                console.log('Store method error:', e.message);
            }
            
            // 尝试通过 emit 事件
            try {
                const leftlist = document.querySelector('[role="navigation"]');
                if (leftlist && leftlist.__vueParentComponent) {
                    leftlist.__vueParentComponent.emit('use-tool', 'projectGenerator');
                    return 'via emit';
                }
            } catch (e) {
                console.log('Emit method error:', e.message);
            }
            
            return 'failed';
        });
        console.log('   Opening result:', opened);

        await sleep(2000);
        await page.screenshot({ path: '/tmp/playwright_step4_after_click.png', fullPage: true });

        // 5. 检查模态框
        console.log('5. Checking modal...');
        
        // 检查 ProjectGenerator 组件
        const modalInfo = await page.evaluate(() => {
            // 检查 ProjectGenerator 组件是否存在
            const componentEl = document.querySelector('.project-generator-modal');
            const overlayEl = document.querySelector('.project-generator-overlay');
            
            // 检查组件的 visible 属性（通过检查渲染的类）
            const allModals = document.querySelectorAll('[class*="project-generator"]');
            
            // 检查 Vue 组件实例 - 尝试不同的方式
            let vueInstance = null;
            const appEl = document.querySelector('#app');
            
            // 方法1: 通过 __vue_app__
            if (appEl?._vei) {
                vueInstance = { source: '__vei', keys: Object.keys(appEl._vei) };
            }
            
            // 检查 main-layout 下的所有组件
            const mainLayout = document.querySelector('.main-layout');
            const mainChildren = mainLayout?.children?.length || 0;
            
            // 检查是否有任何弹窗/模态框相关的元素
            const allOverlays = document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="dialog"]');
            const overlayDetails = Array.from(allOverlays).map(el => ({
                className: el.className,
                display: window.getComputedStyle(el).display,
                visibility: window.getComputedStyle(el).visibility,
                opacity: window.getComputedStyle(el).opacity,
                tagName: el.tagName
            }));
            
            // 检查 Leftlist 组件的 refs
            let leftlistRef = null;
            const leftlistEl = document.querySelector('[role="navigation"]');
            if (leftlistEl?.__vueParentComponent) {
                leftlistRef = 'found';
            }
            
            return {
                componentEl: !!componentEl,
                overlayEl: !!overlayEl,
                allModalsCount: allModals.length,
                allOverlaysCount: allOverlays.length,
                overlayDetails: overlayDetails,
                mainChildren: mainChildren,
                leftlistRef: leftlistRef,
                vueInstance: vueInstance
            };
            return {
                componentEl: !!componentEl,
                overlayEl: !!overlayEl,
                allModalsCount: allModals.length,
                allOverlaysCount: allOverlays.length,
                mainChildren: mainChildren,
                leftlistRef: leftlistRef,
                vueInstance: vueInstance
            };
        });
        console.log('   Modal info:', JSON.stringify(modalInfo, null, 2));
        
        const modalVisible = modalInfo.componentEl || modalInfo.overlayEl;

        if (modalVisible) {
            console.log('   Modal is OPEN!');
            
            // 6. 填写表单
            console.log('6. Filling requirement...');
            await page.evaluate(() => {
                const textarea = document.querySelector('.project-generator-modal textarea');
                if (textarea) {
                    textarea.value = '创建一个简单的计算器 HTML 页面';
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });
            await sleep(1000);
            await page.screenshot({ path: '/tmp/playwright_step6_form.png', fullPage: true });

            // 7. 点击开始生成
            console.log('7. Starting generation...');
            await page.evaluate(() => {
                const btn = document.querySelector('.project-generator-modal button.btn-primary');
                if (btn && !btn.disabled) {
                    btn.click();
                }
            });
            await sleep(2000);
            await page.screenshot({ path: '/tmp/playwright_step7_started.png', fullPage: true });

            // 8. 等待生成
            console.log('8. Waiting for generation...');
            const maxWait = 180000;
            const startTime = Date.now();
            let genComplete = false;

            while (Date.now() - startTime < maxWait) {
                await sleep(5000);
                
                const done = await page.evaluate(() => {
                    const completeBtn = document.querySelector('.project-generator-modal button.btn-success');
                    return !!completeBtn;
                });
                
                if (done) {
                    genComplete = true;
                    console.log('   Generation completed!');
                    break;
                }
                
                const logs = await page.$$('.log-item');
                if (logs.length > 0) {
                    const lastLog = logs[logs.length - 1];
                    const logText = await lastLog.textContent();
                    console.log(`   ${logs.length}: ${logText.substring(0, 60)}`);
                }
            }

            await page.screenshot({ path: '/tmp/playwright_step8_result.png', fullPage: true });

            // 9. 检查下载按钮
            console.log('9. Checking download button...');
            const hasDownload = await page.evaluate(() => {
                const btns = document.querySelectorAll('.project-generator-modal button');
                for (const btn of btns) {
                    if (btn.textContent.includes('下载')) {
                        return true;
                    }
                }
                return false;
            });

            console.log(`   Download button: ${hasDownload ? 'FOUND' : 'NOT FOUND'}`);

            console.log('\n========== TEST SUMMARY ==========');
            console.log(`Modal Opened: YES`);
            console.log(`Generation Complete: ${genComplete ? 'YES' : 'NO'}`);
            console.log(`Download Button: ${hasDownload ? 'FOUND' : 'NOT FOUND'}`);
            console.log('==================================\n');

        } else {
            console.log('   Modal NOT opened');
            console.log('\n========== TEST SUMMARY ==========');
            console.log('Modal Opened: NO');
            console.log('');
            console.log('The ProjectGenerator modal may not be accessible.');
            console.log('Please check if the toolkit menu is working.');
            console.log('==================================\n');
        }

        await browser.close();
        return { success: true };

    } catch (error) {
        console.error('Test error:', error.message);
        await page.screenshot({ path: '/tmp/playwright_error.png', fullPage: true }).catch(() => {});
        await browser.close();
        return { success: false, error: error.message };
    }
}

runTest().then(result => {
    console.log('Final result:', result);
    process.exit(0);
}).catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});