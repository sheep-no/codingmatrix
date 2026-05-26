import { test, expect } from '@playwright/test'
import { apiLogin } from './fixtures/auth.js'

test('debug agent page CSS loading timing', async ({ page }) => {
  await apiLogin(page)
  await page.waitForTimeout(1000)

  // Check token before navigating
  const tokenBeforeNav = await page.evaluate(() => {
    return {
      sessionToken: sessionStorage.getItem('_token'),
      localToken: localStorage.getItem('access_token'),
      userStore: localStorage.getItem('user-store')
    }
  })
  
  console.log('Token before navigation:', JSON.stringify(tokenBeforeNav, null, 2))

  // Navigate to agent page and track CSS loading
  const navigationStart = Date.now()
  
  await page.goto('http://localhost:3000/agent', { waitUntil: 'domcontentloaded' })
  const domContentLoaded = Date.now()
  
  await page.waitForLoadState('load')
  const loadComplete = Date.now()
  
  await page.waitForTimeout(1000)
  const after1s = Date.now()
  
  await page.waitForTimeout(2000)
  const after3s = Date.now()

  // Check CSS at different timestamps
  const cssTiming = await page.evaluate(() => {
    const checkStyles = () => {
      const agentPage = document.querySelector('.agent-page')
      const pageContent = document.querySelector('.page-content')
      const leftPanel = document.querySelector('.left-panel')
      
      return {
        hasAgentPage: !!agentPage,
        hasPageContent: !!pageContent,
        hasLeftPanel: !!leftPanel,
        agentPageStyles: agentPage ? {
          display: window.getComputedStyle(agentPage).display,
          height: window.getComputedStyle(agentPage).height,
          backgroundColor: window.getComputedStyle(agentPage).backgroundColor,
        } : null,
        pageContentStyles: pageContent ? {
          display: window.getComputedStyle(pageContent).display,
          gridTemplateColumns: window.getComputedStyle(pageContent).gridTemplateColumns,
        } : null,
      }
    }
    
    return {
      initial: checkStyles(),
    }
  })

  // Check token after navigation
  const tokenAfterNav = await page.evaluate(() => {
    return {
      sessionToken: sessionStorage.getItem('_token'),
      localToken: localStorage.getItem('access_token'),
      windowUserStore: window.userStore ? window.userStore.getAccessToken() : 'not available'
    }
  })
  
  console.log('Token after navigation:', JSON.stringify(tokenAfterNav, null, 2))

  // Take screenshot
  await page.screenshot({ path: 'test-results/agent-css-timing.png', fullPage: true })
  
  console.log('Navigation Timing:', {
    domContentLoaded: domContentLoaded - navigationStart,
    loadComplete: loadComplete - navigationStart,
    after1s: after1s - navigationStart,
    after3s: after3s - navigationStart,
  })
  
  console.log('CSS Status:', JSON.stringify(cssTiming, null, 2))

  expect(cssTiming.initial.hasAgentPage).toBeTruthy()
})
