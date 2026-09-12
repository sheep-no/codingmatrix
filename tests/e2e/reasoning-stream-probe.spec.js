import { test, expect } from '@playwright/test'
import fs from 'node:fs'

const EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin_test@example.com'
const PASSWORD = process.env.TEST_ADMIN_PASSWORD || '12345678'
const DUMP = '/tmp/reasoning-stream-probe.json'

async function loginAndSeedKeys(page) {
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
    const keysResp = await fetch('/api/v1/agent/apikeys', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${data.access_token}` },
    })
    const keys = await keysResp.json().catch(() => [])
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify(Array.isArray(keys) ? keys : []))
    return { ok: true, keyCount: Array.isArray(keys) ? keys.length : 0 }
  }, { email: EMAIL, password: PASSWORD })
  expect(login.ok, JSON.stringify(login)).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
}

test('深度思考流式实测：抓请求/响应/页面', async ({ page }) => {
  test.setTimeout(180000)
  await loginAndSeedKeys(page)

  await page.locator('button.config-toggle').click()
  const reasoning = page.locator('label.config-item', { hasText: '深度思考' }).locator('input[type="checkbox"]')
  await expect(reasoning).toBeVisible()
  await reasoning.check()
  await expect(page.locator('.composer-summary')).toContainText('深度思考')

  const streamProbe = await page.evaluate(async () => {
    const token = sessionStorage.getItem('_token') || localStorage.getItem('access_token')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 90000)
    const started = Date.now()
    const result = {
      status: 0,
      contentType: '',
      firstByteMs: null,
      elapsedMs: 0,
      aborted: false,
      raw: '',
      lineCount: 0,
      reasoningChunks: 0,
      contentChunks: 0,
      reasoningSample: '',
      contentSample: '',
      eventTypes: [],
      error: '',
    }
    try {
      const resp = await fetch('/api/v1/chat', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt: '用一句话解释什么是质数，先思考再回答。',
          stream: true,
          use_reasoning: true,
          search_mode: 'off',
          api_key_token: (JSON.parse(localStorage.getItem('codingmatrix_apikeys') || '[]').find((k) => k.provider === 'siliconflow') || {}).token,
        }),
        signal: controller.signal,
      })
      result.status = resp.status
      result.contentType = resp.headers.get('content-type') || ''
      if (!resp.body) {
        result.error = 'no body'
        return result
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        if (result.firstByteMs === null) result.firstByteMs = Date.now() - started
        result.raw += decoder.decode(value, { stream: true })
        const preview = result.raw
        if (/"reasoning_content"\s*:\s*"[^"]/.test(preview) || /"content"\s*:\s*"[^"]/.test(preview)) break
        if (preview.length >= 12000) break
      }
    } catch (error) {
      result.aborted = error?.name === 'AbortError'
      result.error = String(error?.message || error)
    } finally {
      clearTimeout(timer)
      controller.abort()
      result.elapsedMs = Date.now() - started
    }

    const lines = result.raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
    result.lineCount = lines.length
    for (const line of lines) {
      const payload = line.startsWith('data:') ? line.slice(5).trim() : line
      let data
      try {
        data = JSON.parse(payload)
      } catch {
        result.eventTypes.push('unparsed')
        continue
      }
      if (data.stage) result.eventTypes.push(`stage:${data.stage}:${data.status || ''}`)
      else if (data.conversation_id !== undefined) result.eventTypes.push('conversation_id')
      else if (data.error) result.eventTypes.push(`error:${String(data.error).slice(0, 80)}`)
      else if (data.choices) result.eventTypes.push('choices')
      else result.eventTypes.push(`keys:${Object.keys(data).join(',')}`)
      const delta = data.choices?.[0]?.delta || {}
      if (delta.reasoning_content) {
        result.reasoningChunks += 1
        if (result.reasoningSample.length < 400) result.reasoningSample += delta.reasoning_content
      }
      if (delta.content) {
        result.contentChunks += 1
        if (result.contentSample.length < 400) result.contentSample += delta.content
      }
    }
    result.rawPreview = result.raw.slice(0, 2500)
    delete result.raw
    return result
  })

  const textarea = page.locator('textarea.chat-input')
  await expect(textarea).toBeVisible()
  await textarea.fill('1+1等于几？先思考再给出答案。')
  await textarea.press('Control+Enter')
  await expect(page.locator('.thinking-section')).toBeVisible({ timeout: 90000 })
  await expect.poll(
    async () => ((await page.locator('.thinking-content').innerText().catch(() => '')) || '').trim().length,
    { timeout: 60000 },
  ).toBeGreaterThan(10)
  const ui = await page.evaluate(() => ({
    thinkingVisible: !!document.querySelector('.thinking-section'),
    thinkingText: (document.querySelector('.thinking-content')?.innerText || '').slice(0, 400),
    aiHtml: (document.querySelector('.message-ai')?.innerText || '').slice(0, 600),
    userText: (document.querySelector('.message-user')?.innerText || '').slice(0, 200),
    composer: document.querySelector('.composer-summary')?.innerText || '',
    streaming: !!document.querySelector('.message-ai.streaming'),
  }))

  const probe = { streamProbe, ui }
  fs.writeFileSync(DUMP, JSON.stringify(probe, null, 2))
  expect(streamProbe.status, JSON.stringify(probe, null, 2)).toBe(200)
  expect(
    streamProbe.reasoningChunks + streamProbe.contentChunks,
    JSON.stringify(probe, null, 2),
  ).toBeGreaterThan(0)
  expect(ui.thinkingVisible, JSON.stringify(probe, null, 2)).toBeTruthy()
  expect(ui.thinkingText.length, JSON.stringify(probe, null, 2)).toBeGreaterThan(10)
})
