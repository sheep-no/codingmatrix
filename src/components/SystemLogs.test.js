import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/api/index', () => ({
  API_CONFIG: { WS_BASE_URL: 'ws://localhost:8000' },
  WebSocketManager: class {
    connect() {
      return Promise.resolve()
    }
    disconnect() {}
    scheduleReconnect() {}
    isReady() {
      return false
    }
    send() {}
  },
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ getAccessToken: () => 'test-token' }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}))

import SystemLogs from './SystemLogs.vue'
import { useLogsStore } from '@/stores/logs'

describe('SystemLogs 自动保存', () => {
  let pinia

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.clear()
  })

  it('store 日志变化时写入 localStorage（FESTATE-03）', async () => {
    mount(SystemLogs, { global: { plugins: [pinia] } })
    const logsStore = useLogsStore()

    logsStore.addLog({ id: 'log-1', level: 'info', message: 'hello-watcher' })
    await nextTick()
    await nextTick()

    const saved = JSON.parse(localStorage.getItem('systemLogsState') || '{}')
    expect(
      (saved.systemLogs || []).some((entry) => entry.message === 'hello-watcher'),
    ).toBe(true)
  })
})
