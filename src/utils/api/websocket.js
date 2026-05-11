/**
 * API WebSocket 管理器
 */
import { API_CONFIG } from './config'

const WS_CONFIG = {
  RECONNECT_INTERVAL: 3000,
  MAX_RECONNECT_ATTEMPTS: 5,
  HEARTBEAT_INTERVAL: 30000
}

export class WebSocketManager {
  constructor(url = null) {
    this.url = url || `${API_CONFIG.WS_BASE_URL}/ws`
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
        const fullUrl = token ? `${this.url}?token=${token}` : this.url
        this.ws = new WebSocket(fullUrl)

        this.ws.onopen = () => {
          this.isConnected = true
          this.reconnectAttempts = 0
          this.startHeartbeat()
          this.emit('open', {})
          resolve()
        }

        this.ws.onmessage = event => {
          try {
            const data = JSON.parse(event.data)
            this.emit('message', data)
          } catch (e) {
            this.emit('message', event.data)
          }
        }

        this.ws.onerror = error => {
          this.emit('error', error)
          reject(error)
        }

        this.ws.onclose = () => {
          this.isConnected = false
          this.stopHeartbeat()
          this.emit('close', {})
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
    }, WS_CONFIG.RECONNECT_INTERVAL)
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
