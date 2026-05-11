/**
 * AI Cloud 专项测试
 * 
 * 针对新增的 AI Cloud 功能进行全面测试：
 * 1. 模型列表
 * 2. 聊天（普通 + 流式）
 * 3. 代码执行
 * 4. 知识库
 * 5. 权限控制
 */

const { chromium } = require('playwright');
const fs = require('fs');

const CONFIG = {
  API_BASE: 'http://localhost:8080',
  TEST_USERS: {
    superadmin: { email: 'mr_yang@example.com', password: '12345678' },
    admin: { email: 'admin_test@example.com', password: '12345678' },
    normal: { email: 'normal_user@example.com', password: '12345678' }
  }
};

async function login(page, user) {
  const csrfRes = await page.request.get(`${CONFIG.API_BASE}/api/v1/csrf-token`);
  const csrfToken = (await csrfRes.json()).csrf_token;
  
  const loginRes = await page.request.post(`${CONFIG.API_BASE}/api/v1/login`, {
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    data: { email: user.email, password: user.password }
  });
  
  if (loginRes.status() === 200) {
    return (await loginRes.json()).access_token;
  }
  return null;
}

function auth(token) {
  return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function test(name, fn) {
  try {
    await fn();
    console.log(`✅ ${name}`);
    return true;
  } catch (e) {
    console.log(`❌ ${name}: ${e.message}`);
    return false;
  }
}

async function runTests() {
  console.log('\n========== AI Cloud 专项测试 ==========\n');
  
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  const superadminToken = await login(page, CONFIG.TEST_USERS.superadmin);
  const adminToken = await login(page, CONFIG.TEST_USERS.admin);
  const normalToken = await login(page, CONFIG.TEST_USERS.normal);
  
  if (!superadminToken) {
    console.log('❌ 登录失败，无法继续测试');
    await browser.close();
    return;
  }
  
  const results = [];
  
  // 1. 模型列表
  results.push(await test('获取模型列表', async () => {
    const res = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/models`, {
      headers: auth(superadminToken)
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const data = await res.json();
    if (!data.models || data.models.length === 0) throw new Error('模型列表为空');
    console.log(`   找到 ${data.models.length} 个模型，默认: ${data.default_model}`);
  }));
  
  // 2. 聊天接口
  results.push(await test('发送聊天消息', async () => {
    const res = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/chat`, {
      headers: auth(superadminToken),
      data: { message: '你好', session_id: null }
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const data = await res.json();
    if (!data.message) throw new Error('无回复内容');
    console.log(`   回复长度: ${data.message.length} 字符`);
  }));
  
  // 3. 流式聊天
  results.push(await test('流式聊天', async () => {
    const res = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/chat/stream`, {
      headers: auth(superadminToken),
      data: { message: '说一句话', session_id: null }
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const text = await res.text();
    if (!text.includes('data:')) throw new Error('非 SSE 格式');
    console.log(`   收到 ${text.split('\n').filter(l => l.startsWith('data:')).length} 个数据块`);
  }));
  
  // 4. 代码执行 - Python
  results.push(await test('Python 代码执行', async () => {
    const res = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/execute`, {
      headers: auth(superadminToken),
      data: { code: 'print("Hello Python!")', language: 'python' }
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const data = await res.json();
    if (!data.success) throw new Error(`执行失败: ${data.error}`);
    console.log(`   输出: ${data.output.trim()}`);
  }));
  
  // 5. 代码执行 - JavaScript
  results.push(await test('JavaScript 代码执行', async () => {
    const res = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/execute`, {
      headers: auth(superadminToken),
      data: { code: 'console.log("Hello JS!");', language: 'javascript' }
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const data = await res.json();
    if (!data.success) throw new Error(`执行失败: ${data.error}`);
    console.log(`   输出: ${data.output.trim()}`);
  }));
  
  // 6. 知识库 - 上传文档
  let docId = null;
  results.push(await test('知识库上传', async () => {
    const content = Buffer.from('这是测试文档内容。用于测试知识库功能。');
    const res = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/upload`, {
      headers: { 'Authorization': `Bearer ${superadminToken}` },
      multipart: {
        file: { name: 'test.txt', mimeType: 'text/plain', buffer: content },
        collection: 'default',
        description: '测试文档'
      }
    });
    if (res.status() !== 200) {
      const err = await res.text();
      throw new Error(`HTTP ${res.status()}: ${err.substring(0, 100)}`);
    }
    const data = await res.json();
    docId = data.doc_id;
    console.log(`   文档 ID: ${docId}, 分块数: ${data.chunk_count}`);
  }));
  
  // 7. 知识库 - 文档列表
  results.push(await test('知识库文档列表', async () => {
    const res = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/docs`, {
      headers: auth(superadminToken)
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const docs = await res.json();
    console.log(`   共 ${docs.length} 个文档`);
  }));
  
  // 8. 知识库 - 检索
  results.push(await test('知识库检索', async () => {
    const res = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/search`, {
      headers: auth(superadminToken),
      data: { query: '测试', collection: 'default', top_k: 5 }
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    const data = await res.json();
    console.log(`   找到 ${data.total_found} 个结果`);
  }));
  
  // 9. 知识库 - 删除
  if (docId) {
    results.push(await test('知识库删除', async () => {
      const res = await page.request.delete(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/docs/${docId}`, {
        headers: auth(superadminToken)
      });
      if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    }));
  }
  
  // 10. 权限控制 - 普通用户拒绝访问
  results.push(await test('普通用户拒绝访问 AI Cloud', async () => {
    const res = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/models`, {
      headers: auth(normalToken)
    });
    if (res.status() !== 403) throw new Error(`HTTP ${res.status()} (预期 403)`);
    console.log('   正确返回 403');
  }));
  
  // 11. 管理员可以访问
  results.push(await test('管理员可以访问 AI Cloud', async () => {
    const res = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/models`, {
      headers: auth(adminToken)
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
    console.log('   管理员正常访问');
  }));
  
  // 12. 获取历史记录
  results.push(await test('获取历史记录', async () => {
    const res = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/history?days=10`, {
      headers: auth(superadminToken)
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
  }));
  
  // 13. 审计日志
  results.push(await test('审计日志查询', async () => {
    const res = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/audit-logs`, {
      headers: auth(superadminToken)
    });
    if (res.status() !== 200) throw new Error(`HTTP ${res.status()}`);
  }));
  
  await browser.close();
  
  // 报告
  const passed = results.filter(r => r).length;
  const total = results.length;
  console.log(`\n========== 测试报告 ==========\n`);
  console.log(`通过: ${passed}/${total} (${(passed/total*100).toFixed(1)}%)`);
  
  if (passed < total) {
    console.log('\n提示: 部分测试失败，可能需要重启后端服务加载新路由');
  }
}

runTests().catch(console.error);
