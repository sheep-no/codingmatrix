// @ts-check
const { test, expect } = require('@playwright/test')

/**
 * 模拟用户在前端输入并调用 code 接口
 */
test.describe('Code API 前端调用测试', () => {
  let authToken = ''

  test.beforeAll(async ({ request }) => {
    // 先注册一个测试用户获取 token
    try {
      const registerResponse = await request.post('http://localhost:8000/api/v1/register', {
        data: {
          username: 'testuser_' + Date.now(),
          email: `test_${Date.now()}@example.com`,
          password: 'TestPassword123!',
          permission_level: 'normal'
        }
      })
      console.log('注册响应:', registerResponse.status())
      
      if (registerResponse.ok()) {
        const regData = await registerResponse.json()
        console.log('注册成功:', regData)
      }
    } catch (e) {
      console.log('注册失败（可能已存在）:', e.message)
    }

    // 登录获取 token
    try {
      const loginResponse = await request.post('http://localhost:8000/api/v1/login', {
        data: {
          username: 'admin',
          password: 'admin123'
        }
      })
      console.log('登录响应状态:', loginResponse.status())
      
      if (loginResponse.ok()) {
        const loginData = await loginResponse.json()
        authToken = loginData.access_token || loginData.token || ''
        console.log('获取到 token:', authToken ? '是' : '否')
      }
    } catch (e) {
      console.log('登录失败:', e.message)
    }
  })

  test('1. 访问首页', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    
    await page.screenshot({ path: 'test-results/01-initial.png' })
    console.log('页面标题:', await page.title())
    
    const bodyText = await page.locator('body').innerText()
    console.log('页面内容（前300字符）:', bodyText.substring(0, 300))
  })

  test('2. 模拟调用 chat 接口（非流式）', async ({ request }) => {
    const headers = {
      'Content-Type': 'application/json',
    }
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`
    }

    const response = await request.post('http://localhost:8000/api/v1/chat', {
      headers,
      data: {
        prompt: '你好，请简单介绍一下 Python',
        model: 'Qwen/Qwen2.5-7B-Instruct',
        stream: false,
        enable_search: false
      }
    })
    
    console.log('响应状态:', response.status())
    const body = await response.text()
    console.log('响应内容（前500字符）:', body.substring(0, 500))
    
    // 验证响应（200 或 401）
    expect([200, 401]).toContain(response.status())
  })

  test('3. 模拟调用 chat 接口（流式）', async ({ request }) => {
    const headers = {
      'Content-Type': 'application/json',
    }
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`
    }

    const response = await request.post('http://localhost:8000/api/v1/chat', {
      headers,
      data: {
        prompt: '写一个 Hello World 的 Python 程序',
        model: 'Qwen/Qwen2.5-7B-Instruct',
        stream: true,
        enable_search: false
      }
    })
    
    console.log('流式响应状态:', response.status())
    console.log('Content-Type:', response.headers()['content-type'])
    
    const body = await response.text()
    console.log('流式响应内容（前800字符）:', body.substring(0, 800))
    
    expect([200, 401]).toContain(response.status())
  })

  test('4. 测试带搜索功能的 chat 接口', async ({ request }) => {
    const headers = {
      'Content-Type': 'application/json',
    }
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`
    }

    const response = await request.post('http://localhost:8000/api/v1/chat', {
      headers,
      data: {
        prompt: 'Python 最新版本是什么？',
        model: 'Qwen/Qwen2.5-7B-Instruct',
        stream: false,
        enable_search: true,
        search_count: 3
      }
    })
    
    console.log('搜索响应状态:', response.status())
    const body = await response.text()
    console.log('搜索响应内容（前500字符）:', body.substring(0, 500))
    
    expect([200, 401]).toContain(response.status())
  })

  test('5. 测试 chat 空 prompt 校验', async ({ request }) => {
    const headers = {
      'Content-Type': 'application/json',
    }
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`
    }

    const response = await request.post('http://localhost:8000/api/v1/chat', {
      headers,
      data: {
        prompt: '',
        model: 'Qwen/Qwen2.5-7B-Instruct',
        stream: false
      }
    })
    
    console.log('空 prompt 响应状态:', response.status())
    const body = await response.text()
    console.log('空 prompt 响应:', body)
    
    // 应该返回 422 验证错误或 401 未授权
    expect([401, 422]).toContain(response.status())
  })

  test('6. 在浏览器中模拟前端交互', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(3000)
    
    await page.screenshot({ path: 'test-results/06-homepage.png', fullPage: true })
    
    // 检查页面元素
    const inputCount = await page.locator('textarea, input[type="text"]').count()
    console.log('找到输入元素数量:', inputCount)
    
    // 查找聊天相关元素
    const chatElements = await page.locator('[class*="chat"], [class*="Chat"]').count()
    console.log('聊天相关元素:', chatElements)
    
    const inputElements = await page.locator('[class*="input"], [class*="Input"]').count()
    console.log('输入相关元素:', inputElements)
    
    // 尝试找到输入框并输入
    const textarea = page.locator('textarea').first()
    if (await textarea.count() > 0) {
      await textarea.fill('测试输入：你好')
      console.log('已输入测试文本')
      await page.screenshot({ path: 'test-results/06-input.png' })
    }
    
    // 检查是否有发送按钮
    const sendButton = page.locator('button:has-text("发送"), button:has-text("Send"), [class*="send"]').first()
    if (await sendButton.count() > 0) {
      console.log('找到发送按钮')
    }
  })
})
