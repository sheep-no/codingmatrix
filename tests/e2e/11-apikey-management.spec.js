// @ts-check
const { test, expect } = require('@playwright/test')
const { apiLogin } = require('./fixtures/auth.js')

/**
 * API Key 管理 E2E 测试
 *
 * 覆盖设置页的密钥管理与 Agent 模型配置界面。
 * 连接测试会请求外部模型服务，这里只验证控件存在，不触发真实网络调用。
 */

async function openApiKeyTab(page) {
  await page.goto('/settings', { waitUntil: 'domcontentloaded' })
  await page.locator('#settings-tab-apikey').click()
  await expect(page.locator('.api-key-manager')).toBeVisible({ timeout: 15000 })
}

async function listKeyTokens(page) {
  return page.evaluate(async () => {
    const token = sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    const headers = { Authorization: `Bearer ${token}` }
    const listResp = await fetch('/api/v1/agent/apikeys', { credentials: 'include', headers })
    const keys = await listResp.json().catch(() => [])
    return (Array.isArray(keys) ? keys : []).map(key => key.token)
  })
}

async function ensureSiliconflowKeyInput(page) {
  const input = page.locator('[data-testid="siliconflow-key-input"]')
  const card = page.locator('.key-card.required-key')
  const clearButton = card.getByRole('button', { name: '清除' })

  // 上一次运行被中断时可能残留多个测试 Key，循环清除直到恢复未保存状态
  for (let i = 0; i < 10; i++) {
    if (await input.isVisible().catch(() => false)) return
    if (!(await clearButton.isVisible().catch(() => false))) break
    await clearButton.click()
    const dialog = page.getByRole('dialog', { name: '确认删除' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'OK' }).click()
    await expect(dialog).toBeHidden()
  }

  await expect(input).toBeVisible({ timeout: 15000 })
}

test.describe('API Key Management', () => {
  // 该账号的 Key 保存在后端 Redis，多个用例会互相删除对方的 Key，
  // 因此强制本文件串行执行，避免 fullyParallel 下的跨 worker 竞态。
  test.describe.configure({ mode: 'serial' })

  // 需按快照清理本次新增的 Key
  let baselineTokens = []

  test.beforeEach(async ({ page }) => {
    await apiLogin(page)
    await openApiKeyTab(page)
    await ensureSiliconflowKeyInput(page)
    baselineTokens = await listKeyTokens(page)
  })

  test.afterEach(async ({ page }) => {
    await page.evaluate(async (tokens) => {
      const token = sessionStorage.getItem('_token') || localStorage.getItem('access_token')
      const headers = { Authorization: `Bearer ${token}` }
      const listResp = await fetch('/api/v1/agent/apikeys', { credentials: 'include', headers })
      const keys = await listResp.json().catch(() => [])
      const created = (Array.isArray(keys) ? keys : [])
        .map(key => key.token)
        .filter(keyToken => !tokens.includes(keyToken))
      for (const keyToken of created) {
        await fetch(`/api/v1/agent/apikey/${keyToken}`, {
          method: 'DELETE',
          credentials: 'include',
          headers,
        })
      }
    }, baselineTokens).catch(() => {})
  })

  test('1. 设置页面加载正常', async ({ page }) => {
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.locator('#settings-tab-apikey')).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('#settings-tab-agent')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'API Key/接口密钥管理' })).toBeVisible()
  })

  test('2. 提交密钥时使用 RSA 公钥加密', async ({ page }) => {
    const publicKeyResponse = page.waitForResponse(
      resp => resp.url().includes('/api/v1/agent/apikey/public-key') && resp.status() === 200,
      { timeout: 15000 }
    )

    await page.locator('[data-testid="siliconflow-key-input"]').fill(`sk-e2e-${Date.now()}`)
    await page.locator('[data-testid="siliconflow-key-save"]').click()

    await publicKeyResponse
    await expect(page.locator('.key-card.required-key')).toContainText('主 Key/密钥')
    await expect(page.locator('.key-card.required-key')).toContainText('剩余')
    await expect(page.locator('.security-notice')).toContainText('RSA 加密传输')
  })

  test('3. 保存后展示测试连接与清除操作', async ({ page }) => {
    await page.locator('[data-testid="siliconflow-key-input"]').fill(`sk-e2e-${Date.now()}`)
    await page.locator('[data-testid="siliconflow-key-save"]').click()

    const requiredCard = page.locator('.key-card.required-key')
    await expect(requiredCard.getByRole('button', { name: '测试连接' })).toBeVisible()
    await expect(requiredCard.getByRole('button', { name: '清除' })).toBeVisible()
  })

  test('4. 清除密钥需要二次确认', async ({ page }) => {
    await page.locator('[data-testid="siliconflow-key-input"]').fill(`sk-e2e-${Date.now()}`)
    await page.locator('[data-testid="siliconflow-key-save"]').click()

    const requiredCard = page.locator('.key-card.required-key')
    await requiredCard.getByRole('button', { name: '清除' }).click()
    // Element Plus 默认语言包的确认按钮可访问名称为 OK
    const dialog = page.getByRole('dialog', { name: '确认删除' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('不可恢复')

    await dialog.getByRole('button', { name: 'OK' }).click()
    await expect(page.locator('[data-testid="siliconflow-key-input"]')).toBeVisible()
  })

  test('5. 供应商选择完整性', async ({ page }) => {
    const providerSelect = page.locator('.provider-select')
    await expect(providerSelect).toBeVisible()
    const providerNames = await providerSelect.locator('option').evaluateAll(
      options => options.map(option => option.value).filter(Boolean)
    )

    expect(providerNames).toEqual(
      expect.arrayContaining(['openai', 'anthropic', 'bailian', 'glm', 'deepseek'])
    )
  })

  test('6. TTL 选项完整性', async ({ page }) => {
    // 第二个 ttl-select 属于“其他供应商”表单，覆盖 1h 起的全部选项
    const ttlSelect = page.locator('.ttl-select').nth(1)
    const ttlValues = await ttlSelect.locator('option').evaluateAll(
      options => options.map(option => option.value).filter(Boolean)
    )

    expect(ttlValues).toEqual(
      expect.arrayContaining(['1h', '24h', '7d', '30d', 'never', 'custom'])
    )
  })

  test('7. Agent 环节配置显示', async ({ page }) => {
    await page.locator('#settings-tab-agent').click()
    await expect(page.locator('.agent-model-config')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.config-table tbody tr').first()).toBeVisible({ timeout: 15000 })

    const roleLabels = await page.locator('.role-badge').allInnerTexts()
    expect(roleLabels.map(label => label.trim())).toEqual(
      expect.arrayContaining(['架构师', '前端工程师', '后端工程师', '审查员', '兜底模型'])
    )
    await expect(page.getByRole('heading', { name: '降级链配置' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '错误类型模型映射' })).toBeVisible()
  })

  test('8. 模型配置覆盖全部角色', async ({ page }) => {
    await page.locator('#settings-tab-agent').click()
    const table = page.locator('.config-table')
    await expect(table).toBeVisible({ timeout: 15000 })

    const rows = table.locator('tbody tr')
    await expect(rows).toHaveCount(5)
    for (let i = 0; i < 5; i++) {
      await expect(rows.nth(i).locator('.role-cell')).not.toBeEmpty()
      await expect(rows.nth(i).locator('.model-cell')).not.toBeEmpty()
    }
  })

  test('9. 本地存储不保存明文密钥', async ({ page }) => {
    await page.locator('[data-testid="siliconflow-key-input"]').fill('sk-e2e-plaintext-check')
    await page.locator('[data-testid="siliconflow-key-save"]').click()
    await expect(page.locator('.key-card.required-key')).toContainText('主 Key/密钥')

    const stored = await page.evaluate(() => localStorage.getItem('codingmatrix_apikeys') || '')
    expect(stored).not.toContain('sk-e2e-plaintext-check')
  })
})
