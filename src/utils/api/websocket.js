/**
 * API WebSocket 管理器
 */
import { API_CONFIG } from './config'

const WS_CONFIG = {
  RECONNECT_INTERVAL: 3000,
  MAX_RECONNECT_ATTEMPTS: 5,
  HEARTBEAT_INTERVAL: 30000
}

// 后端真实 WS 端点（v1 + v2）：
//   v1: /api/v1/tasks/ws/{user_id}                       - 任务状态推送（普通用户）
//   v2: /api/v2/Controller/sys-status?token=xxx          - 系统状态推送（管理员）
//   v2: /api/v2/Controller/logs?token=xxx                - 系统日志推送（管理员）
//   v2: /api/v2/Controller/admin/ws-stats                - 管理员统计
// 修复 P0-6：原默认 `${WS_BASE_URL}/ws` 是死路径，ws 路由不存在，后端拒绝（403）。
// 改用最常见的 v2 sys-status 端点作为默认；调用方仍可传 wsUrl 覆盖。
const DEFAULT_WS_URL = `${API_CONFIG.WS_BASE_URL}/api/v2/Controller/sys-status?token={token}`

export class WebSocketManager {
  constructor(configOrUrl = null) {
    if (typeof configOrUrl === 'object' && configOrUrl !== null) {
      this.url = configOrUrl.wsUrl || DEFAULT_WS_URL
      this._onOpen = configOrUrl.onOpen || null
      this._onMessage = configOrUrl.onMessage || null
      this._onError = configOrUrl.onError || null
      this._onClose = configOrUrl.onClose || null
      this._reconnectDelay = configOrUrl.reconnectDelay || WS_CONFIG.RECONNECT_INTERVAL
    } else {
      this.url = configOrUrl || DEFAULT_WS_URL
      this._onOpen = null
      this._onMessage = null
      this._onError = null
      this._onClose = null
      this._reconnectDelay = WS_CONFIG.RECONNECT_INTERVAL
    }
    this.ws = null
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = WS_CONFIG.MAX_RECONNECT_ATTEMPTS
    this.reconnectTimer = null
    this.heartbeatTimer = null
    this.listeners = new Map()
    this.isConnected = false
  }

  connect(token = null) {
    return new Promise((resolve, reject) => {
      try {
        let fullUrl = this.url
        if (token) {
          // 修复：{token} 占位符要替换成真实 token，而不是置空
          fullUrl = fullUrl.replace(/\{token\}/g, encodeURIComponent(token))
        } else {
          // 没传 token 时清掉占位符；如果剥掉了 ? 形式则把紧跟的 & 升为 ?
          fullUrl = fullUrl.replace(/\?token=\{token\}(&|$)/, (m, tail) => tail === '&' ? '?' : '')
          fullUrl = fullUrl.replace(/&token=\{token\}(?=&|$)/, '')
        }
        this.ws = new WebSocket(fullUrl)

        this.ws.onopen = () => {
          this.isConnected = true
          this.reconnectAttempts = 0
          this.startHeartbeat()
          this.emit('open', {})
          if (this._onOpen) this._onOpen()
          resolve()
        }

        this.ws.onmessage = event => {
          try {
            const data = JSON.parse(event.data)
            this.emit('message', data)
          } catch (e) {
            this.emit('message', event.data)
          }
          if (this._onMessage) this._onMessage(event)
        }

        this.ws.onerror = error => {
          this.emit('error', error)
          if (this._onError) this._onError(error)
          reject(error)
        }

        this.ws.onclose = event => {
          this.isConnected = false
          this.stopHeartbeat()
          this.emit('close', event)
          if (this._onClose) this._onClose(event)
          this.attemptReconnect()
        }
      } catch (error) {
        reject(error)
      }
    })
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.stopHeartbeat()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.isConnected = false
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      if (typeof data === 'object') {
        this.ws.send(JSON.stringify(data))
      } else {
        this.ws.send(data)
      }
      return true
    }
    return false
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, [])
    }
    this.listeners.get(event).push(callback)
  }

  off(event, callback) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event)
      const index = callbacks.indexOf(callback)
      if (index > -1) {
        callbacks.splice(index, 1)
      }
    }
  }

  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(callback => callback(data))
    }
  }

  isReady() {
    return this.ws && this.ws.readyState === WebSocket.OPEN
  }

  scheduleReconnect() {
    this.attemptReconnect()
  }

  attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.emit('reconnect_failed', { attempts: this.reconnectAttempts })
      return
    }

    this.reconnectAttempts++
    this.emit('reconnecting', { attempts: this.reconnectAttempts })

    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(() => {
        // reconnect handled in onclose
      })
    }, this._reconnectDelay)
  }

  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping' })
    }, WS_CONFIG.HEARTBEAT_INTERVAL)
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }
}

export default { WebSocketManager }
