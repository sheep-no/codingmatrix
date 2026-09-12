import { test, expect } from '@playwright/test'

const EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || '12345678'

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
    const permissionLevel = data.permission_level
    if (!permissionLevel) {
      return { ok: false, status: loginResp.status, detail: 'login response missing permission_level' }
    }
    const expiry = Date.now() + 3600000
    const username = data.username || email
    sessionStorage.setItem('_token', data.access_token)
    sessionStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('_token_expiry', String(expiry))
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('username', username)
    localStorage.setItem('email', email)
    localStorage.setItem('permission_level', permissionLevel)
    localStorage.setItem('user-store', JSON.stringify({
      isLoggedIn: true,
      username,
      email,
      permissionLevel,
    }))
    return { ok: true, status: loginResp.status, permissionLevel, username }
  }, { email: EMAIL, password: PASSWORD })
  expect(login.ok, `login failed: ${JSON.stringify(login)}`).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  return login
}

async function clearAdminMenuState(page) {
  await page.evaluate(() => localStorage.removeItem('adminMenuState'))
}

function consoleHeading(permissionLevel) {
  if (permissionLevel === 'superadmin') return '系统管理控制台'
  if (permissionLevel === 'admin') return '管理员控制台'
  return 'Nginx 配置工具'
}

async function openAdminPanel(page) {
  await page.locator('#toolkit').click()
  const menu = page.locator('#toolkit-menu')
  await expect(menu).toBeVisible()
  const adminItem = menu.getByText('管理员面板', { exact: true })
  const visible = await adminItem.isVisible().catch(() => false)
  if (visible) {
    const popupPromise = page.waitForEvent('popup', { timeout: 8000 }).catch(() => null)
    await adminItem.click()
    const popup = await popupPromise
    if (popup) {
      await popup.waitForLoadState('domcontentloaded')
      await expect(popup.locator('.admin-panel')).toBeVisible({ timeout: 15000 })
      return popup
    }
  }
  await page.goto('/admin', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.admin-panel')).toBeVisible({ timeout: 15000 })
  return page
}

async function returnAndReopen(homePage, adminPage) {
  if (adminPage !== homePage && !adminPage.isClosed()) {
    await adminPage.close()
    await expect(homePage.locator('#toolkit')).toBeVisible({ timeout: 15000 })
    return openAdminPanel(homePage)
  }
  await adminPage.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(adminPage.locator('#toolkit')).toBeVisible({ timeout: 15000 })
  return openAdminPanel(adminPage)
}

async function expectSeedUserVisible(admin) {
  await expect(admin.locator('.users-section')).toBeVisible()
  await expect(admin.locator('.user-card').first()).toBeVisible({ timeout: 15000 })
  const seedEmail = admin.locator('.user-email', { hasText: EMAIL })
  if (await seedEmail.count()) {
    await expect(seedEmail.first()).toBeVisible()
    return
  }
  await admin.locator('.users-filters input[placeholder="用户名或邮箱..."]').fill('admin_test')
  await expect(admin.locator('.user-email', { hasText: EMAIL })).toBeVisible({ timeout: 10000 })
}

test.describe('管理员界面浏览器场景', () => {
  test.describe.configure({ mode: 'serial' })
  test.use({ viewport: { width: 1400, height: 900 } })

  test('空搜索、切用户管理、关创建框、关退出确认、返回后再进仍在用户管理', async ({ page }) => {
    test.setTimeout(90000)
    const login = await loginOnFrontend(page)
    await clearAdminMenuState(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    let admin = await openAdminPanel(page)
    await expect(admin.locator('.logo-text h1')).toHaveText(consoleHeading(login.permissionLevel))
    await expect(admin.locator('.header-info')).toContainText(login.username)
    await expect(admin.getByRole('heading', { name: '系统监控仪表板' })).toBeVisible()
    await expect(admin.getByRole('heading', { name: 'CPU 使用率' })).toBeVisible()
    await expect(admin.locator('.nav-item', { hasText: '模型管理' })).toHaveCount(0)
    await expect(admin.locator('.nav-item', { hasText: '代码沙箱' })).toHaveCount(0)

    const search = admin.locator('.search-input')
    await search.fill('用户')
    await expect(admin.locator('.nav-item', { hasText: '用户管理' })).toBeVisible()
    await admin.locator('.clear-btn').click()
    await expect(search).toHaveValue('')

    await admin.locator('.nav-item', { hasText: '用户管理' }).click()
    await expectSeedUserVisible(admin)

    await admin.locator('.create-user-btn').click()
    const createDialog = admin.locator('.modal-overlay', { hasText: '创建用户' })
    await expect(createDialog).toBeVisible()
    await createDialog.getByRole('button', { name: '取消' }).click()
    await expect(createDialog).toHaveCount(0)
    await expectSeedUserVisible(admin)

    await admin.locator('.logout-btn').click()
    const logoutDialog = admin.getByRole('dialog')
    await expect(logoutDialog).toBeVisible()
    await logoutDialog.getByRole('button', { name: '取消' }).click()
    await expect(logoutDialog).toHaveCount(0)
    await expect(admin.locator('.admin-panel')).toBeVisible()

    admin = await returnAndReopen(page, admin)
    await expect(admin.locator('.users-section')).toBeVisible()
    await expect(admin.locator('.nav-item', { hasText: '用户管理' }).first()).toHaveClass(/active/)
    await expectSeedUserVisible(admin)
  })

  test('刷新后仍在用户管理，途中切日志再回仍可继续', async ({ page }) => {
    test.setTimeout(120000)
    const login = await loginOnFrontend(page)
    await clearAdminMenuState(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    let admin = await openAdminPanel(page)
    await expect(admin.locator('.logo-text h1')).toHaveText(consoleHeading(login.permissionLevel))
    await admin.locator('.nav-item', { hasText: '用户管理' }).click()
    await expectSeedUserVisible(admin)

    await admin.reload({ waitUntil: 'domcontentloaded' })
    await expect(admin.locator('.admin-panel')).toBeVisible({ timeout: 15000 })
    await expect(admin.locator('.users-section')).toBeVisible()
    await expect(admin.locator('.nav-item', { hasText: '用户管理' }).first()).toHaveClass(/active/)
    await expectSeedUserVisible(admin)

    await admin.locator('.nav-item', { hasText: '系统日志' }).first().click()
    await expect(admin.locator('.logs-section')).toBeVisible()
    await expect(admin.getByText('日志面板')).toBeVisible()

    admin = await returnAndReopen(page, admin)
    await expect(admin.locator('.logs-section')).toBeVisible()
    await expect(admin.getByText('日志面板')).toBeVisible()
    await expect(admin.locator('.nav-item', { hasText: '系统日志' }).first()).toHaveClass(/active/)
    await admin.locator('.nav-item', { hasText: '用户管理' }).click()
    await expect(admin.locator('.users-section')).toBeVisible()
    await expect(admin.locator('.create-user-btn')).toBeEnabled()
  })
})
