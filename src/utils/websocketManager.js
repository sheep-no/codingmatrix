/**
 * WebSocket 管理器
 * 用于处理系统状态和日志的实时推送
 */

import { API_CONFIG } from './api/config.js'

export class WebSocketManager {
  constructor() {
    this.baseUrl = API_CONFIG.WS_BASE_URL
    this.connections = new Map()
    this.reconnectAttempts = new Map()
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 3000
  }

  /**
   * 连接到系统状态 WebSocket
   * @param {string} token - JWT token
   * @param {function} onMessage - 消息回调
   * @param {function} onError - 错误回调
   * @param {function} onOpen - 连接成功回调
   * @param {function} onClose - 连接关闭回调
   * @returns {WebSocket} WebSocket 实例
   */
  connectSysStatus(token, onMessage, onError, onOpen = null, onClose = null) {
    return this.connect('/Controller/sys-status', token, onMessage, onError, onOpen, onClose)
  }

  /**
   * 连接到日志 WebSocket
   * @param {string} token - JWT token
   * @param {function} onMessage - 消息回调
   * @param {function} onError - 错误回调
   * @param {function} onOpen - 连接成功回调
   * @param {function} onClose - 连接关闭回调
   * @returns {WebSocket} WebSocket 实例
   */
  connectLogs(token, onMessage, onError, onOpen = null, onClose = null) {
    return this.connect('/Controller/logs', token, onMessage, onError, onOpen, onClose)
  }

  /**
   * 通用连接方法
   * @param {string} endpoint - WebSocket 端点
   * @param {string} token - JWT token
   * @param {function} onMessage - 消息回调
   * @param {function} onError - 错误回调
   * @param {function} onOpen - 连接成功回调
   * @param {function} onClose - 连接关闭回调
   * @returns {WebSocket} WebSocket 实例
   */
  connect(endpoint, token, onMessage, onError, onOpen = null, onClose = null) {
    const connectionId = endpoint
    const wsUrl = `${this.baseUrl}${endpoint}?token=${encodeURIComponent(token)}`

    console.log(`[API] 尝试连接 WebSocket: ${wsUrl}`)

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log(`[SUCCESS] WebSocket connected: ${endpoint}`)
      this.reconnectAttempts.delete(connectionId)
      this.connections.set(connectionId, ws)
      if (onOpen) onOpen(ws)
    }

    ws.onmessage = event => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch (error) {
        console.error('WebSocket 消息解析失败:', error, event.data)
        onMessage(event.data)
      }
    }

    ws.onerror = error => {
      console.error(`[ERR] WebSocket error: ${endpoint}`, error)
      onError(error)
    }

    ws.onclose = event => {
      console.log(`[CLOSE] WebSocket closed: ${endpoint}`, event.code, event.reason)
      this.connections.delete(connectionId)
      if (onClose) onClose(event)

      // 自动重连（如果是非正常关闭）
      if (event.code !== 1000 && !this.isManuallyClosed(connectionId)) {
        this.attemptReconnect(endpoint, token, onMessage, onError, onOpen, onClose)
      }
    }

    return ws
  }

  /**
   * 尝试重连
   */
  attemptReconnect(endpoint, token, onMessage, onError, onOpen, onClose) {
    const connectionId = endpoint
    const attempts = this.reconnectAttempts.get(connectionId) || 0

    if (attempts >= this.maxReconnectAttempts) {
      console.error(`WebSocket 重连次数超限 (${this.maxReconnectAttempts})，停止重连：${endpoint}`)
      this.reconnectAttempts.delete(connectionId)
      return
    }

    const delay = this.reconnectDelay * Math.pow(2, attempts)
    console.log(
      `WebSocket 将在 ${delay}ms 后重连（第 ${attempts + 1}/${this.maxReconnectAttempts} 次尝试）`
    )

    this.reconnectAttempts.set(connectionId, attempts + 1)

    setTimeout(() => {
      this.connect(endpoint, token, onMessage, onError, onOpen, onClose)
    }, delay)
  }

  /**
   * 断开连接
   * @param {WebSocket} ws - WebSocket 实例
   * @param {string} connectionId - 连接 ID
   */
  disconnect(ws, connectionId = null) {
    if (connectionId) {
      this.setManuallyClosed(connectionId)
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close(1000, 'Manual disconnect')
      console.log('WebSocket 已手动断开')
    }

    // 清除重连计数
    if (connectionId) {
      this.reconnectAttempts.delete(connectionId)
    }
  }

  /**
   * 断开所有连接
   */
  disconnectAll() {
    this.connections.forEach((ws, connectionId) => {
      this.setManuallyClosed(connectionId)
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, 'Manual disconnect all')
      }
    })
    this.connections.clear()
    this.reconnectAttempts.clear()
    console.log('所有 WebSocket 连接已断开')
  }

  /**
   * 获取连接状态
   * @param {string} connectionId - 连接 ID
   * @returns {boolean} 是否已连接
   */
  isConnected(connectionId) {
    const ws = this.connections.get(connectionId)
    return ws && ws.readyState === WebSocket.OPEN
  }

  /**
   * 获取所有连接状态
   * @returns {Object} 连接状态对象
   */
  getAllConnectionsStatus() {
    const status = {}
    this.connections.forEach((ws, connectionId) => {
      status[connectionId] = {
        connected: ws.readyState === WebSocket.OPEN,
        readyState: ws.readyState,
        url: ws.url
      }
    })
    return status
  }

  /**
   * 发送消息
   * @param {WebSocket} ws - WebSocket 实例
   * @param {any} data - 消息数据
   */
  send(ws, data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    } else {
      console.warn('WebSocket 未连接，无法发送消息')
    }
  }

  // 私有方法：标记为手动关闭（阻止自动重连）
  setManuallyClosed(connectionId) {
    sessionStorage.setItem(`ws_manual_close:${connectionId}`, 'true')
  }

  // 私有方法：检查是否手动关闭
  isManuallyClosed(connectionId) {
    const closed = sessionStorage.getItem(`ws_manual_close:${connectionId}`) === 'true'
    if (closed) {
      sessionStorage.removeItem(`ws_manual_close:${connectionId}`)
    }
    return closed
  }
}

// 创建单例实例
export const wsManager = new WebSocketManager()
export default wsManager
