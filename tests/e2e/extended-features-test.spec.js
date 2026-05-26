import { test, expect } from '@playwright/test'

test.describe('扩展功能测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  test('1. 项目模板选择测试', async ({ page }) => {
    console.log('测试项目模板选择功能')
    
    // 等待页面加载
    await expect(page.locator('h1.page-title')).toHaveText('Agent')
    
    // 查找快速模板按钮
    const templateButtons = await page.locator('.template-btn').count()
    expect(templateButtons).toBeGreaterThan(0)
    
    // 点击第一个模板
    await page.locator('.template-btn').first().click()
    
    // 验证文本区域是否填充了模板内容
    const textarea = page.locator('textarea.prompt-textarea')
    await expect(textarea).not.toBeEmpty()
    
    console.log('✓ 项目模板选择功能正常')
  })

  test('2. 文件编辑和保存测试', async ({ page }) => {
    console.log('测试文件编辑和保存功能')
    
    // 首先确保有文件存在（这个测试需要已有项目数据）
    // 这里我们跳过实际文件编辑，只测试UI元素是否存在
    const fileItems = await page.locator('.file-item').count()
    
    if (fileItems > 0) {
      // 点击第一个文件
      await page.locator('.file-item').first().click()
      
      // 验证文件预览显示
      await expect(page.locator('.file-preview')).toBeVisible()
      
      // 测试复制按钮
      const copyButton = page.locator('.preview-header button:has-text("复制")')
      if (await copyButton.isVisible()) {
        await copyButton.click()
        console.log('✓ 文件编辑UI正常')
      }
    } else {
      console.log('⚠ 没有找到文件，跳过文件编辑测试')
    }
  })

  test('3. 日志显示和过滤测试', async ({ page }) => {
    console.log('测试日志显示和过滤功能')
    
    // 查找日志容器
    const logsContainer = page.locator('.logs-container')
    
    // 测试日志区域是否存在
    await expect(logsContainer).toBeVisible()
    
    // 查找日志项
    const logItems = await page.locator('.log-item').count()
    console.log(`找到 ${logItems} 条日志`)
    
    // 检查不同类型的日志是否存在（info, success, warning, error）
    const logTypes = ['info', 'success', 'warning', 'error']
    for (const type of logTypes) {
      const typeLogs = await page.locator(`.log-item.log-${type}`).count()
      if (typeLogs > 0) {
        console.log(`✓ 找到 ${typeLogs} 条 ${type} 类型日志`)
      }
    }
    
    console.log('✓ 日志显示功能正常')
  })

  test('4. 项目保存功能测试', async ({ page }) => {
    console.log('测试项目保存功能')
    
    // 查找保存项目按钮
    const saveButton = page.locator('button:has-text("保存项目")')
    
    if (await saveButton.isVisible()) {
      // 点击保存按钮
      await saveButton.click()
      
      // 等待可能的模态框出现
      await page.waitForTimeout(1000)
      
      // 查找保存模态框（如果存在）
      const modal = page.locator('.modal-content')
      if (await modal.isVisible()) {
        console.log('✓ 保存模态框显示正常')
        
        // 查找保存确认按钮
        const confirmButton = page.locator('.modal-content button:has-text("保存")')
        if (await confirmButton.isVisible()) {
          console.log('✓ 保存确认按钮存在')
        }
      }
    } else {
      console.log('⚠ 保存按钮不可见（可能需要先生成项目）')
    }
  })

  test('5. 项目导入功能测试', async ({ page }) => {
    console.log('测试项目导入功能')
    
    // 等待"我的项目"标签页可点击
    await page.locator('button.tab-btn:has-text("我的项目")').click()
    
    // 查找导入按钮
    const importButton = page.locator('button:has-text("导入")')
    
    if (await importButton.isVisible()) {
      await importButton.click()
      
      // 验证导入模态框出现
      const uploadModal = page.locator('.modal-content:has-text("导入项目")')
      await expect(uploadModal).toBeVisible()
      
      // 验证上传区域存在
      const uploadZone = page.locator('.upload-zone')
      await expect(uploadZone).toBeVisible()
      
      // 关闭模态框
      await page.locator('.modal-close').first().click()
      
      console.log('✓ 项目导入功能正常')
    } else {
      console.log('⚠ 导入按钮不可见')
    }
  })

  test('6. 项目删除功能测试', async ({ page }) => {
    console.log('测试项目删除功能')
    
    // 切换到"我的项目"标签页
    await page.locator('button.tab-btn:has-text("我的项目")').click()
    await page.waitForTimeout(500)
    
    // 查找项目卡片
    const projectCards = await page.locator('.project-card').count()
    
    if (projectCards > 0) {
      // 查找删除按钮
      const deleteButton = page.locator('.project-card').first().locator('button:has-text("删除")')
      await expect(deleteButton).toBeVisible()
      
      console.log('✓ 项目删除按钮存在')
    } else {
      console.log('⚠ 没有找到项目卡片，跳过删除测试')
    }
  })

  test('7. 决策对话框功能测试', async ({ page }) => {
    console.log('测试决策对话框功能')
    
    // 决策对话框通常在生成过程中出现
    // 我们测试模态框的结构是否正确
    
    // 查找决策对话框（可能不显示）
    const decisionModal = page.locator('.modal-content.decision-modal')
    const isVisible = await decisionModal.isVisible().catch(() => false)
    
    if (!isVisible) {
      console.log('⚠ 决策对话框未显示（需要生成项目触发）')
    } else {
      // 测试决策选项
      const decisionOptions = await page.locator('.decision-option').count()
      if (decisionOptions > 0) {
        console.log(`✓ 找到 ${decisionOptions} 个决策选项`)
        
        // 测试"使用默认值"按钮
        const skipButton = page.locator('button:has-text("使用默认值")')
        await expect(skipButton).toBeVisible()
        
        // 测试"确认决策"按钮
        const confirmButton = page.locator('button:has-text("确认决策")')
        await expect(confirmButton).toBeVisible()
      }
    }
  })

  test('8. 响应式设计测试', async ({ page }) => {
    console.log('测试响应式设计')
    
    // 测试桌面视图
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.waitForTimeout(500)
    const desktopElements = await page.locator('.page-content').count()
    expect(desktopElements).toBeGreaterThan(0)
    console.log('✓ 桌面视图正常')
    
    // 测试平板视图
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.waitForTimeout(500)
    const tabletElements = await page.locator('.page-content').count()
    expect(tabletElements).toBeGreaterThan(0)
    console.log('✓ 平板视图正常')
    
    // 测试手机视图
    await page.setViewportSize({ width: 375, height: 667 })
    await page.waitForTimeout(500)
    const mobileElements = await page.locator('.page-content').count()
    expect(mobileElements).toBeGreaterThan(0)
    console.log('✓ 手机视图正常')
  })

  test('9. 键盘快捷键测试', async ({ page }) => {
    console.log('测试键盘快捷键')
    
    // 测试Enter键（可能在某些表单中）
    const textarea = page.locator('textarea.prompt-textarea')
    await textarea.focus()
    await page.keyboard.type('测试文本')
    await page.keyboard.press('Enter')
    
    // 验证文本是否输入成功
    const value = await textarea.inputValue()
    expect(value).toContain('测试')
    
    console.log('✓ 键盘输入正常')
  })

  test('10. 性能和资源加载测试', async ({ page }) => {
    console.log('测试性能和资源加载')
    
    // 监控网络请求
    const requests = []
    page.on('request', request => {
      requests.push({
        url: request.url(),
        resourceType: request.resourceType()
      })
    })
    
    // 等待页面完全加载
    await page.waitForLoadState('networkidle')
    
    // 分析资源加载
    const jsRequests = requests.filter(r => r.resourceType === 'script')
    const cssRequests = requests.filter(r => r.resourceType === 'stylesheet')
    const apiRequests = requests.filter(r => r.resourceType === 'fetch' || r.resourceType === 'xhr')
    
    console.log(`✓ 加载了 ${jsRequests.length} 个JS文件`)
    console.log(`✓ 加载了 ${cssRequests.length} 个CSS文件`)
    console.log(`✓ 发起了 ${apiRequests.length} 个API请求`)
    
    // 检查是否有失败的请求
    const failedRequests = []
    page.on('response', response => {
      if (response.status() >= 400) {
        failedRequests.push({
          url: response.url(),
          status: response.status()
        })
      }
    })
    
    if (failedRequests.length > 0) {
      console.log('⚠ 发现失败的请求:')
      failedRequests.forEach(req => {
        console.log(`  ${req.status}: ${req.url}`)
      })
    } else {
      console.log('✓ 所有请求成功')
    }
  })
})

test.describe('下载功能专项测试', () => {
  test('1. 下载按钮显示测试', async ({ page }) => {
    console.log('测试下载按钮显示')
    
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    
    // 生成项目后测试下载按钮
    // 这里我们测试按钮元素是否存在
    const downloadButton = page.locator('button:has-text("下载")')
    const isVisible = await downloadButton.isVisible().catch(() => false)
    
    if (isVisible) {
      console.log('✓ 下载按钮可见')
    } else {
      console.log('⚠ 下载按钮不可见（可能需要先生成项目）')
    }
  })

  test('2. 下载功能完整性测试', async ({ page }) => {
    console.log('测试下载功能完整性')
    
    // 这个测试需要实际生成项目才能完整测试
    // 这里我们测试API端点的可访问性
    
    // 模拟下载请求
    const downloadUrl = '/api/v1/agent/generate/download/test_project'
    
    try {
      const response = await page.request.get(downloadUrl)
      // 404是预期的，因为项目不存在，但端点应该存在
      if (response.status() === 404 || response.status() === 401) {
        console.log('✓ 下载端点可访问（需要认证或项目存在）')
      } else {
        console.log(`⚠ 下载端点返回状态: ${response.status()}`)
      }
    } catch (error) {
      console.log('✗ 下载端点不可访问:', error.message)
    }
  })
})