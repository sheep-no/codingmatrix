const { test, expect } = require('@playwright/test')

test('简单项目生成测试', async ({ page }) => {
  test.setTimeout(300000) // 5 分钟

  // 登录
  await page.goto('/')
  await page.waitForTimeout(2000)

  await page.evaluate(async () => {
    const csrfResponse = await fetch('/api/v1/csrf-token', { credentials: 'include' })
    const csrfData = await csrfResponse.json()

    const loginResponse = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfData.csrf_token
      },
      body: JSON.stringify({ email: 'admin@example.com', password: 'admin123' })
    })

    const data = await loginResponse.json()
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('username', data.username || 'admin')
    localStorage.setItem('permission_level', data.permission_level || 'superadmin')
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify([{
      token: 'test-token-for-e2e',
      provider: 'siliconflow',
      status: 'verified',
      enabled: true
    }]))
  })

  // 导航到 Agent 页面
  await page.goto('/agent')
  await page.waitForTimeout(3000)

  // 输入需求
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 10000 })
  await textarea.fill('创建一个简单的 Python 计算器，支持加减乘除运算')
  await page.waitForTimeout(500)

  // 点击生成按钮
  const generateButton = page.locator('button:has-text("开始生成")').first()
  await expect(generateButton).toBeVisible({ timeout: 5000 })
  await generateButton.click()

  const startTime = Date.now()
  console.log('开始生成...')

  // 等待生成完成 - 检查文件列表出现
  let completed = false
  let attempts = 0
  const maxAttempts = 240 // 4 分钟

  while (!completed && attempts < maxAttempts) {
    await page.waitForTimeout(1000)
    attempts++

    const status = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      const hasStopButton = buttons.some(btn => btn.textContent?.includes('停止'))
      const hasGeneratingButton = buttons.some(btn => btn.textContent?.includes('生成中'))
      const hasProgressBar = document.querySelector('.progress-bar, [class*="progress"]')
      
      // 检查是否有文件列表
      const fileItems = document.querySelectorAll('.file-item, .file-list-item, [class*="file-item"]')
      
      // 检查是否有完成提示
      const bodyText = document.body.innerText || ''
      const hasCompleted = bodyText.includes('生成完成') || bodyText.includes('已完成')
      
      return {
        isGenerating: hasStopButton || hasGeneratingButton || hasProgressBar,
        fileCount: fileItems.length,
        hasCompleted
      }
    })

    if (attempts % 10 === 0) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(0)
      console.log(`[${elapsed}s] 生成中... 文件数: ${status.fileCount}, 生成中: ${status.isGenerating}`)
    }

    // 如果不再生成中且有文件，或者有完成提示，则认为完成
    if ((!status.isGenerating && status.fileCount > 0) || status.hasCompleted) {
      completed = true
    }
  }

  const totalTime = ((Date.now() - startTime) / 1000).toFixed(1)
  console.log(`生成完成，总耗时: ${totalTime}s`)

  // 获取最终文件列表
  const files = await page.evaluate(() => {
    const fileItems = document.querySelectorAll('.file-item, .file-list-item, [class*="file-item"]')
    return Array.from(fileItems).map(item => item.textContent?.trim()).filter(Boolean)
  })
  console.log(`生成的文件: ${files.length} 个`)
  files.forEach(f => console.log(`  - ${f}`))

  // 验证生成了文件
  expect(files.length).toBeGreaterThan(0)
  expect(totalTime).toBeLessThan(300) // 应该在 5 分钟内完成
})
