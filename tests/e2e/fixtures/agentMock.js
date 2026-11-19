/**
 * Agent 工作台 E2E 公共桩
 *
 * 本地种子 Key 只用于通过前端“必须配置 Key”的守卫；
 * 真正的模型调用由 page.route 拦截，避免消耗真实额度。
 */

export const MOCK_KEYS = [{
  token: 'e2e-mock-siliconflow-token',
  provider: 'siliconflow',
  remark: 'E2E Mock Key',
  status: 'verified',
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
  ttl_seconds: 86400,
  enabled: true,
}]

export async function seedMockKeys(page, keys = MOCK_KEYS) {
  await page.addInitScript(items => {
    localStorage.setItem('codingmatrix_apikeys', JSON.stringify(items))
  }, keys)
}

export function sseBody(events) {
  return events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
}

export async function mockProjectStream(page, events, onRequest) {
  await page.route('**/api/v1/agent/orchestrate/stream', async route => {
    const request = route.request()
    if (onRequest) onRequest(request)
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: sseBody(events),
    })
  })
}

export async function mockModelContext(page) {
  await page.route('**/api/v1/agent/sessions/*/model-context', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ context: { config_version: '', roles: {}, assignments: {} }, revision: 1 }),
  }))
}

export function fileEvent(path, content = '// e2e') {
  return {
    type: 'file',
    path,
    content,
    line_count: content.split('\n').length,
    file_size: Buffer.byteLength(content),
    file_size_human: `${Buffer.byteLength(content)} B`,
  }
}

export function progressEvent(phase, step, percentage) {
  return { type: 'progress', data: { phase, step, percentage } }
}

export function doneEvent(projectPath = 'e2e-project') {
  return { type: 'done', data: { project_path: projectPath } }
}
