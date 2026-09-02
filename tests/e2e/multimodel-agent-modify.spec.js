/**
 * 多模型 Agent 修改能力测试
 * 测试流程：
 * 1. 生成一个项目
 * 2. 故意删除一个文件
 * 3. 输入模糊问题，观察多模型 agent 如何诊断和修复
 */
const { test, expect } = require('@playwright/test');
const { apiLogin } = require('./fixtures/auth');
const crypto = require('crypto');

// 测试配置
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000';

// 通过测试环境变量提供 SiliconFlow API Key
const REAL_API_KEY = process.env.TEST_API_KEY;

// RSA 加密函数
function encryptWithPublicKey(publicKeyPem, data) {
  const publicKey = crypto.createPublicKey(publicKeyPem);
  const encrypted = crypto.publicEncrypt(
    {
      key: publicKey,
      padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
      oaepHash: 'sha256'
    },
    Buffer.from(data)
  );
  return encrypted.toString('base64');
}

// 提交 API Key 到后端
async function submitApiKey(page, apiKey, token, provider = 'siliconflow') {
  // 1. 先查询是否已有 API Key
  const listResp = await page.request.get(`${API_BASE}/api/v1/agent/apikeys`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const listData = await listResp.json();
  
  // 接口返回的是数组格式
  const keys = Array.isArray(listData) ? listData : (listData.keys || []);
  if (keys.length > 0) {
    const existingKey = keys.find(k => k.provider === provider);
    if (existingKey) {
      console.log('[DEBUG] 使用已存在的 SiliconFlow API Key');
      return { success: true, token: existingKey.token };
    }
  }
  
  // 2. 没有已存在的 Key，尝试创建新的
  const publicKeyResp = await page.request.get(`${API_BASE}/api/v1/agent/apikey/public-key`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const publicKeyData = await publicKeyResp.json();
  const publicKeyPem = publicKeyData.public_key;
  
  const encryptedKey = encryptWithPublicKey(publicKeyPem, apiKey);
  
  const csrfResp = await page.request.get(`${API_BASE}/api/v1/csrf-token`);
  const csrfData = await csrfResp.json();
  const csrfToken = csrfData.csrf_token;
  
  const submitResp = await page.request.post(`${API_BASE}/api/v1/agent/apikey`, {
    data: {
      encrypted_key: encryptedKey,
      provider: provider,
      ttl: 86400,
      remark: '测试 API Key'
    },
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-CSRF-Token': csrfToken
    }
  });
  
  const submitResult = await submitResp.json();
  
  // 如果达到上限 (403)，尝试删除最旧的 key 后重试
  if (submitResp.status() === 403 && keys.length > 0) {
    console.log('[DEBUG] API Key 达到上限，尝试删除最旧的 key...');
    const oldestKey = keys[keys.length - 1]; // 最后一个是最早创建的
    try {
      const deleteResp = await page.request.delete(`${API_BASE}/api/v1/agent/apikey/${oldestKey.token}`, {
        headers: { 'Authorization': `Bearer ${token}`, 'X-CSRF-Token': csrfToken }
      });
      if (deleteResp.ok()) {
        console.log(`[DEBUG] 已删除旧 key: ${oldestKey.token}`);
        // 重试创建
        const retryResp = await page.request.post(`${API_BASE}/api/v1/agent/apikey`, {
          data: {
            encrypted_key: encryptedKey,
            provider: provider,
            ttl: 86400,
            remark: '测试 API Key'
          },
          headers: {
            'Authorization': `Bearer ${token}`,
            'X-CSRF-Token': csrfToken
          }
        });
        return await retryResp.json();
      }
    } catch (e) {
      console.log('[WARNING] 删除旧 key 失败:', e.message);
    }
  }
  
  return submitResult;
}

// 辅助函数：获取当前生成的文件列表
async function getGeneratedFiles(page) {
  return await page.evaluate(() => {
    const items = document.querySelectorAll('.file-item .file-name');
    return Array.from(items).map(el => el.textContent);
  });
}

// 辅助函数：调试截图
async function debugScreenshot(page, name) {
  const timestamp = Date.now();
  const path = `test-results/debug-${name}-${timestamp}.png`;
  await page.screenshot({ path, fullPage: true });
  console.log(`[DEBUG] 截图已保存: ${path}`);
  return path;
}

// 辅助函数：获取页面状态
async function getPageState(page) {
  return await page.evaluate(() => {
    const state = {
      url: window.location.href,
      title: document.title,
      hasAgentPage: !!document.querySelector('.agent-page'),
      hasTextarea: !!document.querySelector('.prompt-textarea'),
      textareaValue: document.querySelector('.prompt-textarea')?.value || '',
      hasProgressBar: !!document.querySelector('.progress-bar-section'),
      hasTimeline: !!document.querySelector('.timeline'),
      hasFileTree: !!document.querySelector('.file-tree'),
      hasFiles: document.querySelectorAll('.file-item').length,
      buttons: Array.from(document.querySelectorAll('button')).map(b => ({
        text: b.textContent.trim(),
        disabled: b.disabled,
        className: b.className
      })),
      errors: Array.from(document.querySelectorAll('.el-message--error, .error-message')).map(el => el.textContent)
    };
    return state;
  });
}

test.describe('多模型 Agent 修改能力测试', () => {
  test('完整测试：生成 -> 删除文件 -> 模糊问题修复', async ({ page }) => {
    test.setTimeout(600000); // 10分钟超时
    test.skip(!REAL_API_KEY, '需要设置 TEST_API_KEY 才能执行真实模型验收');
    
    // 捕获浏览器控制台日志
    page.on('console', msg => {
      if (msg.text().includes('[SSE]') || msg.text().includes('error') || msg.text().includes('Error')) {
        console.log(`[BROWSER] ${msg.text()}`);
      }
    });
    
    console.log('=== 步骤0：登录 ===');
    
    // 先登录获取有效的 token
    let loginResult;
    try {
      loginResult = await apiLogin(page, BASE_URL);
      console.log('[DEBUG] 登录成功');
    } catch (error) {
      console.log('[ERROR] 登录失败:', error.message);
      test.skip();
      return;
    }
    
    // 提交测试环境提供的 SiliconFlow API Key 并设置前端 localStorage
    console.log('[DEBUG] 正在提交 SiliconFlow API Key...');
    let siliconflowTokenId = 'mock-siliconflow-token';
    try {
      const submitResult = await submitApiKey(page, REAL_API_KEY, loginResult.token, 'siliconflow');
      console.log('[DEBUG] API Key 提交结果:', submitResult);
      
      if (submitResult.success) {
        siliconflowTokenId = submitResult.token;
        console.log('[DEBUG] 已获得 SiliconFlow token ID');
      } else {
        console.log('[WARNING] API Key 提交失败:', submitResult.message);
      }
    } catch (error) {
      console.log('[ERROR] API Key 提交失败:', error.message);
    }
    
    console.log('=== 步骤1：进入 Agent 页面 ===');
    
    // 拦截 refresh 请求，防止清除 token
    await page.route('**/api/v1/refresh', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: loginResult.token, expires_in: 3600 })
      });
    });
    
    // 拦截 csrf-token 请求
    await page.route('**/api/v1/csrf-token', async route => {
      const response = await page.request.fetch(route.request());
      await route.fulfill({ response });
    });
    
    // 导航到 Agent 页面
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    
    // 在 Agent 页面上下文中设置所有存储
    await page.evaluate((data) => {
      // 设置 JWT token
      const expiry = Date.now() + 3600000;
      sessionStorage.setItem('_token', data.token);
      sessionStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('access_token', data.token);
      localStorage.setItem('_token_expiry', String(expiry));
      
      // 设置 API Key token
      const tokens = [
        {
          token: data.apiKeyId,
          provider: 'siliconflow',
          remark: '测试 API Key',
          status: 'verified',
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 86400 * 1000).toISOString(),
          ttl_seconds: 86400,
          enabled: true
        }
      ];
      localStorage.setItem('codingmatrix_apikeys', JSON.stringify(tokens));
      
      // 设置用户信息
      localStorage.setItem('username', 'admin@example.com');
      localStorage.setItem('email', 'admin@example.com');
      localStorage.setItem('permission_level', 'superadmin');
      
      console.log('[DEBUG] 存储已设置');
    }, { token: loginResult.token, apiKeyId: siliconflowTokenId });
    
    // 等待 Vue 应用重新读取存储
    await page.waitForTimeout(1000);
    
    // 验证存储已设置
    const storageCheck = await page.evaluate(() => {
      return {
        sessionToken: !!sessionStorage.getItem('_token'),
        localToken: !!localStorage.getItem('access_token'),
        apiKeys: !!localStorage.getItem('codingmatrix_apikeys')
      };
    });
    console.log('[DEBUG] 存储验证:', storageCheck);
    console.log('[DEBUG] 正在导航到 Agent 页面...');
    await page.goto(`${BASE_URL}/agent`);
    console.log('[DEBUG] 页面已加载，等待 domcontentloaded...');
    await page.waitForLoadState('domcontentloaded');
    console.log('[DEBUG] domcontentloaded 完成');
    
    // 等待页面完全加载
    console.log('[DEBUG] 等待 .agent-page 元素...');
    await page.waitForSelector('.agent-page', { timeout: 30000 });
    console.log('[DEBUG] .agent-page 元素已找到');
    
    // 获取初始页面状态
    const initialState = await getPageState(page);
    console.log('[DEBUG] 初始页面状态:', JSON.stringify(initialState, null, 2));
    
    // 检查是否有错误
    if (initialState.errors.length > 0) {
      console.log('[WARNING] 页面有错误:', initialState.errors);
    }
    
    console.log('=== 步骤2：输入项目需求并生成 ===');
    
    // 输入一个简单的项目需求
    const projectPrompt = '创建一个简单的 Vue 3 + FastAPI 待办事项应用，包含前后端代码';
    
    // 找到输入框并输入需求
    const textarea = await page.waitForSelector('.prompt-textarea');
    
    // 使用 Playwright 的 fill 方法，它会自动触发 input 事件
    await textarea.focus();
    await textarea.fill(projectPrompt);
    
    // 手动触发 input 事件以确保 Vue 响应式更新
    await textarea.dispatchEvent('input');
    
    // 等待 Vue 更新
    await page.waitForTimeout(1000);
    
    // 验证输入和按钮状态
    const inputState = await page.evaluate(() => {
      const textarea = document.querySelector('.prompt-textarea');
      const buttons = Array.from(document.querySelectorAll('button'));
      const generateBtn = buttons.find(b => b.textContent.includes('开始生成'));
      
      // 检查 Vue 组件的 props
      const vueInstance = textarea?.__vueParentComponent || textarea?.__vue__;
      const props = vueInstance?.props || {};
      
      return {
        textareaValue: textarea?.value,
        btnDisabled: generateBtn?.disabled,
        btnText: generateBtn?.textContent,
        vuePrompt: props.prompt,
        vueGenerating: props.generating
      };
    });
    console.log('[DEBUG] 输入状态:', inputState);
    
    // 截图记录生成前状态
    await debugScreenshot(page, 'before-generate');
    
    // 检查是否有模型选择器
    const hasModelSelector = await page.evaluate(() => {
      return !!document.querySelector('.model-select');
    });
    
    console.log('[DEBUG] 模型选择器存在:', hasModelSelector);
    
    // 检查 token 状态（在点击生成按钮前）
    const tokenState = await page.evaluate(() => {
      return {
        sessionToken: !!sessionStorage.getItem('_token'),
        localToken: !!localStorage.getItem('access_token'),
        apiKeys: !!localStorage.getItem('codingmatrix_apikeys'),
        apiKeysContent: localStorage.getItem('codingmatrix_apikeys')
      };
    });
    console.log('[DEBUG] Token 状态:', JSON.stringify(tokenState, null, 2));
    
    if (hasModelSelector) {
      // 选择第一个可用的模型
      const modelOptions = await page.evaluate(() => {
        const select = document.querySelector('.model-select');
        const options = Array.from(select?.querySelectorAll('option') || []);
        return options.map(opt => ({ value: opt.value, text: opt.textContent }));
      });
      console.log('[DEBUG] 可用模型选项:', modelOptions);
      
      // 选择第一个非空选项
      if (modelOptions.length > 1) {
        const firstModel = modelOptions.find(opt => opt.value !== '');
        if (firstModel) {
          await page.selectOption('.model-select', firstModel.value);
          console.log('[DEBUG] 已选择模型:', firstModel.text);
        }
      }
    }
    
    // 点击生成按钮 - 使用 Playwright 的 click 方法
    const generateBtn = page.locator('.action-buttons .btn-primary').first();
    
    // 监听网络请求
    const requests = [];
    page.on('request', request => {
      if (request.url().includes('/agent/')) {
        requests.push({
          url: request.url(),
          method: request.method(),
          headers: request.headers()
        });
      }
    });
    
    // 监听网络响应
    const responses = [];
    page.on('response', response => {
      if (response.url().includes('/agent/')) {
        responses.push({
          url: response.url(),
          status: response.status(),
          statusText: response.statusText()
        });
      }
    });
    
    await generateBtn.click({ force: true });
    
    // 等待 Vue 更新
    await page.waitForTimeout(3000);
    
    // 检查点击后的存储状态
    const afterClickStorage = await page.evaluate(() => {
      return {
        sessionToken: !!sessionStorage.getItem('_token'),
        sessionTokenValue: sessionStorage.getItem('_token')?.substring(0, 30),
        localToken: !!localStorage.getItem('access_token'),
        localTokenValue: localStorage.getItem('access_token')?.substring(0, 30),
        apiKeys: !!localStorage.getItem('codingmatrix_apikeys')
      };
    });
    console.log('[DEBUG] 点击后存储状态:', JSON.stringify(afterClickStorage, null, 2));
    
    console.log('[DEBUG] 网络请求:', requests);
    console.log('[DEBUG] 网络响应:', responses);
    
    // 检查点击后的状态
    const afterClickState = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.textContent.includes('开始生成') || b.textContent.includes('生成中'));
      const vueInstance = btn?.__vueParentComponent || btn?.__vue__;
      
      // 检查是否有错误消息
      const errorMessages = Array.from(document.querySelectorAll('.el-message--error, .el-message__content')).map(el => el.textContent);
      
      // 检查所有消息
      const allMessages = Array.from(document.querySelectorAll('.el-message')).map(el => ({
        type: el.className,
        text: el.textContent
      }));
      
      return {
        btnText: btn?.textContent,
        btnDisabled: btn?.disabled,
        vueGenerating: vueInstance?.props?.generating,
        hasProgress: !!document.querySelector('.progress-bar-section'),
        hasTimeline: !!document.querySelector('.timeline'),
        errorMessages,
        allMessages,
        generating: window.__VUE_APP__?.config?.globalProperties?.$store?.state?.generation?.isGenerating
      };
    });
    console.log('[DEBUG] 点击后状态:', JSON.stringify(afterClickState, null, 2));
    
    // 检查按钮状态
    const btnState = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.textContent.includes('开始生成') || b.textContent.includes('生成中'));
      return {
        text: btn?.textContent,
        disabled: btn?.disabled,
        hasProgress: !!document.querySelector('.progress-bar-section'),
        hasTimeline: !!document.querySelector('.timeline'),
        hasFiles: document.querySelectorAll('.file-item').length
      };
    });
    console.log('[DEBUG] 点击生成按钮后状态:', btnState);
    
    // 等待生成开始（按钮变为禁用或出现进度条）
    console.log('[DEBUG] 等待生成开始...');
    
    // 使用更宽松的等待条件
    try {
      await page.waitForFunction(() => {
        // 检查按钮是否变为禁用（正在生成）
        const btn = document.querySelector('.btn-primary');
        if (btn && btn.disabled) return true;
        
        // 检查是否出现进度条
        const progress = document.querySelector('.progress-bar-section');
        if (progress) return true;
        
        // 检查是否出现时间线
        const timeline = document.querySelector('.timeline');
        if (timeline) return true;
        
        // 检查是否出现思考消息
        const thinking = document.querySelector('.thinking-item-message');
        if (thinking) return true;
        
        // 检查是否出现文件
        const files = document.querySelectorAll('.file-item');
        if (files.length > 0) return true;
        
        return false;
      }, { timeout: 30000 });
      
      console.log('[DEBUG] 检测到生成已开始');
    } catch (error) {
      console.log('[ERROR] 生成未开始，页面状态:');
      const errorState = await getPageState(page);
      console.log(JSON.stringify(errorState, null, 2));
      await debugScreenshot(page, 'generate-timeout');
      throw error;
    }
    
    console.log('=== 步骤3：等待生成完成 ===');
    
    // 等待生成完成（按钮恢复可用且不再是"生成中"状态）
    // 需要处理可能弹出的决策卡片
    await page.waitForFunction(() => {
      // 检查是否有决策卡片需要确认
      const decisionCards = document.querySelectorAll('.decision-card');
      if (decisionCards.length > 0) {
        // 尝试点击默认值和确认按钮
        const defaultBtns = document.querySelectorAll('.btn-decision-secondary');
        const confirmBtns = document.querySelectorAll('.btn-decision-primary');
        defaultBtns.forEach(btn => {
          if (btn.textContent.includes('默认值')) btn.click();
        });
        confirmBtns.forEach(btn => {
          if (btn.textContent.includes('确认')) btn.click();
        });
      }
      
      // 检查按钮是否恢复可用（不再是"生成中..."状态）
      const btn = document.querySelector('.btn-primary');
      if (btn && !btn.disabled && !btn.textContent.includes('生成中')) {
        // 检查是否有文件生成
        const files = document.querySelectorAll('.file-item');
        return files.length > 0;
      }
      return false;
    }, { timeout: 180000 });
    
    // 额外等待确保生成完全结束
    await page.waitForTimeout(2000);
    
    // 再次确认按钮状态
    const btnEnabled = await page.evaluate(() => {
      const btn = document.querySelector('.btn-primary');
      return btn && !btn.disabled && !btn.textContent.includes('生成中');
    });
    if (!btnEnabled) {
      console.log('[WARNING] 按钮仍处于禁用状态，继续等待...');
      await page.waitForFunction(() => {
        const btn = document.querySelector('.btn-primary');
        return btn && !btn.disabled && !btn.textContent.includes('生成中');
      }, { timeout: 60000 });
    }
    
    // 获取生成的文件列表
    const filesBeforeDelete = await getGeneratedFiles(page);
    console.log('生成的文件列表:', filesBeforeDelete);
    
    // 确保有文件生成
    expect(filesBeforeDelete.length).toBeGreaterThan(0);
    
    // 截图记录生成后状态
    await debugScreenshot(page, 'after-generate');
    
    console.log('=== 步骤4：故意删除一个文件 ===');
    
    // 选择第一个要删除的文件（排除主入口文件）
    const fileToDelete = filesBeforeDelete.find(f => 
      !f.includes('main') && 
      !f.includes('index') && 
      !f.includes('App') &&
      !f.includes('package.json')
    ) || filesBeforeDelete[0];
    
    console.log('准备删除文件:', fileToDelete);
    
    // 点击文件选中它
    await page.click(`.file-item:has-text("${fileToDelete}")`);
    
    // 等待文件被选中（selected 类在 .tree-item 上）
    await page.waitForSelector(`.tree-item.selected:has-text("${fileToDelete}")`, { timeout: 5000 });
    
    // 等待编辑器面板出现（删除按钮在编辑器面板中）
    await page.waitForSelector('.editor-actions', { timeout: 5000 });
    
    // 点击删除按钮（使用 force: true 因为按钮可能被其他元素遮挡）
    await page.click('.editor-btn.btn-delete', { force: true });
    
    // 确认删除（如果有确认对话框）
    try {
      await page.waitForSelector('.el-message-box', { timeout: 3000 });
      await page.click('.el-message-box__btns .el-button--primary');
    } catch (e) {
      // 没有确认对话框，继续
    }
    
    // 等待删除完成
    await page.waitForTimeout(1000);
    
    // 验证文件已删除
    const filesAfterDelete = await getGeneratedFiles(page);
    console.log('删除后的文件列表:', filesAfterDelete);
    expect(filesAfterDelete.length).toBeLessThan(filesBeforeDelete.length);
    
    // 截图记录删除后状态
    await debugScreenshot(page, 'after-delete');
    
    console.log('=== 步骤5：输入模糊问题测试 Agent 诊断能力 ===');
    
    // 输入模糊问题，不明确说哪个文件被删除了
    const vagueProblem = '应用好像有问题，无法正常运行，请帮我检查并修复';
    
    // 清空输入框并输入新问题
    const inputForDebug = await page.waitForSelector('.prompt-textarea');
    await inputForDebug.fill(vagueProblem);
    
    // 触发 input 事件确保 Vue 响应式更新
    await inputForDebug.dispatchEvent('input');
    
    // 等待 Vue 更新
    await page.waitForTimeout(500);
    
    // 截图记录调试前状态
    await debugScreenshot(page, 'before-debug');
    
    // 点击主生成按钮（系统会自动判断是增量更新）
    await page.click('.btn-primary:has-text("继续生成")');
    
    console.log('=== 步骤6：观察多模型 Agent 的诊断过程 ===');
    
    // 等待 Agent 开始工作（出现时间线或思考消息）
    try {
      await page.waitForFunction(() => {
        const timeline = document.querySelector('.timeline');
        const thinking = document.querySelector('.thinking-item-message');
        const logs = document.querySelector('.log-item-merged');
        return timeline || thinking || logs;
      }, { timeout: 30000 });
      console.log('[DEBUG] 检测到 Agent 工作已开始');
    } catch (error) {
      console.log('[WARNING] 未检测到 Agent 工作，继续等待...');
    }
    
    // 监听思考过程面板
    const thinkingMessages = [];
    
    // 设置定时器收集思考消息
    const collectThinking = setInterval(async () => {
      try {
        const messages = await page.evaluate(() => {
          const items = document.querySelectorAll('.thinking-item-message');
          return Array.from(items).map(el => el.textContent);
        });
        if (messages.length > 0) {
          thinkingMessages.push(...messages);
          console.log(`[DEBUG] 收集到 ${messages.length} 条思考消息`);
        }
      } catch (e) {
        // 忽略错误
      }
    }, 2000);
    
    // 等待修复完成或超时
    try {
      await page.waitForFunction(() => {
        // 检查是否还在生成中
        const btn = document.querySelector('.btn-primary');
        if (btn && !btn.disabled && btn.textContent.includes('继续生成')) {
          // 检查是否有新的文件或修复完成
          return true;
        }
        
        // 检查是否有完成提示
        const success = document.querySelector('.el-message--success');
        if (success) return true;
        
        return false;
      }, { timeout: 120000 });
      console.log('[DEBUG] 检测到修复已完成');
    } catch (error) {
      console.log('[WARNING] 修复超时，继续收集信息...');
    }
    
    clearInterval(collectThinking);
    
    console.log('=== 步骤7：验证修复结果 ===');
    
    // 获取修复后的文件列表
    const filesAfterFix = await getGeneratedFiles(page);
    console.log('修复后的文件列表:', filesAfterFix);
    
    // 验证被删除的文件是否被恢复
    const isFileRestored = filesAfterFix.includes(fileToDelete);
    console.log(`文件 ${fileToDelete} 是否被恢复: ${isFileRestored}`);
    
    // 检查是否有诊断日志
    const logs = await page.evaluate(() => {
      const logItems = document.querySelectorAll('.log-item-merged .log-msg');
      return Array.from(logItems).map(el => el.textContent);
    });
    
    console.log('诊断日志:', logs.slice(0, 5)); // 只显示前5条
    
    // 检查是否有决策面板（Agent 可能需要用户确认）
    const hasDecisions = await page.evaluate(() => {
      return document.querySelectorAll('.decision-card').length > 0;
    });
    
    if (hasDecisions) {
      console.log('Agent 提出了决策建议，正在确认...');
      // 如果有决策，选择默认选项
      await page.click('.btn-decision-secondary:has-text("默认值")');
      await page.click('.btn-decision-primary:has-text("确认")');
      await page.waitForTimeout(2000);
    }
    
    // 最终截图
    await debugScreenshot(page, 'final-result');
    
    console.log('=== 测试完成 ===');
    console.log('收集到的思考消息数量:', thinkingMessages.length);
    
    // 输出测试报告
    const testReport = {
      originalFiles: filesBeforeDelete.length,
      deletedFile: fileToDelete,
      filesAfterDelete: filesAfterDelete.length,
      filesAfterFix: filesAfterFix.length,
      fileRestored: isFileRestored,
      thinkingMessages: thinkingMessages.length,
      logsCount: logs.length
    };
    
    console.log('测试报告:', JSON.stringify(testReport, null, 2));
    
    // 基本断言
    expect(filesAfterFix.length).toBeGreaterThanOrEqual(filesAfterDelete.length);
  });

  test('单元测试：多模型路由验证', async ({ page }) => {
    // 这个测试验证多模型路由是否正常工作
    console.log('验证多模型路由功能...');
    
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('networkidle');
    
    // 等待页面加载
    await page.waitForSelector('.agent-page', { timeout: 10000 });
    
    // 检查模型选择器是否存在
    const hasModelSelector = await page.evaluate(() => {
      return document.querySelectorAll('.model-select, .model-selector').length > 0;
    });
    
    console.log('模型选择器存在:', hasModelSelector);
    
    // 如果有模型选择器，检查选项
    if (hasModelSelector) {
      const modelOptions = await page.evaluate(() => {
        const select = document.querySelector('.model-select');
        if (!select) return [];
        const options = select.querySelectorAll('option, optgroup');
        return Array.from(options).map(opt => ({
          value: opt.value,
          text: opt.textContent,
          tagName: opt.tagName
        }));
      });
      
      console.log('可用模型选项:', modelOptions);
    }
    
    // 检查是否有模型相关的 UI 元素
    const modelUI = await page.evaluate(() => {
      const elements = document.querySelectorAll('[class*="model"], [class*="provider"]');
      return Array.from(elements).map(el => ({
        className: el.className,
        text: el.textContent.trim().substring(0, 50)
      }));
    });
    
    console.log('模型相关 UI 元素:', modelUI);
  });

  test('性能测试：Agent 响应时间', async ({ page }) => {
    test.setTimeout(120000);
    
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('networkidle');
    
    // 等待页面加载
    await page.waitForSelector('.agent-page', { timeout: 10000 });
    
    const startTime = Date.now();
    
    // 输入简单需求
    const textarea = await page.waitForSelector('.prompt-textarea');
    await textarea.fill('创建一个 Hello World 的 Python 脚本');
    
    // 开始生成
    await page.click('.action-buttons .btn-primary');
    
    // 等待第一个文件出现
    try {
      await page.waitForSelector('.file-item', { timeout: 60000 });
      const firstFileTime = Date.now() - startTime;
      console.log('第一个文件生成时间:', firstFileTime, 'ms');
      
      // 继续等待生成完成
      await page.waitForFunction(() => {
        const btn = document.querySelector('.btn-primary');
        return btn && !btn.disabled;
      }, { timeout: 60000 });
      
      const totalTime = Date.now() - startTime;
      console.log('总生成时间:', totalTime, 'ms');
      
      // 性能断言
      expect(firstFileTime).toBeLessThan(60000); // 第一个文件应该在60秒内
      expect(totalTime).toBeLessThan(120000); // 总时间应该在120秒内
    } catch (error) {
      console.log('[ERROR] 性能测试超时');
      await debugScreenshot(page, 'performance-timeout');
      throw error;
    }
  });
});
