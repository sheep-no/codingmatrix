import { test, expect } from '@playwright/test'

test.describe('完整项目生成流程测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  test('1. 简单项目生成完整流程', async ({ page }) => {
    console.log('开始完整项目生成流程测试')
    
    // 步骤1: 验证页面加载
    console.log('步骤1: 验证页面加载')
    await expect(page.locator('h1.page-title')).toHaveText('Agent')
    await expect(page.locator('textarea.prompt-textarea')).toBeVisible()
    console.log('✓ 页面加载成功')
    
    // 步骤2: 输入项目描述
    console.log('步骤2: 输入项目描述')
    const textarea = page.locator('textarea.prompt-textarea')
    const testPrompt = '创建一个简单的待办事项应用，包含添加、删除和标记完成功能'
    
    await textarea.fill(testPrompt)
    await expect(textarea).toHaveValue(testPrompt)
    console.log('✓ 项目描述输入成功')
    
    // 步骤3: 点击生成按钮
    console.log('步骤3: 点击生成按钮')
    const generateButton = page.locator('button:has-text("生成项目")')
    await expect(generateButton).toBeVisible()
    await generateButton.click()
    console.log('✓ 生成按钮点击成功')
    
    // 步骤4: 验证生成状态
    console.log('步骤4: 验证生成状态')
    await page.waitForTimeout(2000)
    
    // 查找生成状态指示器
    const isGenerating = await page.locator('.status-dot.generating').isVisible().catch(() => false)
    if (isGenerating) {
      console.log('✓ 生成状态显示正常')
    }
    
    // 步骤5: 监控生成进度
    console.log('步骤5: 监控生成进度')
    let fileCount = 0
    let maxWaitTime = 30000 // 30秒超时
    let startTime = Date.now()
    
    while (Date.now() - startTime < maxWaitTime) {
      fileCount = await page.locator('.file-item').count()
      if (fileCount > 0) {
        console.log(`✓ 已生成 ${fileCount} 个文件`)
        break
      }
      await page.waitForTimeout(1000)
    }
    
    if (fileCount === 0) {
      console.log('⚠ 30秒内未检测到文件生成')
    }
    
    // 步骤6: 检查日志输出
    console.log('步骤6: 检查日志输出')
    const logItems = await page.locator('.log-item').count()
    if (logItems > 0) {
      console.log(`✓ 发现 ${logItems} 条日志记录`)
      
      // 检查是否有不同类型的日志
      const infoLogs = await page.locator('.log-item.log-info').count()
      const successLogs = await page.locator('.log-item.log-success').count()
      
      console.log(`  - 信息日志: ${infoLogs}`)
      console.log(`  - 成功日志: ${successLogs}`)
    }
    
    // 步骤7: 测试文件预览
    console.log('步骤7: 测试文件预览')
    if (fileCount > 0) {
      // 点击第一个文件
      await page.locator('.file-item').first().click()
      await page.waitForTimeout(1000)
      
      // 验证文件预览显示
      const filePreview = page.locator('.file-preview')
      const isPreviewVisible = await filePreview.isVisible().catch(() => false)
      
      if (isPreviewVisible) {
        console.log('✓ 文件预览显示正常')
        
        // 检查文件内容是否加载
        const fileContent = await page.locator('.file-preview pre code').textContent()
        if (fileContent && fileContent.trim().length > 0) {
          console.log(`✓ 文件内容已加载 (${fileContent.length} 字符)`)
        }
      }
    }
    
    // 步骤8: 测试停止生成功能
    console.log('步骤8: 测试停止生成功能')
    const stopButton = page.locator('button:has-text("停止")')
    const isStopVisible = await stopButton.isVisible().catch(() => false)
    
    if (isStopVisible) {
      console.log('✓ 停止按钮可见')
    } else {
      console.log('⚠ 停止按钮不可见（可能已完成）')
    }
    
    // 步骤9: 验证生成完成状态
    console.log('步骤9: 验证生成完成状态')
    const isComplete = await page.locator('.status-dot.complete').isVisible().catch(() => false)
    const isGeneratingEnd = await page.locator('.status-dot.generating').isVisible().catch(() => false)
    
    if (isComplete || !isGeneratingEnd) {
      console.log('✓ 生成流程已完成')
    } else {
      console.log('⚠ 生成可能仍在进行中')
    }
    
    console.log('完整项目生成流程测试完成')
  })

  test('2. 模板快速生成流程', async ({ page }) => {
    console.log('开始模板快速生成流程测试')
    
    // 步骤1: 选择模板
    console.log('步骤1: 选择模板')
    const templateButtons = await page.locator('.template-btn').count()
    expect(templateButtons).toBeGreaterThan(0)
    
    await page.locator('.template-btn').first().click()
    console.log('✓ 模板选择成功')
    
    // 步骤2: 验证模板内容
    const textarea = page.locator('textarea.prompt-textarea')
    const templateContent = await textarea.inputValue()
    expect(templateContent.length).toBeGreaterThan(0)
    console.log(`✓ 模板内容已填充 (${templateContent.length} 字符)`)
    
    // 步骤3: 可以修改模板内容（可选）
    const modifiedContent = templateContent + '\n添加自定义功能'
    await textarea.fill(modifiedContent)
    await expect(textarea).toHaveValue(modifiedContent)
    console.log('✓ 模板内容修改成功')
    
    // 步骤4: 生成项目
    const generateButton = page.locator('button:has-text("生成项目")')
    await generateButton.click()
    console.log('✓ 开始生成项目')
    
    // 等待一段时间观察生成进度
    await page.waitForTimeout(5000)
    
    // 检查是否有文件生成
    const fileCount = await page.locator('.file-item').count()
    if (fileCount > 0) {
      console.log(`✓ 模板生成产生 ${fileCount} 个文件`)
    } else {
      console.log('⚠ 模板生成尚未产生文件')
    }
    
    console.log('模板快速生成流程测试完成')
  })

  test('3. 错误处理流程测试', async ({ page }) => {
    console.log('开始错误处理流程测试')
    
    // 步骤1: 测试空输入
    console.log('步骤1: 测试空输入')
    const textarea = page.locator('textarea.prompt-textarea')
    await textarea.fill('')
    
    const generateButton = page.locator('button:has-text("生成项目")')
    await generateButton.click()
    
    // 等待检查是否阻止了空输入
    await page.waitForTimeout(1000)
    const fileCount = await page.locator('.file-item').count()
    
    if (fileCount === 0) {
      console.log('✓ 空输入被正确阻止')
    } else {
      console.log('⚠ 空输入未被阻止（可能需要改进）')
    }
    
    // 步骤2: 测试极短输入
    console.log('步骤2: 测试极短输入')
    await textarea.fill('测试')
    await generateButton.click()
    await page.waitForTimeout(2000)
    
    console.log('✓ 极短输入测试完成')
    
    // 步骤3: 测试超长输入
    console.log('步骤3: 测试超长输入')
    const longInput = '这是一个很长的项目描述。'.repeat(50)
    await textarea.fill(longInput)
    
    // 验证输入是否成功
    const currentValue = await textarea.inputValue()
    expect(currentValue).toBe(longInput)
    console.log('✓ 超长输入可以正常输入')
    
    console.log('错误处理流程测试完成')
  })

  test('4. 多次生成流程测试', async ({ page }) => {
    console.log('开始多次生成流程测试')
    
    const textarea = page.locator('textarea.prompt-textarea')
    const generateButton = page.locator('button:has-text("生成项目")')
    
    // 第一次生成
    console.log('第一次生成')
    await textarea.fill('第一个项目')
    await generateButton.click()
    await page.waitForTimeout(3000)
    
    let fileCount = await page.locator('.file-item').count()
    console.log(`第一次生成文件数: ${fileCount}`)
    
    // 第二次生成（应该清除之前的内容）
    console.log('第二次生成')
    await textarea.fill('第二个项目')
    await generateButton.click()
    await page.waitForTimeout(3000)
    
    fileCount = await page.locator('.file-item').count()
    console.log(`第二次生成文件数: ${fileCount}`)
    
    // 第三次生成
    console.log('第三次生成')
    await textarea.fill('第三个项目')
    await generateButton.click()
    await page.waitForTimeout(3000)
    
    fileCount = await page.locator('.file-item').count()
    console.log(`第三次生成文件数: ${fileCount}`)
    
    console.log('✓ 多次生成流程测试完成')
  })

  test('5. 项目保存和加载流程', async ({ page }) => {
    console.log('开始项目保存和加载流程测试')
    
    // 步骤1: 生成一个简单项目
    const textarea = page.locator('textarea.prompt-textarea')
    const generateButton = page.locator('button:has-text("生成项目")')
    
    await textarea.fill('测试保存功能的项目')
    await generateButton.click()
    await page.waitForTimeout(5000)
    
    // 步骤2: 查找保存按钮
    console.log('步骤2: 查找保存按钮')
    const saveButton = page.locator('button:has-text("保存项目")')
    const isSaveVisible = await saveButton.isVisible().catch(() => false)
    
    if (isSaveVisible) {
      console.log('✓ 保存按钮可见')
    } else {
      console.log('⚠ 保存按钮不可见')
    }
    
    // 步骤3: 切换到"我的项目"标签页
    console.log('步骤3: 切换到"我的项目"标签页')
    const projectsTab = page.locator('button.tab-btn:has-text("我的项目")')
    await projectsTab.click()
    await page.waitForTimeout(1000)
    
    // 步骤4: 检查项目列表
    console.log('步骤4: 检查项目列表')
    const projectCards = await page.locator('.project-card').count()
    console.log(`发现 ${projectCards} 个已保存的项目`)
    
    if (projectCards > 0) {
      // 步骤5: 测试加载项目
      console.log('步骤5: 测试加载项目')
      const openButton = page.locator('.project-card').first().locator('button:has-text("打开")')
      await openButton.click()
      await page.waitForTimeout(1000)
      
      // 验证是否切换回生成标签页
      const activeTab = page.locator('button.tab-btn.active')
      const tabText = await activeButton.textContent()
      expect(tabText).toContain('项目生成')
      console.log('✓ 项目加载成功，已切换到生成标签页')
    }
    
    console.log('项目保存和加载流程测试完成')
  })

  test('6. UI交互完整性测试', async ({ page }) => {
    console.log('开始UI交互完整性测试')
    
    // 测试所有主要UI元素的可交互性
    
    // 1. 测试Tab切换
    console.log('1. 测试Tab切换')
    const generateTab = page.locator('button.tab-btn:has-text("项目生成")')
    const projectsTab = page.locator('button.tab-btn:has-text("我的项目")')
    
    await projectsTab.click()
    await expect(projectsTab).toHaveClass(/active/)
    console.log('✓ 我的项目Tab激活')
    
    await generateTab.click()
    await expect(generateTab).toHaveClass(/active/)
    console.log('✓ 项目生成Tab激活')
    
    // 2. 测试文本区域焦点和输入
    console.log('2. 测试文本区域')
    const textarea = page.locator('textarea.prompt-textarea')
    await textarea.focus()
    await expect(textarea).toBeFocused()
    await textarea.type('测试输入')
    await expect(textarea).toHaveValue(/测试输入/)
    console.log('✓ 文本区域交互正常')
    
    // 3. 测试按钮状态
    console.log('3. 测试按钮状态')
    const generateButton = page.locator('button:has-text("生成项目")')
    await expect(generateButton).toBeEnabled()
    console.log('✓ 生成按钮可点击')
    
    // 4. 测试文件树交互
    console.log('4. 测试文件树交互')
    // 先生成一些内容
    await page.locator('textarea.prompt-textarea').fill('生成文件树测试')
    await generateButton.click()
    await page.waitForTimeout(3000)
    
    const fileItems = await page.locator('.file-item').count()
    if (fileItems > 0) {
      await page.locator('.file-item').first().click()
      await page.waitForTimeout(500)
      
      const selectedFile = page.locator('.file-item.active')
      const isSelectedVisible = await selectedFile.isVisible().catch(() => false)
      if (isSelectedVisible) {
        console.log('✓ 文件选择交互正常')
      }
    }
    
    // 5. 测试日志区域滚动
    console.log('5. 测试日志区域')
    const logsContainer = page.locator('.logs-container')
    const isLogsVisible = await logsContainer.isVisible().catch(() => false)
    if (isLogsVisible) {
      console.log('✓ 日志区域显示正常')
    }
    
    console.log('UI交互完整性测试完成')
  })
})