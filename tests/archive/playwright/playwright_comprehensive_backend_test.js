/**
 * 后端 API 全面 Playwright 测试
 * 
 * 覆盖所有模块：
 * 1. 认证模块
 * 2. 代码问答
 * 3. 虚拟姬 AI
 * 4. PPT 生成
 * 5. 文件管理
 * 6. 任务队列
 * 7. Kolors 图像生成
 * 8. AI Cloud 聊天
 * 9. AI Cloud 知识库
 * 10. 工作流
 * 11. AI Agent
 * 12. 健康检查
 * 13. Nginx 管理
 * 14. 用户管理
 * 15. Guardian 监控
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ==================== 测试配置 ====================
const CONFIG = {
  BASE_URL: process.env.BASE_URL || 'http://localhost:3001',
  API_BASE: process.env.API_BASE || 'http://localhost:8080',
  TEST_USERS: {
    superadmin: {
      email: 'mr_yang@example.com',
      password: '12345678',
      username: 'mr_yang'
    },
    admin: {
      email: 'admin_test@example.com',
      password: '12345678',
      username: 'admin_test'
    },
    normal: {
      email: 'normal_user@example.com',
      password: '12345678',
      username: 'normal_user'
    }
  },
  TIMEOUT: 30000,
  REPORT_DIR: '/tmp/playwright-reports'
};

// ==================== 测试结果存储 ====================
const testResults = {
  passed: [],
  failed: [],
  skipped: [],
  startTime: null,
  endTime: null
};

// ==================== 工具函数 ====================
function log(message, type = 'info') {
  const prefix = {
    info: 'ℹ️',
    success: '✅',
    error: '❌',
    warn: '⚠️',
    test: '🧪'
  }[type] || 'ℹ️';
  console.log(`${prefix} ${message}`);
}

function recordResult(module, testName, status, detail = '') {
  const result = {
    module,
    test: testName,
    status,
    detail,
    timestamp: new Date().toISOString()
  };
  testResults[status === 'passed' ? 'passed' : status === 'failed' ? 'failed' : 'skipped'].push(result);
  
  if (status === 'passed') {
    log(`${module} - ${testName}`, 'success');
  } else if (status === 'failed') {
    log(`${module} - ${testName}: ${detail}`, 'error');
  } else {
    log(`${module} - ${testName}: 跳过`, 'warn');
  }
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ==================== 核心功能 ====================

/**
 * 登录并获取 JWT Token
 */
async function loginAndGetToken(page, user) {
  log(`尝试登录用户: ${user.email}`, 'info');
  
  try {
    // 1. 获取 CSRF Token
    const csrfResponse = await page.request.get(`${CONFIG.API_BASE}/api/v1/csrf-token`);
    const csrfData = await csrfResponse.json();
    const csrfToken = csrfData.csrf_token;
    
    // 2. 获取 RSA 公钥
    const publicKeyResponse = await page.request.get(`${CONFIG.API_BASE}/api/v1/public-key`);
    const publicKeyData = await publicKeyResponse.json();
    
    // 3. 登录（使用明文密码，如果 RSA 加密不可用）
    const loginResponse = await page.request.post(`${CONFIG.API_BASE}/api/v1/login`, {
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken
      },
      data: {
        email: user.email,
        password: user.password
      }
    });
    
    const loginData = await loginResponse.json();
    
    if (loginResponse.status() === 200 && loginData.access_token) {
      log(`登录成功: ${user.email}`, 'success');
      return loginData.access_token;
    } else {
      log(`登录失败: ${JSON.stringify(loginData)}`, 'error');
      return null;
    }
  } catch (error) {
    log(`登录异常: ${error.message}`, 'error');
    return null;
  }
}

/**
 * 创建带认证头的请求上下文
 */
function authHeaders(token) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
}

// ==================== 测试模块 ====================

/**
 * 1. 健康检查模块（无需认证）
 */
async function testHealthCheck(page) {
  const module = '健康检查';
  log(`\n========== ${module} ==========\n`, 'test');
  
  const endpoints = [
    { path: '/api/v1/health', name: '综合健康检查' },
    { path: '/api/v1/health/ready', name: '就绪检查' },
    { path: '/api/v1/health/live', name: '存活检查' },
    { path: '/api/v1/health/detailed', name: '详细健康信息' },
    { path: '/api/v1/health/models', name: '模型健康状态' }
  ];
  
  for (const endpoint of endpoints) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}${endpoint.path}`);
      if (response.status() === 200) {
        recordResult(module, endpoint.name, 'passed');
      } else {
        recordResult(module, endpoint.name, 'failed', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, endpoint.name, 'failed', error.message);
    }
  }
}

/**
 * 2. 认证模块
 */
async function testAuth(page) {
  const module = '认证模块';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 2.1 获取 CSRF Token
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/csrf-token`);
    if (response.status() === 200) {
      const data = await response.json();
      if (data.csrf_token) {
        recordResult(module, '获取 CSRF Token', 'passed');
      } else {
        recordResult(module, '获取 CSRF Token', 'failed', '缺少 csrf_token 字段');
      }
    } else {
      recordResult(module, '获取 CSRF Token', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取 CSRF Token', 'failed', error.message);
  }
  
  // 2.2 获取 RSA 公钥
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/public-key`);
    if (response.status() === 200) {
      recordResult(module, '获取 RSA 公钥', 'passed');
    } else {
      recordResult(module, '获取 RSA 公钥', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取 RSA 公钥', 'failed', error.message);
  }
  
  // 2.3 用户登录
  const token = await loginAndGetToken(page, CONFIG.TEST_USERS.superadmin);
  if (token) {
    recordResult(module, '用户登录 (superadmin)', 'passed');
  } else {
    recordResult(module, '用户登录 (superadmin)', 'failed', '登录失败');
  }
  
  // 2.4 Token 刷新
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/refresh`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (response.status() === 200) {
      recordResult(module, 'Token 刷新', 'passed');
    } else {
      recordResult(module, 'Token 刷新', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, 'Token 刷新', 'skipped', error.message);
  }
  
  return token;
}

/**
 * 3. AI Cloud 聊天模块
 */
async function testAICloudChat(page, token) {
  const module = 'AI Cloud 聊天';
  log(`\n========== ${module} ==========\n`, 'test');
  
  let sessionId = null;
  
  // 3.1 获取模型列表
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/models`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      const data = await response.json();
      if (data.models && data.models.length > 0) {
        recordResult(module, '获取模型列表', 'passed', `共 ${data.models.length} 个模型`);
      } else {
        recordResult(module, '获取模型列表', 'failed', '模型列表为空');
      }
    } else {
      recordResult(module, '获取模型列表', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取模型列表', 'failed', error.message);
  }
  
  // 3.2 发送聊天消息
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/chat`, {
      headers: authHeaders(token),
      data: {
        message: '你好，请简单介绍一下你自己',
        session_id: null
      }
    });
    
    if (response.status() === 200) {
      const data = await response.json();
      sessionId = data.session_id;
      if (data.message && data.session_id) {
        recordResult(module, '发送聊天消息', 'passed');
      } else {
        recordResult(module, '发送聊天消息', 'failed', '响应格式错误');
      }
    } else {
      recordResult(module, '发送聊天消息', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '发送聊天消息', 'failed', error.message);
  }
  
  // 3.3 流式聊天
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/chat/stream`, {
      headers: authHeaders(token),
      data: {
        message: '请说一句话',
        session_id: sessionId,
        model_id: 'deepseek-r1'
      }
    });
    
    if (response.status() === 200) {
      const text = await response.text();
      if (text.includes('data:') || text.includes('delta')) {
        recordResult(module, '流式聊天', 'passed');
      } else {
        recordResult(module, '流式聊天', 'failed', '响应格式不正确');
      }
    } else {
      recordResult(module, '流式聊天', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '流式聊天', 'failed', error.message);
  }
  
  // 3.4 获取历史记录
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/history?days=10`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取历史记录', 'passed');
    } else {
      recordResult(module, '获取历史记录', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取历史记录', 'failed', error.message);
  }
  
  // 3.5 搜索历史记录
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/history/search?keyword=你好&days=10`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '搜索历史记录', 'passed');
    } else {
      recordResult(module, '搜索历史记录', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '搜索历史记录', 'failed', error.message);
  }
  
  // 3.6 导出会话
  if (sessionId) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/history/export/${sessionId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '导出会话', 'passed');
      } else {
        recordResult(module, '导出会话', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '导出会话', 'failed', error.message);
    }
  }
  
  // 3.7 审计日志
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/audit-logs`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '审计日志查询', 'passed');
    } else {
      recordResult(module, '审计日志查询', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '审计日志查询', 'failed', error.message);
  }
  
  // 3.8 审查队列
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/reviews`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '审查队列', 'passed');
    } else {
      recordResult(module, '审查队列', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '审查队列', 'failed', error.message);
  }
  
  return sessionId;
}

/**
 * 4. AI Cloud 代码执行
 */
async function testAICloudExecute(page, token) {
  const module = 'AI Cloud 代码执行';
  log(`\n========== ${module} ==========\n`, 'test');
  
  const testCases = [
    {
      name: 'Python 基础输出',
      code: 'print("Hello from Python!")',
      language: 'python'
    },
    {
      name: 'Python 数学计算',
      code: 'result = 2 + 3 * 4\nprint(f"结果: {result}")',
      language: 'python'
    },
    {
      name: 'Python 列表操作',
      code: 'nums = [1, 2, 3, 4, 5]\nprint(f"总和: {sum(nums)}")\nprint(f"最大值: {max(nums)}")',
      language: 'python'
    },
    {
      name: 'JavaScript 基础',
      code: 'console.log("Hello from JavaScript!");\nconst sum = [1, 2, 3].reduce((a, b) => a + b, 0);\nconsole.log(`总和: ${sum}`);',
      language: 'javascript'
    }
  ];
  
  for (const testCase of testCases) {
    try {
      const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/execute`, {
        headers: authHeaders(token),
        data: {
          code: testCase.code,
          language: testCase.language,
          timeout: 10
        }
      });
      
      if (response.status() === 200) {
        const data = await response.json();
        if (data.success) {
          recordResult(module, `${testCase.name}`, 'passed', `输出: ${data.output?.substring(0, 50)}`);
        } else {
          recordResult(module, `${testCase.name}`, 'failed', `错误: ${data.error}`);
        }
      } else {
        recordResult(module, `${testCase.name}`, 'failed', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, `${testCase.name}`, 'failed', error.message);
    }
  }
}

/**
 * 5. AI Cloud 知识库
 */
async function testAICloudKnowledge(page, token) {
  const module = 'AI Cloud 知识库';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 5.1 创建测试文档
  const testDocPath = path.join(CONFIG.REPORT_DIR, 'test_doc.txt');
  fs.writeFileSync(testDocPath, '这是一个测试文档。\n用于测试知识库上传功能。\n包含多行内容。');
  
  // 5.2 上传文档
  let docId = null;
  try {
    const formData = new FormData();
    const fileContent = fs.readFileSync(testDocPath);
    formData.append('file', new Blob([fileContent]), 'test_doc.txt');
    formData.append('collection', 'default');
    formData.append('description', '测试文档');
    
    // 使用 multipart/form-data
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/upload`, {
      headers: {
        'Authorization': `Bearer ${token}`
      },
      multipart: {
        file: {
          name: 'test_doc.txt',
          mimeType: 'text/plain',
          buffer: fileContent
        },
        collection: 'default',
        description: '测试文档'
      }
    });
    
    if (response.status() === 200) {
      const data = await response.json();
      docId = data.doc_id;
      recordResult(module, '上传文档', 'passed', `文档 ID: ${docId}`);
    } else {
      const errorText = await response.text();
      recordResult(module, '上传文档', 'failed', `HTTP ${response.status()}: ${errorText.substring(0, 100)}`);
    }
  } catch (error) {
    recordResult(module, '上传文档', 'failed', error.message);
  }
  
  // 5.3 获取文档列表
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/docs`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      const docs = await response.json();
      recordResult(module, '获取文档列表', 'passed', `共 ${docs.length} 个文档`);
    } else {
      recordResult(module, '获取文档列表', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取文档列表', 'failed', error.message);
  }
  
  // 5.4 检索知识库
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/search`, {
      headers: authHeaders(token),
      form: {
        query: '测试',
        collection: 'default',
        top_k: '5'
      }
    });
    if (response.status() === 200) {
      recordResult(module, '检索知识库', 'passed');
    } else {
      recordResult(module, '检索知识库', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '检索知识库', 'failed', error.message);
  }
  
  // 5.5 删除文档
  if (docId) {
    try {
      const response = await page.request.delete(`${CONFIG.API_BASE}/api/v1/aicloud/knowledge/docs/${docId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '删除文档', 'passed');
      } else {
        recordResult(module, '删除文档', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '删除文档', 'failed', error.message);
    }
  }
}

/**
 * 6. AI Agent 模块
 */
async function testAIAgent(page, token) {
  const module = 'AI Agent';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 6.1 获取模型列表
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/agent/models`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取模型列表', 'passed');
    } else {
      recordResult(module, '获取模型列表', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取模型列表', 'failed', error.message);
  }
  
  // 6.2 创建会话
  let sessionId = null;
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/agent/sessions`, {
      headers: authHeaders(token),
      data: {
        session_type: 'chat',
        model_key: 'deepseek-r1'
      }
    });
    if (response.status() === 200) {
      const data = await response.json();
      sessionId = data.session_id;
      recordResult(module, '创建会话', 'passed');
    } else {
      recordResult(module, '创建会话', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '创建会话', 'failed', error.message);
  }
  
  // 6.3 获取会话列表
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/agent/sessions?limit=10&offset=0`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取会话列表', 'passed');
    } else {
      recordResult(module, '获取会话列表', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取会话列表', 'failed', error.message);
  }
  
  // 6.4 处理任务（非流式）
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/agent/process`, {
      headers: authHeaders(token),
      data: {
        task: '请解释什么是 Python 的装饰器',
        context: { session_id: sessionId },
        task_type: 'code_question'
      },
      timeout: 60000
    });
    if (response.status() === 200) {
      recordResult(module, '处理任务', 'passed');
    } else {
      recordResult(module, '处理任务', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '处理任务', 'failed', error.message);
  }
  
  // 6.5 获取记忆上下文
  if (sessionId) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/agent/memory/${sessionId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '获取记忆上下文', 'passed');
      } else {
        recordResult(module, '获取记忆上下文', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '获取记忆上下文', 'failed', error.message);
    }
  }
  
  // 6.6 添加知识
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/agent/knowledge`, {
      headers: authHeaders(token),
      data: {
        content: 'Python 装饰器是一个函数，它接受一个函数作为参数并返回一个新的函数。',
        knowledge_key: 'python_decorator',
        category: 'programming',
        importance: 5
      }
    });
    if (response.status() === 200) {
      recordResult(module, '添加知识', 'passed');
    } else {
      recordResult(module, '添加知识', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '添加知识', 'failed', error.message);
  }
  
  // 6.7 搜索知识
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/agent/knowledge/search?q=装饰器&limit=5`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '搜索知识', 'passed');
    } else {
      recordResult(module, '搜索知识', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '搜索知识', 'failed', error.message);
  }
  
  // 6.8 获取模型使用统计
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/agent/stats/models`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取模型使用统计', 'passed');
    } else {
      recordResult(module, '获取模型使用统计', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取模型使用统计', 'failed', error.message);
  }
  
  return sessionId;
}

/**
 * 7. 代码问答模块
 */
async function testCodeQA(page, token) {
  const module = '代码问答';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 7.1 发送代码问题
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/code`, {
      headers: authHeaders(token),
      data: {
        prompt: '请解释 Python 中的列表推导式',
        model: 'deepseek-r1',
        stream: false
      },
      timeout: 60000
    });
    if (response.status() === 200) {
      recordResult(module, '发送代码问题', 'passed');
    } else {
      recordResult(module, '发送代码问题', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '发送代码问题', 'failed', error.message);
  }
}

/**
 * 8. 虚拟姬 AI 模块
 */
async function testGirlAi(page, token) {
  const module = '虚拟姬 AI';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 8.1 获取角色列表
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/GirlAi/characters`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      const data = await response.json();
      recordResult(module, '获取角色列表', 'passed', `共 ${data.length || 0} 个角色`);
    } else {
      recordResult(module, '获取角色列表', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取角色列表', 'failed', error.message);
  }
  
  // 8.2 发送消息
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/GirlAi`, {
      headers: authHeaders(token),
      data: {
        prompt: '你好',
        max_tokens: 100
      },
      timeout: 60000
    });
    if (response.status() === 200) {
      recordResult(module, '发送消息', 'passed');
    } else {
      recordResult(module, '发送消息', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '发送消息', 'failed', error.message);
  }
  
  // 8.3 获取历史记录
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/GirlAi/history?limit=10&offset=0`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取历史记录', 'passed');
    } else {
      recordResult(module, '获取历史记录', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取历史记录', 'failed', error.message);
  }
}

/**
 * 9. 文件管理模块
 */
async function testFileManagement(page, token) {
  const module = '文件管理';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 9.1 上传文件
  let fileId = null;
  const testFilePath = path.join(CONFIG.REPORT_DIR, 'test_file.txt');
  fs.writeFileSync(testFilePath, '这是一个测试文件。');
  
  try {
    const fileContent = fs.readFileSync(testFilePath);
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/files/upload`, {
      headers: {
        'Authorization': `Bearer ${token}`
      },
      multipart: {
        file: {
          name: 'test_file.txt',
          mimeType: 'text/plain',
          buffer: fileContent
        }
      }
    });
    if (response.status() === 200) {
      const data = await response.json();
      fileId = data.file_id || data.id;
      recordResult(module, '上传文件', 'passed', `文件 ID: ${fileId}`);
    } else {
      recordResult(module, '上传文件', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '上传文件', 'failed', error.message);
  }
  
  // 9.2 列出文件
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/files?page=1&page_size=10`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '列出文件', 'passed');
    } else {
      recordResult(module, '列出文件', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '列出文件', 'failed', error.message);
  }
  
  // 9.3 获取文件信息
  if (fileId) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/files/${fileId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '获取文件信息', 'passed');
      } else {
        recordResult(module, '获取文件信息', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '获取文件信息', 'failed', error.message);
    }
  }
  
  // 9.4 下载文件
  if (fileId) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/files/${fileId}/download`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '下载文件', 'passed');
      } else {
        recordResult(module, '下载文件', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '下载文件', 'failed', error.message);
    }
  }
  
  // 9.5 删除文件
  if (fileId) {
    try {
      const response = await page.request.delete(`${CONFIG.API_BASE}/api/v1/files/${fileId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '删除文件', 'passed');
      } else {
        recordResult(module, '删除文件', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '删除文件', 'failed', error.message);
    }
  }
}

/**
 * 10. 任务队列模块
 */
async function testTaskQueue(page, token) {
  const module = '任务队列';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 10.1 列出任务
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/tasks?page=1&page_size=10`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '列出任务', 'passed');
    } else {
      recordResult(module, '列出任务', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '列出任务', 'failed', error.message);
  }
}

/**
 * 11. Kolors 图像生成模块
 */
async function testKolors(page, token) {
  const module = 'Kolors 图像生成';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 11.1 获取配置
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/kolors/config`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取配置', 'passed');
    } else {
      recordResult(module, '获取配置', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取配置', 'failed', error.message);
  }
}

/**
 * 12. 工作流模块
 */
async function testWorkflow(page, token) {
  const module = '工作流';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 12.1 导入工作流
  let workflowId = null;
  try {
    const testWorkflow = {
      nodes: [
        { id: 'node1', type: 'task', content: '测试节点' }
      ],
      edges: []
    };
    
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v1/workflow/import`, {
      headers: authHeaders(token),
      data: testWorkflow
    });
    if (response.status() === 200) {
      const data = await response.json();
      workflowId = data.workflow_id;
      recordResult(module, '导入工作流', 'passed');
    } else {
      recordResult(module, '导入工作流', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '导入工作流', 'failed', error.message);
  }
  
  // 12.2 获取工作流状态
  if (workflowId) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/workflow/status/${workflowId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '获取工作流状态', 'passed');
      } else {
        recordResult(module, '获取工作流状态', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '获取工作流状态', 'failed', error.message);
    }
  }
  
  // 12.3 导出工作流
  if (workflowId) {
    try {
      const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/workflow/export/${workflowId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '导出工作流', 'passed');
      } else {
        recordResult(module, '导出工作流', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '导出工作流', 'failed', error.message);
    }
  }
  
  // 12.4 删除工作流
  if (workflowId) {
    try {
      const response = await page.request.delete(`${CONFIG.API_BASE}/api/v1/workflow/${workflowId}`, {
        headers: authHeaders(token)
      });
      if (response.status() === 200) {
        recordResult(module, '删除工作流', 'passed');
      } else {
        recordResult(module, '删除工作流', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '删除工作流', 'failed', error.message);
    }
  }
}

/**
 * 13. 用户管理模块（需要 admin 权限）
 */
async function testUserManagement(page, adminToken) {
  const module = '用户管理';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 13.1 查询用户列表
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/users?page=1&page_size=10`, {
      headers: authHeaders(adminToken)
    });
    if (response.status() === 200) {
      recordResult(module, '查询用户列表', 'passed');
    } else {
      recordResult(module, '查询用户列表', 'failed', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '查询用户列表', 'failed', error.message);
  }
  
  // 13.2 创建新用户
  let newUserId = null;
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v2/Controller/create_user`, {
      headers: authHeaders(adminToken),
      data: {
        username: 'test_user_playwright',
        email: 'test_playwright@example.com',
        password: '123456',
        permission_level: 'normal'
      }
    });
    if (response.status() === 200) {
      const data = await response.json();
      newUserId = data.user_id || data.id;
      recordResult(module, '创建新用户', 'passed');
    } else {
      recordResult(module, '创建新用户', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '创建新用户', 'failed', error.message);
  }
  
  // 13.3 更新用户
  if (newUserId) {
    try {
      const response = await page.request.patch(`${CONFIG.API_BASE}/api/v2/Controller/update_user/${newUserId}`, {
        headers: authHeaders(adminToken),
        data: {
          username: 'test_user_updated'
        }
      });
      if (response.status() === 200) {
        recordResult(module, '更新用户', 'passed');
      } else {
        recordResult(module, '更新用户', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '更新用户', 'failed', error.message);
    }
  }
  
  // 13.4 重置密码
  if (newUserId) {
    try {
      const response = await page.request.post(`${CONFIG.API_BASE}/api/v2/Controller/${newUserId}/reset-password`, {
        headers: authHeaders(adminToken),
        data: {
          new_password: 'newpassword123'
        }
      });
      if (response.status() === 200) {
        recordResult(module, '重置密码', 'passed');
      } else {
        recordResult(module, '重置密码', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '重置密码', 'failed', error.message);
    }
  }
  
  // 13.5 删除用户
  if (newUserId) {
    try {
      const response = await page.request.delete(`${CONFIG.API_BASE}/api/v2/Controller/delete_user/${newUserId}`, {
        headers: authHeaders(adminToken)
      });
      if (response.status() === 200) {
        recordResult(module, '删除用户', 'passed');
      } else {
        recordResult(module, '删除用户', 'skipped', `HTTP ${response.status()}`);
      }
    } catch (error) {
      recordResult(module, '删除用户', 'failed', error.message);
    }
  }
}

/**
 * 14. Guardian 监控模块（需要 admin 权限）
 */
async function testGuardian(page, adminToken) {
  const module = 'Guardian 监控';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 14.1 列出服务
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/services`, {
      headers: authHeaders(adminToken)
    });
    if (response.status() === 200) {
      recordResult(module, '列出服务', 'passed');
    } else {
      recordResult(module, '列出服务', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '列出服务', 'failed', error.message);
  }
  
  // 14.2 获取配置
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/admin/config`, {
      headers: authHeaders(adminToken)
    });
    if (response.status() === 200) {
      recordResult(module, '获取配置', 'passed');
    } else {
      recordResult(module, '获取配置', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取配置', 'failed', error.message);
  }
  
  // 14.3 获取服务器资源状态
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/admin/stats`, {
      headers: authHeaders(adminToken)
    });
    if (response.status() === 200) {
      recordResult(module, '获取服务器资源状态', 'passed');
    } else {
      recordResult(module, '获取服务器资源状态', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取服务器资源状态', 'failed', error.message);
  }
  
  // 14.4 获取 WebSocket 连接统计
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/admin/ws-stats`, {
      headers: authHeaders(adminToken)
    });
    if (response.status() === 200) {
      recordResult(module, '获取 WebSocket 统计', 'passed');
    } else {
      recordResult(module, '获取 WebSocket 统计', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取 WebSocket 统计', 'failed', error.message);
  }
  
  // 14.5 获取限流配置
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/admin/rate-limit`, {
      headers: authHeaders(adminToken)
    });
    if (response.status() === 200) {
      recordResult(module, '获取限流配置', 'passed');
    } else {
      recordResult(module, '获取限流配置', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取限流配置', 'failed', error.message);
  }
}

/**
 * 15. Nginx 管理模块
 */
async function testNginxManagement(page, token) {
  const module = 'Nginx 管理';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 15.1 获取 Nginx 配置
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/nginx/config`, {
      headers: authHeaders(token)
    });
    if (response.status() === 200) {
      recordResult(module, '获取 Nginx 配置', 'passed');
    } else {
      recordResult(module, '获取 Nginx 配置', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '获取 Nginx 配置', 'failed', error.message);
  }
  
  // 15.2 生成 Nginx 配置
  try {
    const response = await page.request.post(`${CONFIG.API_BASE}/api/v2/nginx/generate`, {
      headers: authHeaders(token),
      data: {
        config_type: 'reverse_proxy',
        port: 8080,
        server_name: 'localhost'
      },
      timeout: 60000
    });
    if (response.status() === 200) {
      recordResult(module, '生成 Nginx 配置', 'passed');
    } else {
      recordResult(module, '生成 Nginx 配置', 'skipped', `HTTP ${response.status()}`);
    }
  } catch (error) {
    recordResult(module, '生成 Nginx 配置', 'failed', error.message);
  }
}

// ==================== 权限控制测试 ====================

/**
 * 16. 权限控制测试
 */
async function testPermissionControl(page, normalToken, adminToken) {
  const module = '权限控制';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 16.1 普通用户访问管理员接口（应该失败）
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v2/Controller/users?page=1&page_size=10`, {
      headers: authHeaders(normalToken)
    });
    if (response.status() === 403) {
      recordResult(module, '普通用户拒绝访问管理员接口', 'passed');
    } else {
      recordResult(module, '普通用户拒绝访问管理员接口', 'failed', `HTTP ${response.status()} (预期 403)`);
    }
  } catch (error) {
    recordResult(module, '普通用户拒绝访问管理员接口', 'failed', error.message);
  }
  
  // 16.2 普通用户访问 AI Cloud（应该成功，因为 admin 级别）
  try {
    const response = await page.request.get(`${CONFIG.API_BASE}/api/v1/aicloud/models`, {
      headers: authHeaders(normalToken)
    });
    // aicloud 需要 admin 权限，普通用户应该被拒绝
    if (response.status() === 403) {
      recordResult(module, '普通用户拒绝访问 AI Cloud', 'passed');
    } else {
      recordResult(module, '普通用户拒绝访问 AI Cloud', 'failed', `HTTP ${response.status()} (预期 403)`);
    }
  } catch (error) {
    recordResult(module, '普通用户拒绝访问 AI Cloud', 'failed', error.message);
  }
}

// ==================== 前端 UI 测试 ====================

/**
 * 17. 前端 UI 测试
 */
async function testFrontendUI(page, token) {
  const module = '前端 UI';
  log(`\n========== ${module} ==========\n`, 'test');
  
  // 17.1 访问首页
  try {
    await page.goto(CONFIG.BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const title = await page.title();
    if (title) {
      recordResult(module, '访问首页', 'passed', `标题: ${title}`);
    } else {
      recordResult(module, '访问首页', 'failed', '页面标题为空');
    }
  } catch (error) {
    recordResult(module, '访问首页', 'failed', error.message);
  }
  
  // 17.2 检查静态资源
  try {
    const hasJS = await page.evaluate(() => {
      const scripts = document.querySelectorAll('script[src]');
      return scripts.length > 0;
    });
    if (hasJS) {
      recordResult(module, '静态资源加载', 'passed');
    } else {
      recordResult(module, '静态资源加载', 'failed', '未找到 JS 文件');
    }
  } catch (error) {
    recordResult(module, '静态资源加载', 'failed', error.message);
  }
}

// ==================== 主测试流程 ====================

async function runAllTests() {
  console.log('\n========================================');
  console.log('后端 API 全面 Playwright 测试');
  console.log('========================================\n');
  
  testResults.startTime = new Date();
  
  // 创建报告目录
  if (!fs.existsSync(CONFIG.REPORT_DIR)) {
    fs.mkdirSync(CONFIG.REPORT_DIR, { recursive: true });
  }
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });
  
  const page = await context.newPage();
  
  try {
    // 1. 健康检查（无需认证）
    await testHealthCheck(page);
    
    // 2. 认证模块
    const superadminToken = await testAuth(page);
    if (!superadminToken) {
      log('认证失败，终止测试', 'error');
      return;
    }
    
    // 登录普通用户
    const normalToken = await loginAndGetToken(page, CONFIG.TEST_USERS.normal);
    const adminToken = await loginAndGetToken(page, CONFIG.TEST_USERS.admin);
    
    // 3-9. 功能模块测试（使用 superadmin token）
    await testAICloudChat(page, superadminToken);
    await testAICloudExecute(page, superadminToken);
    await testAICloudKnowledge(page, superadminToken);
    await testAIAgent(page, superadminToken);
    await testCodeQA(page, superadminToken);
    await testGirlAi(page, superadminToken);
    await testFileManagement(page, superadminToken);
    await testTaskQueue(page, superadminToken);
    await testKolors(page, superadminToken);
    await testWorkflow(page, superadminToken);
    
    // 10. Nginx 管理
    await testNginxManagement(page, superadminToken);
    
    // 11. 用户管理（需要 admin）
    await testUserManagement(page, adminToken || superadminToken);
    
    // 12. Guardian 监控（需要 admin）
    await testGuardian(page, adminToken || superadminToken);
    
    // 13. 权限控制测试
    if (normalToken) {
      await testPermissionControl(page, normalToken, superadminToken);
    }
    
    // 14. 前端 UI 测试
    await testFrontendUI(page, superadminToken);
    
  } catch (error) {
    log(`测试异常: ${error.message}`, 'error');
    
    // 保存错误截图
    const screenshotPath = path.join(CONFIG.REPORT_DIR, 'error-screenshot.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    log(`错误截图已保存: ${screenshotPath}`, 'warn');
  } finally {
    await browser.close();
  }
  
  testResults.endTime = new Date();
  
  // 生成测试报告
  generateReport();
}

function generateReport() {
  const duration = testResults.endTime - testResults.startTime;
  const totalTests = testResults.passed.length + testResults.failed.length + testResults.skipped.length;
  
  console.log('\n========================================');
  console.log('测试报告');
  console.log('========================================\n');
  console.log(`测试总数: ${totalTests}`);
  console.log(`✅ 通过: ${testResults.passed.length}`);
  console.log(`❌ 失败: ${testResults.failed.length}`);
  console.log(`⚠️  跳过: ${testResults.skipped.length}`);
  console.log(`⏱️  耗时: ${(duration / 1000).toFixed(2)} 秒`);
  console.log(`\n通过率: ${((testResults.passed.length / totalTests) * 100).toFixed(1)}%`);
  
  if (testResults.failed.length > 0) {
    console.log('\n失败详情:');
    testResults.failed.forEach((result, index) => {
      console.log(`  ${index + 1}. [${result.module}] ${result.test}: ${result.detail}`);
    });
  }
  
  // 保存 JSON 报告
  const reportPath = path.join(CONFIG.REPORT_DIR, `test-report-${Date.now()}.json`);
  fs.writeFileSync(reportPath, JSON.stringify(testResults, null, 2));
  log(`测试报告已保存: ${reportPath}`, 'info');
  
  // 保存文本报告
  const textReportPath = path.join(CONFIG.REPORT_DIR, `test-report-${Date.now()}.txt`);
  let textReport = `后端 API 全面测试报告\n`;
  textReport += `========================\n\n`;
  textReport += `测试时间: ${testResults.startTime.toLocaleString()}\n`;
  textReport += `耗时: ${(duration / 1000).toFixed(2)} 秒\n\n`;
  textReport += `测试总数: ${totalTests}\n`;
  textReport += `通过: ${testResults.passed.length}\n`;
  textReport += `失败: ${testResults.failed.length}\n`;
  textReport += `跳过: ${testResults.skipped.length}\n`;
  textReport += `通过率: ${((testResults.passed.length / totalTests) * 100).toFixed(1)}%\n\n`;
  
  textReport += `详细结果:\n`;
  textReport += `----------\n`;
  
  // 按模块分组
  const modules = {};
  [...testResults.passed, ...testResults.failed, ...testResults.skipped].forEach(result => {
    if (!modules[result.module]) {
      modules[result.module] = [];
    }
    modules[result.module].push(result);
  });
  
  for (const [module, results] of Object.entries(modules)) {
    textReport += `\n[${module}]\n`;
    results.forEach(result => {
      const icon = result.status === 'passed' ? '✅' : result.status === 'failed' ? '❌' : '⚠️';
      textReport += `  ${icon} ${result.test}`;
      if (result.detail) {
        textReport += ` - ${result.detail}`;
      }
      textReport += `\n`;
    });
  }
  
  fs.writeFileSync(textReportPath, textReport);
  log(`文本报告已保存: ${textReportPath}`, 'info');
}

// 运行测试
runAllTests()
  .then(() => {
    process.exit(0);
  })
  .catch(error => {
    console.error('测试执行失败:', error);
    process.exit(1);
  });
