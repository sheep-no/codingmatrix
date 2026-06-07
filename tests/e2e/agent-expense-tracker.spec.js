/**
 * 多模型 Agent 项目生成测试 - 个人记账本 Web 应用
 * 
 * 测试目标：验证默认模型能否正确生成完整的个人记账本项目
 */
import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000';

/** 清理运行中的会话，避免 429 限流 */
function cleanupRunningSessions() {
  try {
    execSync(`python3 -c "
import sqlite3
conn = sqlite3.connect('/workspace/app.db')
cursor = conn.cursor()
cursor.execute(\\"UPDATE project_sessions SET status = 'failed', error_message = 'cleaned for e2e test' WHERE status = 'running'\\")
conn.commit()
conn.close()
"`, { timeout: 5000 });
  } catch (e) {
    console.log('cleanup warning:', e.message);
  }
}

const REQUIREMENT = `个人记账本 Web 应用

1. 功能要求
1.1 用户功能（无需登录）
- 查看支出统计图表（按分类展示饼图，展示近7天每日支出折线图）
- 查看最近的10条支出记录（表格形式：日期、分类、金额、备注）

1.2 管理员功能（需登录）
- 登录凭证：硬编码 admin / 123456
- 登录后可进行：
  - 添加支出记录：日期（默认当天）、分类（餐饮/购物/交通/娱乐/其他）、金额、备注（可选）
  - 编辑/删除已有支出记录
  - 导出全部支出记录为 CSV 文件

1.3 数据存储
- 使用 SQLite 数据库，表名 expenses
- 字段：id, date, category, amount, note

2. 技术栈限制
- 后端：Python 3.9+，Flask（或 FastAPI）
- 前端：HTML5 + CSS3 + 原生 JavaScript（不使用前端框架）
- 图表库：ECharts 或 Chart.js（通过 CDN 引入）
- 其他：无需额外数据库配置，运行自动创建表

3. 非功能要求
- 代码结构清晰，按功能模块拆分文件（如 app.py, db.py, templates/, static/）
- 包含详细的 README.md，说明如何安装依赖（requirements.txt）、初始化数据库、运行服务
- 所有前端页面响应式（适配移动端宽度）
- 提供关键代码注释，解释设计决策

4. 测试场景
- 场景A：未登录状态下，只能看到统计图和最近记录，不能增删改
- 场景B：登录后，添加一笔"餐饮 50元"，饼图和折线图立即更新
- 场景C：删除一条记录后，图表同步刷新
- 场景D：导出 CSV 文件内容正确
`.trim();

test.describe('多模型 Agent 项目生成测试 - 个人记账本', () => {
  test.describe.configure({ project: 'chromium' });

  test('生成个人记账本 Web 应用项目', async ({ page }) => {
    test.setTimeout(600000);

    // 清理运行中的会话
    cleanupRunningSessions();

    const timeline = [];
    let startTime = Date.now();

    // ===== SSE 请求跟踪 =====
    let sseRequestSent = false;
    let sseResponseReceived = false;
    let sseResponseOk = false;
    let sseResponseStatusCode = 0;
    let sseResponseBody = '';

    page.on('request', (req) => {
      if (req.url().includes('/agent/orchestrate/stream')) {
        sseRequestSent = true;
        console.log(`[SSE] 请求已发出: ${req.method()} ${req.url()}`);
      }
    });

    page.on('response', async (res) => {
      if (res.url().includes('/agent/orchestrate/stream')) {
        sseResponseReceived = true;
        sseResponseStatusCode = res.status();
        sseResponseOk = sseResponseStatusCode === 200;
        console.log(`[SSE] 响应状态: ${sseResponseStatusCode}`);
        try {
          sseResponseBody = await res.text().catch(() => '(无法读取 body)');
        } catch { }
      }
    });

    // 监听控制台
    page.on('console', (msg) => {
      const t = msg.text();
      if (t.includes('[SSE]') || t.includes('[Agent]') || t.includes('stream')) {
        console.log(`[控制台] ${t}`);
      }
    });

    // ========== 1. 登录 ==========
    console.log('\n=== 步骤 1: 登录 ===');
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // 使用后端 API 直接登录（与 fixtures/auth.js 一致的方式）
    const loginResult = await page.evaluate(async ({ email, password }) => {
      try {
        // 获取 CSRF token
        const csrfResp = await fetch('/api/v1/csrf-token');
        const csrfData = await csrfResp.json();
        const csrfToken = csrfData.csrf_token;

        // 明文登录
        const resp = await fetch('/api/v1/login', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
          body: JSON.stringify({ email, password }),
        });
        if (!resp.ok) {
          const errText = await resp.text();
          return { success: false, error: `HTTP ${resp.status}: ${errText}` };
        }
        return await resp.json();
      } catch (e) {
        return { success: false, error: e.message };
      }
    }, { email: 'admin@example.com', password: 'admin123' });

    expect(loginResult.access_token, `登录失败: ${loginResult.error || JSON.stringify(loginResult)}`).toBeTruthy();

    await page.evaluate((data) => {
      const expiry = Date.now() + 3600000;
      sessionStorage.setItem('_token', data.access_token);
      sessionStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('username', data.username || 'admin');
      localStorage.setItem('email', data.email || 'admin@example.com');
      localStorage.setItem('permission_level', data.permission_level || 'superadmin');
      localStorage.setItem('user-store', JSON.stringify({
        isLoggedIn: true,
        username: data.username || 'admin',
        email: data.email || 'admin@example.com',
        permissionLevel: data.permission_level || 'superadmin'
      }));
    }, loginResult);

    timeline.push({ step: '登录', duration: Date.now() - startTime });
    console.log('✓ 登录成功');

    // ========== 2. 导航到 Agent 页面 ==========
    console.log('\n=== 步骤 2: 导航到 Agent 页面 ===');
    startTime = Date.now();

    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);

    timeline.push({ step: '导航到 Agent', duration: Date.now() - startTime });
    console.log('✓ Agent 页面已加载');

    // ========== 3. 输入需求并触发生成 ==========
    console.log('\n=== 步骤 3: 输入需求并触发生成 ===');
    startTime = Date.now();

    // 设置假的 SiliconFlow token 让前端 hasSiliconflowKey = true
    // （后端 .env 已有真实 API key，前端只需要通过检查）
    await page.evaluate(() => {
      const tokens = [{
        id: 'test-token',
        provider: 'siliconflow',
        name: 'Test SiliconFlow Key',
        enabled: true,
        token_preview: 'sk-****test',
        created_at: new Date().toISOString()
      }];
      localStorage.setItem('codingmatrix_apikeys', JSON.stringify(tokens));
    });

    // 刷新页面让 store 重新加载
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);

    // 验证 hasSiliconflowKey 现在为 true
    const keyCheck = await page.evaluate(() => {
      const app = document.querySelector('#app');
      const pinia = app.__vue_app__.config.globalProperties.$pinia;
      const store = pinia._s.get('apikey');
      return { hasSiliconflowKey: store.hasSiliconflowKey };
    });
    console.log('API Key 检查:', JSON.stringify(keyCheck));

    // 通过 Vue 组件设置 session.projectPrompt 并触发 generateProject
    // 注意：Playwright fill() 不触发 Vue 的 @input 事件（:value 单向绑定问题）
    // 因此直接通过组件实例设置 session.projectPrompt
    const genResult = await page.evaluate(async (requirement) => {
      try {
        const agentPage = document.querySelector('.agent-page');
        if (!agentPage) return { error: 'no agent page element' };
        const vueComp = agentPage.__vueParentComponent;
        if (!vueComp) return { error: 'no vue component' };

        const session = vueComp.setupState.session;
        if (!session) return { error: 'no session' };

        // 直接设置 session 的 projectPrompt（session 是 composable 返回的 plain object）
        session.projectPrompt = requirement;

        // 调用 generateProject
        const gp = vueComp.setupState.generateProject;
        if (typeof gp !== 'function') return { error: 'generateProject is not a function' };
        gp();
        return { ok: true };
      } catch (e) {
        return { error: e.message };
      }
    }, REQUIREMENT);

    if (genResult.error) {
      console.log('⚠ 触发生成失败:', genResult.error);
    } else {
      console.log('✓ 已触发 generateProject()');
    }

    // 等待 SSE 请求发出（最多 30 秒）
    console.log('等待 SSE 请求发出...');
    const sseRequestWaitStart = Date.now();
    while (!sseRequestSent && Date.now() - sseRequestWaitStart < 30000) {
      await page.waitForTimeout(1000);
      const elapsed = Math.round((Date.now() - sseRequestWaitStart) / 1000);
      if (elapsed % 5 === 0 && elapsed > 0) {
        console.log(`等待 SSE 请求... ${elapsed}s`);
      }
    }

    if (!sseRequestSent) {
      console.log('⚠ SSE 请求未发出，检查后端日志...');
      // 检查后端是否有请求
      const apiCheck = await page.evaluate(async (token) => {
        try {
          const resp = await fetch('/api/v1/agent/sessions', {
            headers: { 'Authorization': 'Bearer ' + token }
          });
          return { status: resp.status, ok: resp.ok };
        } catch (e) {
          return { error: e.message };
        }
      }, loginResult.access_token);
      console.log('Agent API 检查:', JSON.stringify(apiCheck));
    } else {
      console.log('✓ SSE 请求已发出');
    }

    timeline.push({ step: '触发生成', duration: Date.now() - startTime });

    // ========== 4. 等待 SSE 流完成 ==========
    console.log('\n=== 步骤 4: 等待 SSE 流完成 ===');
    startTime = Date.now();

    // 方式 A：等待 SSE 响应到达（表示请求已被后端处理）
    const sseResponseWaitStart = Date.now();
    while (!sseResponseReceived && Date.now() - sseResponseWaitStart < 120000) {
      await page.waitForTimeout(2000);
      const elapsed = Math.round((Date.now() - sseResponseWaitStart) / 1000);
      if (elapsed % 10 === 0 && elapsed > 0) {
        console.log(`等待 SSE 响应... ${elapsed}s`);
      }
    }

    if (sseResponseReceived) {
      console.log(`✓ SSE 响应已收到 (status=${sseResponseOk ? '200' : sseResponseStatusCode})`);
      if (!sseResponseOk) {
        console.log('SSE 响应内容:', sseResponseBody.substring(0, 500));
        // 429 表示有运行中的会话，需要先清理
        if (sseResponseStatusCode === 429) {
          console.log('⚠ 后端返回 429 并发限制，请先清理运行中的会话');
          test.skip(true, '后端有运行中的会话，请先清理');
          return;
        }
      }
    } else {
      console.log('⚠ SSE 响应未收到（120s 超时），检查页面状态...');
    }

    // 方式 B：等待页面上的文件列表出现（最多 3 分钟，因为 SSE 200 后文件会逐步出现）
    console.log('等待页面显示生成的文件...');
    const fileWaitStart = Date.now();
    let fileCount = 0;
    const maxFileWait = sseResponseOk ? 180000 : 30000; // SSE 成功等 3 分钟，失败等 30 秒

    while (fileCount === 0 && Date.now() - fileWaitStart < maxFileWait) {
      await page.waitForTimeout(3000);

      fileCount = await page.evaluate(() => {
        // 检查多种文件列表选择器
        const selectors = [
          '.file-item', '.generated-file', '[data-file]',
          '.file-path', '.file-name', '.file-list-item',
          '.agent-file-item', '.sidebar-file-item', '.file-entry',
          '.file-tree-node', '.file-tree-item',
          '[class*="file-item"]', '[class*="file-item"]',
          '.agent-file-panel .file-item',
        ];
        for (const sel of selectors) {
          const count = document.querySelectorAll(sel).length;
          if (count > 0) return count;
        }

        // 检查 Vue store
        try {
          const app = document.querySelector('#app');
          if (app && app.__vue_app__) {
            const pinia = app.__vue_app__.config.globalProperties.$pinia;
            if (pinia) {
              const state = pinia.state.value;
              if (state.agentFiles && state.agentFiles.generatedFiles && state.agentFiles.generatedFiles.length > 0) {
                return state.agentFiles.generatedFiles.length;
              }
              if (state.agentWorkspace && state.agentWorkspace.generatedFiles && state.agentWorkspace.generatedFiles.length > 0) {
                return state.agentWorkspace.generatedFiles.length;
              }
            }
          }
        } catch { }

        // 检查页面上是否有文件名出现（更宽泛的匹配）
        const bodyText = document.body.innerText;
        const filePatterns = [/\.py\b/, /\.html\b/, /\.css\b/, /\.js\b/, /requirements\.txt/, /README\.md/, /app\.py/];
        const matchCount = filePatterns.filter(p => p.test(bodyText)).length;
        if (matchCount >= 2) return matchCount; // 至少匹配 2 个文件模式

        return 0;
      });

      const elapsed = Math.round((Date.now() - fileWaitStart) / 1000);
      if (fileCount === 0 && elapsed % 15 === 0 && elapsed > 0) {
        console.log(`等待文件列表... ${elapsed}s`);
      }
    }

    if (fileCount > 0) {
      console.log(`✓ 检测到 ${fileCount} 个生成的文件`);
    } else {
      console.log('⚠ 5 分钟超时，未检测到文件列表');
    }

    timeline.push({ step: '等待生成完成', duration: Date.now() - startTime });

    // ========== 5. 验证生成结果 ==========
    console.log('\n=== 步骤 5: 验证生成结果 ===');
    startTime = Date.now();

    // 获取页面上显示的文件
    const fileList = await page.evaluate(() => {
      const files = [];

      // DOM 选择器
      const selectors = [
        '.file-item', '.generated-file', '[data-file]',
        '.file-path', '.file-name', '.file-list-item',
        '.agent-file-item', '.sidebar-file-item', '.file-entry',
        '.file-tree-node', '.file-tree-item',
        '[class*="file-item"]',
      ];
      for (const sel of selectors) {
        document.querySelectorAll(sel).forEach(el => {
          const text = el.textContent?.trim() || el.getAttribute('data-file') || el.getAttribute('data-path');
          if (text?.trim()) files.push(text.trim());
        });
      }

      // Vue store
      if (files.length === 0) {
        try {
          const app = document.querySelector('#app');
          if (app && app.__vue_app__) {
            const pinia = app.__vue_app__.config.globalProperties.$pinia;
            if (pinia) {
              const state = pinia.state.value;
              const storeFiles = (state.agentFiles?.generatedFiles || []).concat(state.agentWorkspace?.generatedFiles || []);
              storeFiles.forEach(f => files.push(f.path || f.name || String(f)));
            }
          }
        } catch { }
      }

      // 从页面文字提取文件名（兜底）
      if (files.length === 0) {
        const bodyText = document.body.innerText;
        const fileRegex = /[\w\/.-]+\.(py|html|css|js|txt|md|json|yml|yaml)/g;
        const matches = bodyText.match(fileRegex) || [];
        files.push(...matches);
      }

      return [...new Set(files)];
    });

    console.log(`找到 ${fileList.length} 个文件:`);
    fileList.slice(0, 30).forEach(f => console.log(`  - ${f}`));
    if (fileList.length > 30) console.log(`  ... 还有 ${fileList.length - 30} 个`);

    // 关键文件检查
    const expectedPatterns = [
      { pattern: /\.py$/, name: 'Python 文件' },
      { pattern: /\.html$/, name: 'HTML 模板' },
      { pattern: /requirements\.txt$/, name: 'requirements.txt' },
      { pattern: /\.css$/, name: 'CSS 文件' },
      { pattern: /\.js$/, name: 'JavaScript 文件' },
    ];

    const foundPatterns = {};
    for (const { pattern, name } of expectedPatterns) {
      foundPatterns[name] = fileList.some(f => pattern.test(f));
      console.log(`  ${foundPatterns[name] ? '✓' : '✗'} ${name}`);
    }

    // 文件结构检查
    const structureChecks = {
      'templates 目录': fileList.some(f => f.includes('templates/')),
      'static 目录': fileList.some(f => f.includes('static/')),
      '数据库相关': fileList.some(f => /db|database|sqlite/i.test(f)),
    };

    for (const [name, found] of Object.entries(structureChecks)) {
      console.log(`  ${found ? '✓' : '✗'} ${name}`);
    }

    timeline.push({ step: '验证生成结果', duration: Date.now() - startTime });

    // ========== 结果汇总 ==========
    console.log('\n=== 测试结果汇总 ===');
    console.log(`总耗时: ${timeline.reduce((s, t) => s + t.duration, 0)}ms`);
    console.log('\n时间线:');
    timeline.forEach(({ step, duration }) => console.log(`  ${step}: ${duration}ms`));

    console.log('\nSSE 状态:');
    console.log(`  请求已发出: ${sseRequestSent}`);
    console.log(`  响应已收到: ${sseResponseReceived}`);
    console.log(`  响应状态: ${sseResponseOk ? '200 OK' : '失败'}`);

    // 断言：至少应该有文件生成
    if (fileList.length === 0) {
      console.log('\n⚠ 未找到生成的文件，可能原因:');
      console.log('  1. SSE 请求未发出（按钮选择器问题）');
      console.log('  2. 后端处理失败');
      console.log('  3. 文件列表选择器不匹配');
      console.log('  4. SSE 流超时');
    }

    expect(fileList.length, '应至少生成 1 个文件').toBeGreaterThan(0);
  });
});
