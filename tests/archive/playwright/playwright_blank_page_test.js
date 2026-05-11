/**
 * 前端空白页面调试测试
 * 
 * 检查前端页面为什么加载后什么都没有显示
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

async function runTest() {
    console.log('=== 前端空白页面调试测试 ===');
    console.log(`目标 URL: ${BASE_URL}`);
    
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    
    // 收集控制台消息和错误
    const consoleMessages = [];
    const pageErrors = [];
    const failedRequests = [];
    
    page.on('console', msg => {
        consoleMessages.push({ type: msg.type(), text: msg.text() });
    });
    
    page.on('pageerror', error => {
        pageErrors.push(error.message);
        console.error('页面错误:', error.message);
    });
    
    page.on('requestfailed', request => {
        failedRequests.push({
            url: request.url(),
            error: request.failure()?.errorText
        });
    });
    
    try {
        // 导航到页面
        console.log('\n1. 正在导航...');
        const response = await page.goto(BASE_URL, { 
            waitUntil: 'domcontentloaded',
            timeout: 30000
        });
        console.log(`   响应状态: ${response.status()}`);
        
        // 等待一段时间让 Vue 应用加载
        await page.waitForTimeout(5000);
        
        // 截图
        await page.screenshot({ path: 'test_output/blank-page-full.png', fullPage: true });
        await page.screenshot({ path: 'test_output/blank-page-viewport.png' });
        console.log('\n2. 已保存截图到 test_output/');
        
        // 检查页面标题
        const title = await page.title();
        console.log(`\n3. 页面标题: "${title}"`);
        
        // 检查 HTML 内容
        const html = await page.content();
        console.log(`\n4. HTML 长度: ${html.length} 字符`);
        
        // 检查 #app 元素
        const appElement = await page.$('#app');
        if (appElement) {
            const appHtml = await appElement.innerHTML();
            console.log(`\n5. #app 内容长度: ${appHtml.length} 字符`);
            console.log(`   #app 内容预览: ${appHtml.substring(0, 300)}...`);
            
            // 检查是否有 Vue 组件渲染
            const children = await appElement.$$('*');
            console.log(`   #app 子元素数量: ${children.length}`);
        } else {
            console.log('\n5. #app 元素不存在!');
        }
        
        // 检查关键组件
        console.log('\n6. 关键组件检查:');
        const components = [
            { selector: '#leftlist', name: '左侧边栏' },
            { selector: '.center-content-wrapper', name: '中心内容区' },
            { selector: '.bottom-input-container', name: '底部输入框' },
            { selector: '.main-layout', name: '主布局' },
            { selector: '.toast-container', name: 'Toast 通知' }
        ];
        
        for (const comp of components) {
            const el = await page.$(comp.selector);
            console.log(`   ${comp.name} (${comp.selector}): ${el ? '存在' : '不存在'}`);
        }
        
        // 检查网络请求
        console.log('\n7. 网络请求统计:');
        const requests = [];
        page.on('request', req => requests.push(req.url()));
        
        // 检查 JS 文件加载
        const jsFiles = consoleMessages.filter(m => 
            m.text.includes('.js') || m.text.includes('chunk')
        );
        console.log(`   JS 相关消息: ${jsFiles.length} 条`);
        
        // 输出错误信息
        if (pageErrors.length > 0) {
            console.log('\n8. === 页面错误 ===');
            pageErrors.forEach((err, i) => console.log(`   ${i + 1}. ${err}`));
        }
        
        if (failedRequests.length > 0) {
            console.log('\n9. === 失败的请求 ===');
            failedRequests.forEach((req, i) => console.log(`   ${i + 1}. ${req.url} - ${req.error}`));
        }
        
        // 检查控制台错误
        const errorMessages = consoleMessages.filter(m => 
            m.type === 'error' || m.text.includes('Error') || m.text.includes('error')
        );
        if (errorMessages.length > 0) {
            console.log('\n10. === 控制台错误 ===');
            errorMessages.slice(0, 20).forEach((msg, i) => console.log(`   ${i + 1}. [${msg.type}] ${msg.text.substring(0, 200)}`));
        }
        
        // 检查 Vue 是否正确初始化
        const vueCheck = await page.evaluate(() => {
            const app = document.querySelector('#app');
            return {
                hasApp: !!app,
                hasVueInstance: !!app?.__vue_app__,
                hasChildNodes: app?.childNodes?.length || 0,
                innerHTML: app?.innerHTML?.substring(0, 500) || ''
            };
        });
        
        console.log('\n11. === Vue 状态 ===');
        console.log(`   有 #app: ${vueCheck.hasApp}`);
        console.log(`   有 Vue 实例: ${vueCheck.hasVueInstance}`);
        console.log(`   子节点数: ${vueCheck.hasChildNodes}`);
        console.log(`   内容预览: ${vueCheck.innerHTML.substring(0, 200)}`);
        
        // 尝试手动触发 Vue 挂载
        console.log('\n12. 尝试检查 main.js 导入...');
        const scriptTags = await page.$$('script[type="module"]');
        console.log(`   模块脚本数量: ${scriptTags.length}`);
        
        for (const script of scriptTags.slice(0, 3)) {
            const src = await script.getAttribute('src');
            console.log(`   脚本 src: ${src}`);
            
            // 尝试加载脚本内容
            if (src && src.startsWith('/')) {
                const scriptResp = await page.goto(`${BASE_URL}${src}`, { timeout: 10000 }).catch(() => null);
                if (scriptResp) {
                    console.log(`   脚本响应状态: ${scriptResp.status()}`);
                    await page.goBack();
                }
            }
        }
        
    } catch (error) {
        console.error('测试执行错误:', error.message);
    } finally {
        await browser.close();
    }
    
    console.log('\n=== 测试完成 ===');
}

runTest().catch(console.error);
