import { test, expect } from '@playwright/test'

test.describe('Theme Switcher', () => {
  test('默认加载主题', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher', { timeout: 5000 })
    
    const html = page.locator('html')
    const theme = await html.evaluate(el => {
      if (el.classList.contains('theme-light')) return 'light'
      if (el.classList.contains('theme-default')) return 'default'
      if (el.classList.contains('theme-dark')) return 'dark'
      return 'unknown'
    })
    
    console.log(`Current theme: ${theme}`)
    console.log('HTML classes:', await html.evaluate(el => el.className))
    expect(['light', 'default', 'dark'].includes(theme)).toBeTruthy()
  })

  test('切换到明亮模式', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const lightBtn = page.locator('.theme-switcher .theme-btn').first()
    await lightBtn.click()
    await page.waitForTimeout(500)
    
    const html = page.locator('html')
    const hasLightTheme = await html.evaluate(el => el.classList.contains('theme-light'))
    console.log('Light theme class applied:', hasLightTheme)
    console.log('HTML classes:', await html.evaluate(el => el.className))
    expect(hasLightTheme).toBe(true)
    
    const bgPrimary = await page.evaluate(() => 
      getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()
    )
    console.log('bg-primary value:', bgPrimary)
    expect(bgPrimary).toBe('#ffffff')
  })

  test('切换到默认模式', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const defaultBtn = page.locator('.theme-switcher .theme-btn').nth(1)
    await defaultBtn.click()
    await page.waitForTimeout(500)
    
    const html = page.locator('html')
    const hasDefaultTheme = await html.evaluate(el => el.classList.contains('theme-default'))
    console.log('Default theme class applied:', hasDefaultTheme)
    console.log('HTML classes:', await html.evaluate(el => el.className))
    expect(hasDefaultTheme).toBe(true)
    
    const bgPrimary = await page.evaluate(() => 
      getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()
    )
    console.log('bg-primary value:', bgPrimary)
    expect(bgPrimary).toBe('#fcfdfd')
  })

  test('切换到暗色模式', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const darkBtn = page.locator('.theme-switcher .theme-btn').nth(2)
    await darkBtn.click()
    await page.waitForTimeout(500)
    
    const html = page.locator('html')
    const hasDarkTheme = await html.evaluate(el => el.classList.contains('theme-dark'))
    console.log('Dark theme class applied:', hasDarkTheme)
    console.log('HTML classes:', await html.evaluate(el => el.className))
    expect(hasDarkTheme).toBe(true)
    
    const bgPrimary = await page.evaluate(() => 
      getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()
    )
    console.log('bg-primary value:', bgPrimary)
    expect(bgPrimary).toBe('#0f172a')
    
    const textPrimary = await page.evaluate(() => 
      getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim()
    )
    console.log('text-primary value:', textPrimary)
    expect(textPrimary).toBe('#f8fafc')
  })

  test('主题按钮有正确的激活状态', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const darkBtn = page.locator('.theme-switcher .theme-btn').nth(2)
    await darkBtn.click()
    await page.waitForTimeout(500)
    
    const isActive = await darkBtn.evaluate(el => el.classList.contains('active'))
    expect(isActive).toBe(true)
    
    const lightBtn = page.locator('.theme-switcher .theme-btn').first()
    const lightActive = await lightBtn.evaluate(el => el.classList.contains('active'))
    expect(lightActive).toBe(false)
  })

  test('主题在页面刷新后保持', async ({ page, browserName }) => {
    if (browserName === 'webkit') {
      test.skip()
      return
    }
    
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const darkBtn = page.locator('.theme-switcher .theme-btn').nth(2)
    await darkBtn.click()
    await page.waitForTimeout(500)
    
    await page.reload()
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    
    const html = page.locator('html')
    const hasDarkTheme = await html.evaluate(el => el.classList.contains('theme-dark'))
    expect(hasDarkTheme).toBe(true)
  })

  test('不同主题下的颜色变量值正确', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const themes = [
      {
        name: 'light',
        btnIndex: 0,
        expected: {
          '--bg-primary': '#ffffff',
          '--bg-secondary': '#f8fafc',
          '--text-primary': '#0f172a'
        }
      },
      {
        name: 'default',
        btnIndex: 1,
        expected: {
          '--bg-primary': '#fcfdfd',
          '--bg-secondary': '#f0f7f6',
          '--text-primary': '#1a2e35'
        }
      },
      {
        name: 'dark',
        btnIndex: 2,
        expected: {
          '--bg-primary': '#0f172a',
          '--bg-secondary': '#1e293b',
          '--text-primary': '#f8fafc'
        }
      }
    ]
    
    for (const theme of themes) {
      const btn = page.locator('.theme-switcher .theme-btn').nth(theme.btnIndex)
      await btn.click()
      await page.waitForTimeout(500)
      
      console.log(`\n=== Testing ${theme.name} theme ===`)
      console.log('HTML classes:', await page.evaluate(() => document.documentElement.className))
      
      for (const [varName, expectedValue] of Object.entries(theme.expected)) {
        const actualValue = await page.evaluate(v => 
          getComputedStyle(document.documentElement).getPropertyValue(v).trim()
        , varName)
        
        console.log(`${theme.name} theme - ${varName}: ${actualValue} (expected: ${expectedValue})`)
        expect(actualValue).toBe(expectedValue)
      }
    }
  })

  test('主题切换后组件样式正确应用', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    await page.waitForSelector('.theme-switcher .theme-btn', { state: 'visible' })
    
    const darkBtn = page.locator('.theme-switcher .theme-btn').nth(2)
    await darkBtn.click()
    await page.waitForTimeout(500)
    
    const appBg = await page.evaluate(() => {
      const app = document.querySelector('#app')
      return getComputedStyle(app).backgroundColor
    })
    
    expect(appBg).not.toBe('rgb(255, 255, 255)')
  })
})
