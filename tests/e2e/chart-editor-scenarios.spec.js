import { test, expect } from '@playwright/test'

const EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || '12345678'

const salesData = [
  { month: 'Jan', sales: 12 },
  { month: 'Feb', sales: 24 },
  { month: 'Mar', sales: 18 },
]

async function loginOnFrontend(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  const login = await page.evaluate(async ({ email, password }) => {
    const csrfResp = await fetch('/api/v1/csrf-token', { credentials: 'include' })
    const csrfData = await csrfResp.json()
    const loginResp = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfData.csrf_token,
      },
      body: JSON.stringify({ email, password }),
    })
    const data = await loginResp.json().catch(() => ({}))
    if (!loginResp.ok || !data.access_token) {
      return { ok: false, status: loginResp.status, detail: data.detail || data.message || '' }
    }
    const expiry = Date.now() + 3600000
    sessionStorage.setItem('_token', data.access_token)
    sessionStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('username', data.username || email)
    localStorage.setItem('email', email)
    localStorage.setItem('permission_level', data.permission_level || 'superadmin')
    localStorage.setItem('user-store', JSON.stringify({
      isLoggedIn: true,
      username: data.username || email,
      email,
      permissionLevel: data.permission_level || 'superadmin',
    }))
    return { ok: true, status: loginResp.status }
  }, { email: EMAIL, password: PASSWORD })
  expect(login.ok, `login failed: ${JSON.stringify(login)}`).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
}

async function clearChartDrafts(page) {
  await page.evaluate(() => {
    Object.keys(localStorage)
      .filter((key) => key.startsWith('chart-editor-draft-v'))
      .forEach((key) => localStorage.removeItem(key))
  })
}

async function openChartEditor(page) {
  await page.locator('#toolkit').click()
  const menu = page.locator('#toolkit-menu')
  await expect(menu).toBeVisible()
  const popupPromise = page.waitForEvent('popup', { timeout: 8000 }).catch(() => null)
  await menu.getByText('图表编辑器', { exact: true }).click()
  const popup = await popupPromise
  if (popup) {
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.getByRole('heading', { name: '图表编辑器' })).toBeVisible({ timeout: 15000 })
    return popup
  }
  await page.goto('/chart-editor', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '图表编辑器' })).toBeVisible({ timeout: 15000 })
  return page
}

async function returnAndReopen(homePage, editorPage) {
  const closePromise = editorPage.waitForEvent('close', { timeout: 5000 }).catch(() => null)
  await editorPage.locator('.back-btn').click()
  await closePromise
  if (editorPage.isClosed()) {
    return openChartEditor(homePage)
  }
  await expect(editorPage).toHaveURL(/\/(?:$|\?)/, { timeout: 10000 })
  await editorPage.goto('/chart-editor', { waitUntil: 'domcontentloaded' })
  await expect(editorPage.getByRole('heading', { name: '图表编辑器' })).toBeVisible({ timeout: 15000 })
  return editorPage
}

async function uploadSalesData(editorPage) {
  await editorPage.locator('input[type="file"]').first().setInputFiles({
    name: 'sales.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(salesData)),
  })
  await expect(editorPage.locator('.data-item')).toContainText('sales.json')
}

test.describe('图表编辑器浏览器场景', () => {
  test.describe.configure({ mode: 'serial' })
  test.use({ viewport: { width: 1400, height: 900 } })

  test('空添加禁用、切类型、关清空框、返回后再进仍保留草稿', async ({ page }) => {
    test.setTimeout(90000)
    await loginOnFrontend(page)
    await clearChartDrafts(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    let editor = await openChartEditor(page)
    await expect(editor.getByRole('button', { name: '添加图表' })).toBeDisabled()
    await expect(editor.getByText('请先导入数据')).toBeVisible()

    await uploadSalesData(editor)
    await expect(editor.getByRole('button', { name: '添加图表' })).toBeEnabled()

    await editor.locator('.chart-type-card', { hasText: '折线图' }).click()
    await expect(editor.locator('.chart-type-card', { hasText: '折线图' })).toHaveClass(/active/)

    await editor.getByRole('button', { name: '添加图表' }).click()
    await expect(editor.locator('.chart-preview-item')).toHaveCount(1)
    await expect(editor.locator('.chart-container canvas')).toBeVisible()

    const title = `E2E图表场景 ${Date.now()}`
    await editor.getByPlaceholder('图表标题').fill(title)
    await expect(editor.locator('.chart-preview-title')).toHaveText(title)

    await editor.getByRole('button', { name: '清空所有图表' }).click()
    const confirm = editor.getByRole('dialog')
    await expect(confirm).toBeVisible()
    await confirm.getByRole('button', { name: '取消' }).click()
    await expect(confirm).toHaveCount(0)
    await expect(editor.locator('.chart-preview-item')).toHaveCount(1)

    editor = await returnAndReopen(page, editor)
    await expect(editor.locator('.data-item')).toContainText('sales.json')
    await expect(editor.locator('.chart-preview-title')).toHaveText(title)
    await expect(editor.getByText('需要重新选择文件')).toBeVisible()
    await expect(editor.locator('.chart-type-card', { hasText: '折线图' })).toHaveClass(/active/)
  })

  test('刷新后草稿还在，途中返回可再打开并继续编辑', async ({ page }) => {
    test.setTimeout(120000)
    await loginOnFrontend(page)
    await clearChartDrafts(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    let editor = await openChartEditor(page)
    await uploadSalesData(editor)
    await editor.getByRole('button', { name: '添加图表' }).click()
    await expect(editor.locator('.chart-preview-item')).toHaveCount(1)

    const title = `E2E图表刷新 ${Date.now()}`
    await editor.getByPlaceholder('图表标题').fill(title)
    await expect(editor.locator('.chart-preview-title')).toHaveText(title)

    await editor.reload({ waitUntil: 'domcontentloaded' })
    await expect(editor.getByRole('heading', { name: '图表编辑器' })).toBeVisible({ timeout: 15000 })
    await expect(editor.locator('.chart-preview-title')).toHaveText(title)
    await expect(editor.locator('.data-item')).toContainText('sales.json')
    await expect(editor.getByText('需要重新选择文件')).toBeVisible()

    await uploadSalesData(editor)
    await expect(editor.locator('.data-item')).toContainText('3 行 · 2 字段')
    await expect(editor.locator('.chart-container canvas')).toBeVisible()

    const midTitle = `E2E途中返回 ${Date.now()}`
    await editor.getByPlaceholder('图表标题').fill(midTitle)
    await expect(editor.locator('.chart-preview-title')).toHaveText(midTitle)
    editor = await returnAndReopen(page, editor)
    await expect(editor.getByRole('heading', { name: '图表编辑器' })).toBeVisible()
    await expect(editor.locator('.chart-preview-title')).toHaveText(midTitle)
    await expect(editor.getByPlaceholder('图表标题')).toBeEnabled()
    await expect(editor.locator('.data-item')).toContainText('sales.json')
  })
})
