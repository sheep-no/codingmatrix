const { test, expect } = require('@playwright/test');
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const BACKEND_URL = process.env.API_BASE || 'http://127.0.0.1:8000';
const STATE_FILE = path.resolve(__dirname, '../../test-results/extreme-test-state.json');

// 极限复杂度需求
const EXTREME_REQUIREMENT = `请生成一个完整的企业级在线博客内容管理系统（CMS），包含前后端分离架构。

## 一、项目概述
这是一个功能完整的个人/团队博客平台，支持多用户、多角色、内容管理、评论互动、数据统计等功能。

## 二、技术栈要求
### 前端
- 使用 Vue 3 + Vite + Pinia + Vue Router
- 使用 Element Plus 作为 UI 组件库
- 使用 Axios 进行 HTTP 请求
- 响应式设计，支持移动端

### 后端
- 使用 Python FastAPI 框架
- 使用 SQLAlchemy ORM + SQLite
- 使用 JWT 进行认证
- 使用 Pydantic 进行数据验证

## 三、核心功能模块

### 1. 用户认证与权限管理
- 用户注册（邮箱+密码，密码加密存储）
- 用户登录（JWT token，支持 refresh token）
- 用户资料管理（头像、昵称、简介）
- 角色权限系统（管理员、编辑、普通用户、访客）
- 密码重置功能

### 2. 文章管理系统
- 文章 CRUD（创建、读取、更新、删除）
- Markdown 编辑器支持（带实时预览）
- 文章分类管理（多级分类）
- 标签系统（多对多关系）
- 文章状态（草稿、已发布、已归档）
- 文章搜索（标题、内容、标签模糊搜索）
- 文章分页列表
- 热门文章排行（按浏览量、点赞数）

### 3. 评论与互动系统
- 文章评论（支持嵌套回复）
- 评论点赞/取消点赞
- 评论审核（管理员可删除不当评论）
- 用户点赞/收藏文章

### 4. 媒体管理
- 图片上传（支持拖拽上传）
- 图片缩略图生成
- 文件存储管理

### 5. 数据统计仪表盘
- 文章总数、用户总数、评论总数
- 每日/每周/每月访问量统计
- 热门文章 Top 10
- 用户活跃度统计

### 6. 系统设置
- 站点基本设置（标题、描述、Logo）
- SEO 设置（Meta 标签、sitemap）
- 评论设置（是否开启评论、审核模式）

## 四、数据库设计
需要设计以下数据表：
- users（用户表）
- roles（角色表）
- user_roles（用户角色关联表）
- categories（分类表）
- articles（文章表）
- article_tags（文章标签关联表）
- tags（标签表）
- comments（评论表）
- comment_likes（评论点赞表）
- article_likes（文章点赞表）
- site_settings（站点设置表）
- statistics（统计表）

## 五、API 接口设计
需要实现以下 RESTful API：
- POST /api/auth/register - 注册
- POST /api/auth/login - 登录
- POST /api/auth/refresh - 刷新 token
- GET /api/articles - 文章列表（分页、搜索、过滤）
- GET /api/articles/{id} - 文章详情
- POST /api/articles - 创建文章（需登录）
- PUT /api/articles/{id} - 更新文章（作者或管理员）
- DELETE /api/articles/{id} - 删除文章（作者或管理员）
- GET /api/categories - 分类列表
- GET /api/tags - 标签列表
- POST /api/articles/{id}/comments - 发表评论
- GET /api/articles/{id}/comments - 获取评论列表
- POST /api/comments/{id}/like - 点赞评论
- GET /api/stats - 统计数据
- GET /api/settings - 站点设置

## 六、前端页面
需要实现以下页面：
- 首页（文章列表、侧边栏、分页）
- 文章详情页（Markdown 渲染、评论区、相关推荐）
- 分类/标签筛选页
- 搜索结果页
- 用户登录/注册页
- 用户个人中心
- 后台管理面板（仪表盘、文章管理、评论管理、用户管理、系统设置）

## 七、代码质量要求
- 前后端代码分离清晰
- 后端有完整的错误处理和中间件
- 前端有路由守卫（登录验证）
- 包含 requirements.txt 和 package.json
- 包含 README.md 说明文档
- 包含 .env.example 环境变量示例

请生成完整可运行的项目代码，所有文件必须完整，不要省略任何部分。`;

// 通过 Node.js HTTP 登录获取 token（使用明文模式）
async function loginViaHttp() {
  return new Promise((resolve, reject) => {
    // 获取 CSRF Token
    http.get(`${BACKEND_URL}/api/v1/csrf-token`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const csrfData = JSON.parse(data);
        const csrfToken = csrfData.csrf_token;

        // 明文登录
        const loginData = JSON.stringify({
          email: TEST_EMAIL,
          password: TEST_PASSWORD
        });

        const req = http.request({
          hostname: '127.0.0.1',
          port: 8080,
          path: '/api/v1/login',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
            'Cookie': `csrf_token=${csrfToken}`
          }
        }, (res2) => {
          let data2 = '';
          res2.on('data', chunk => data2 += chunk);
          res2.on('end', () => {
            if (res2.statusCode === 200) {
              const loginResult = JSON.parse(data2);
              resolve({ success: true, token: loginResult.access_token, username: loginResult.username });
            } else {
              resolve({ success: false, error: data2 });
            }
          });
        });
        req.on('error', reject);
        req.write(loginData);
        req.end();
      });
    });
  });
}

// 加载状态
function loadState() {
  try {
    console.log(`\n[状态恢复] 尝试加载: ${STATE_FILE}`);
    console.log(`[状态恢复] 文件存在: ${fs.existsSync(STATE_FILE)}`);
    if (fs.existsSync(STATE_FILE)) {
      const state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
      console.log(`\n[状态恢复] 发现上次保存的状态:`);
      console.log(`  Session ID: ${state.session_id || '无'}`);
      console.log(`  Output Dir: ${state.output_dir || '无'}`);
      console.log(`  已生成文件: ${state.generated_files?.length || 0} 个`);
      console.log(`  增量模式: ${state.incremental || false}`);
      return state;
    }
  } catch (e) {
    console.log(`[状态恢复] 加载失败: ${e.message}`);
    console.log(`[状态恢复] 错误堆栈:`, e.stack);
  }
  return null;
}

// 保存状态
function saveState(state) {
  try {
    fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf-8');
    console.log(`\n[状态保存] 已保存进度状态`);
  } catch (e) {
    console.log(`[状态保存] 保存失败: ${e.message}`);
  }
}

test.describe('Agent 能力极限测试 - 全栈复杂项目生成（支持断点续传）', () => {
  test.describe.configure({ project: 'chromium' });

  test('生成复杂全栈项目（在线博客+管理系统）', async ({ page }) => {
    test.setTimeout(900000);

    const timeline = [];
    const sseEvents = [];
    let startTime;

    // 加载上次状态
    const previousState = loadState();

    // ========== 步骤 1: 登录（通过 Node.js HTTP） ==========
    console.log('\n=== 步骤 1: 登录 ===');
    startTime = Date.now();

    const loginResult = await loginViaHttp();
    console.log('登录结果:', loginResult);
    expect(loginResult.success).toBe(true);

    // 在浏览器中设置 token
    await page.goto(BASE_URL);
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate((token) => {
      localStorage.setItem('access_token', token);
    }, loginResult.token);

    timeline.push({ time: Date.now() - startTime, type: 'login_complete' });

    // ========== 步骤 2: 准备生成参数 ==========
    console.log('\n=== 步骤 2: 准备生成参数 ===');

    let sessionId = previousState?.session_id || `extreme_test_${Date.now()}`;
    let outputDir = previousState?.output_dir || null;
    let isIncremental = previousState?.incremental || false;

    console.log(`Session ID: ${sessionId}`);
    console.log(`Output Dir: ${outputDir || '（首次生成）'}`);
    console.log(`增量模式: ${isIncremental ? '是（继续上次）' : '否（全新生成）'}`);

    // ========== 步骤 3: 调用 SSE API ==========
    console.log('\n=== 步骤 3: 开始生成（SSE 流式）===');

    // 添加浏览器控制台事件监听，实时显示进度
    page.on('console', msg => {
      const text = msg.text();
      if (text.startsWith('[SSE]')) {
        console.log(text);
      }
    });

    const sseResult = await page.evaluate(async ({ req, sessionId, outputDir, incremental }) => {
      const token = localStorage.getItem('access_token');
      const events = [];

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1200000); // 20 分钟超时

      try {
        const requestBody = {
          requirement: req,
          enable_review: true,
          enable_validation: true,
          enable_error_recovery: true,
          enable_memory: true,
          incremental: incremental,
          require_approval: false,
          session_id: sessionId
        };

        if (outputDir) {
          requestBody.output_dir = outputDir;
        }

        console.log('[SSE] 发送请求到 /api/v1/agent/orchestrate/stream');

        const resp = await fetch('/api/v1/agent/orchestrate/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(requestBody),
          signal: controller.signal
        });

        if (!resp.ok) {
          clearTimeout(timeoutId);
          const errText = await resp.text().catch(() => '');
          console.log(`[SSE] 请求失败: ${resp.status} ${errText}`);
          let errData = {};
          try { errData = JSON.parse(errText); } catch(e) {}
          return {
            success: false,
            error: errData.detail?.message || errData.detail || errData.message || resp.statusText,
            events: []
          };
        }

        console.log('[SSE] 连接成功，开始接收流式数据...');

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lastLogTime = Date.now();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.substring(6));
                events.push({
                  type: data.type,
                  data: data.data || {},
                  timestamp: Date.now()
                });

                // 每 3 秒打印一次进度到 Node.js 终端
                if (Date.now() - lastLogTime > 3000) {
                  if (data.type === 'progress') {
                    const d = data.data || {};
                    const detail = d.step || '';
                    const pct = d.percentage ? `${d.percentage.toFixed(1)}%` : '';
                    const file = d.file_path || '';
                    console.log(`[SSE] ${detail} ${pct} ${file}`.trim());
                    lastLogTime = Date.now();
                  }
                }

                if (data.type === 'done' || data.type === 'error') {
                  clearTimeout(timeoutId);
                  return {
                    success: data.type === 'done',
                    events: events,
                    finalData: data.data,
                    sessionId: sessionId
                  };
                }
              } catch (e) {
                // 忽略解析错误
              }
            }
          }
        }

        clearTimeout(timeoutId);
        console.log('[SSE] 流结束');
        return { success: true, events: events, finalData: null, sessionId: sessionId };
      } catch (error) {
        clearTimeout(timeoutId);
        console.log(`[SSE] 异常: ${error.message}`);
        return { success: false, error: error.message, events: events, sessionId: sessionId };
      }
    }, {
      req: EXTREME_REQUIREMENT,
      sessionId: sessionId,
      outputDir: outputDir,
      incremental: isIncremental
    });

    timeline.push({ time: Date.now() - startTime, type: 'sse_complete' });

    // ========== 步骤 4: 保存状态 ==========
    const generatedFiles = sseResult.events
      .filter(e => e.type === 'progress' && e.data.step === 'file_generated')
      .map(e => e.data.file_path);

    const finalOutputDir = sseResult.finalData?.output_dir || outputDir || '';

    const newState = {
      session_id: sseResult.sessionId || sessionId,
      output_dir: finalOutputDir,
      generated_files: generatedFiles,
      incremental: true,
      last_run_time: new Date().toISOString(),
      total_events: sseResult.events.length,
      success: sseResult.success
    };

    saveState(newState);

    // ========== 步骤 5: 分析结果 ==========
    console.log('\n========== 极限测试结果 ==========');
    console.log(`SSE 调用成功: ${sseResult.success}`);
    console.log(`接收事件总数: ${sseResult.events.length}`);
    console.log(`Session ID: ${sseResult.sessionId || sessionId}`);
    console.log(`Output Dir: ${finalOutputDir}`);

    const eventTypes = {};
    for (const event of sseResult.events) {
      eventTypes[event.type] = (eventTypes[event.type] || 0) + 1;
    }

    console.log('\n事件类型分布:');
    for (const [type, count] of Object.entries(eventTypes)) {
      console.log(`  ${type}: ${count} 次`);
    }

    console.log('\n关键事件时间线（前 50 个）:');
    for (const event of sseResult.events.slice(0, 50)) {
      const data = event.data;
      let detail = '';
      if (event.type === 'progress') {
        if (data.step === 'generating_file') {
          detail = `生成文件: ${data.file_path || ''}`;
        } else if (data.step === 'file_generated') {
          detail = `✓ ${data.file_path || ''}`;
        } else if (data.step === 'analyzing_complexity') {
          detail = `复杂度: ${data.complexity || ''}, 文件: ${data.estimated_files || ''}`;
        } else {
          detail = `${data.step} (${data.current}/${data.total})`;
        }
      } else if (event.type === 'done') {
        detail = `完成! 文件数: ${data.total_files_created || 0}`;
      } else if (event.type === 'error') {
        detail = `错误: ${data.error || ''}`;
      }
      console.log(`  [${event.type}] ${detail}`);
    }

    console.log('\n========== 生成的文件列表 ==========');
    console.log(`共生成 ${generatedFiles.length} 个文件:`);
    generatedFiles.forEach((f, i) => console.log(`  ${i + 1}. ${f}`));

    if (sseResult.success && sseResult.finalData) {
      console.log('\n========== 最终结果 ==========');
      console.log(`输出目录: ${sseResult.finalData.output_dir || 'N/A'}`);
      console.log(`总文件数: ${sseResult.finalData.total_files_created || 0}`);
      console.log(`验证状态: ${sseResult.finalData.validation?.is_valid ? '通过' : '未通过'}`);
    }

    expect(sseResult.events.length).toBeGreaterThan(0);
    expect(sseResult.events.some(e => e.type === 'progress')).toBe(true);

    if (sseResult.success) {
      expect(sseResult.finalData.total_files_created).toBeGreaterThan(0);
    }

    console.log(`\n总耗时: ${Date.now() - startTime}ms (${((Date.now() - startTime) / 60000).toFixed(1)}分钟)`);
  });
});
