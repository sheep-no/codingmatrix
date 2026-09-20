// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WebSocketManager } from './websocket'

class FakeWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static CLOSED = 3

  constructor(url) {
    this.url = url
    this.readyState = FakeWebSocket.CONNECTING
    FakeWebSocket.instances.push(this)
  }

  send() {}

  close() {
    this.readyState = FakeWebSocket.CLOSED
    if (this.onclose) this.onclose({ code: 1000 })
  }

  emitOpen() {
    this.readyState = FakeWebSocket.OPEN
    if (this.onopen) this.onopen()
  }
}

describe('WebSocketManager 重连与手动断开', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('重连时复用首次连接传入的 token', async () => {
    const manager = new WebSocketManager('ws://example.test/api/v2/Controller/logs?token={token}')

    const first = manager.connect('secret-token')
    FakeWebSocket.instances[0].emitOpen()
    await first
    expect(FakeWebSocket.instances[0].url).toContain('token=secret-token')

    // 网络断开：触发自动重连
    FakeWebSocket.instances[0].onclose({ code: 1006 })
    vi.advanceTimersByTime(3000)

    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1].url).toContain('token=secret-token')
    expect(FakeWebSocket.instances[1].url).not.toContain('{token}')
  })

  it('主动 disconnect 后不再自动重连', async () => {
    const manager = new WebSocketManager('ws://example.test/api/v2/Controller/logs?token={token}')

    const connected = manager.connect('secret-token')
    FakeWebSocket.instances[0].emitOpen()
    await connected

    manager.disconnect()
    vi.advanceTimersByTime(30000)

    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
