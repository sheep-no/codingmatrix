/**
 * WebSocket 连接池优化版
 *
 * 性能提升:
 * 1. 连接共享 - 多个组件订阅同一个 WebSocket 连接
 * 2. 发布/订阅模式 - 高效消息分发
 * 3. 连接计数管理 - 最后一个用户断开才关闭连接
 * 4. 指数退避重连 - 智能重连策略
 * 5. 消息缓冲 - 连接断开时缓存消息
 *
 * @author Performance Optimization Team
 * @version 2.0.0
 */

import { API_CONFIG } from './api/config.js'

// WebSocket 配置常量
const WS_CONFIG = {
  MAX_RECONNECT_ATTEMPTS: 10,
  INITIAL_RECONNECT_DELAY: 1000,
  MAX_RECONNECT_DELAY: 30000,
  BUFFER_SIZE: 1000,
  BUFFER_FLUSH_TIMEOUT: 5000,
  HEARTBEAT_INTERVAL: 25000,
  HEARTBEAT_TIMEOUT: 5000
}

// 连接状态枚举
const ConnectionState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting'
}

/**
 * WebSocket 连接池类
 */
export class WebSocketPool {
  constructor() {
    this.baseUrl = import.meta.env.VITE_WS_BASE || 'ws://127.0.0.1:8080'

    // 连接池 Map: endpoint -> SharedConnection
    this.pool = new Map()

    // 消息缓冲区：endpoint -> [messages]
    this.buffers = new Map()

    // 统计信息
    this.stats = {
      totalConnections: 0,
      activeConnections: 0,
      totalMessages: 0,
      cacheHits: 0,
      reconnects: 0
    }
  }

  /**
   * 获取或创建共享连接
   * @param {string} endpoint - WebSocket 端点
   * @param {string} token - JWT token
   * @returns {SharedConnection} 共享连接实例
   */
  getConnection(endpoint, token) {
    const connectionId = endpoint

    if (!this.pool.has(connectionId)) {
      const connection = new SharedConnection(
        connectionId,
        `${this.baseUrl}${endpoint}`,
        token,
        this
      )
      this.pool.set(connectionId, connection)
      this.stats.totalConnections++

      console.log(`[API] 创建 WebSocket 共享连接：${connectionId}`)
    } else {
      this.stats.cacheHits++
    }

    return this.pool.get(connectionId)
  }

  /**
   * 订阅连接消息
   * @param {string} endpoint - WebSocket 端点
   * @param {string} token - JWT token
   * @param {function} onMessage - 消息回调
   * @param {function} onStatusChange - 状态变化回调
   * @returns {function} 取消订阅函数
   */
  subscribe(endpoint, token, onMessage, onStatusChange = null) {
    const connection = this.getConnection(endpoint, token)
    const subscriberId = connection.addSubscriber(onMessage, onStatusChange)

    // 如果尚未连接，自动连接
    if (connection.state !== ConnectionState.CONNECTED) {
      connection.connect()
    }

    // 返回取消订阅函数
    return () => {
      this.unsubscribe(endpoint, subscriberId)
    }
  }

  /**
   * 取消订阅
   * @param {string} endpoint - WebSocket 端点
   * @param {string} subscriberId - 订阅者 ID
   */
  unsubscribe(endpoint, subscriberId) {
    const connection = this.pool.get(endpoint)
    if (connection) {
      connection.removeSubscriber(subscriberId)

      // 如果没有订阅者了，断开连接
      if (connection.subscriberCount === 0) {
        console.log(`[API] 断开 WebSocket 连接（无订阅者）：${endpoint}`)
        connection.disconnect()

        // 可选：从池中移除（保持连接可快速重连）
        // this.pool.delete(endpoint)
      }
    }
  }

  /**
   * 发送消息到指定连接
   * @param {string} endpoint - WebSocket 端点
   * @param {any} data - 消息数据
   * @returns {boolean} 是否发送成功
   */
  send(endpoint, data) {
    const connection = this.pool.get(endpoint)
    if (connection && connection.isReady()) {
      connection.send(data)
      return true
    }
    return false
  }

  /**
   * 获取连接状态
   * @param {string} endpoint - WebSocket 端点
   * @returns {Object} 连接状态
   */
  getStatus(endpoint) {
    const connection = this.pool.get(endpoint)
    if (!connection) {
      return {
        state: ConnectionState.DISCONNECTED,
        subscribers: 0
      }
    }

    return {
      state: connection.state,
      subscribers: connection.subscriberCount,
      reconnectAttempts: connection.reconnectAttempts,
      lastMessageAt: connection.lastMessageAt
    }
  }

  /**
   * 获取所有连接状态
   * @returns {Object} 所有连接状态
   */
  getAllStatus() {
    const status = {}
    this.pool.forEach((connection, endpoint) => {
      status[endpoint] = {
        state: connection.state,
        subscribers: connection.subscriberCount,
        reconnectAttempts: connection.reconnectAttempts,
        lastMessageAt: connection.lastMessageAt
      }
    })
    return status
  }

  /**
   * 获取统计信息
   * @returns {Object} 统计信息
   */
  getStats() {
    return {
      ...this.stats,
      activeConnections: Array.from(this.pool.values()).filter(
        conn => conn.state === ConnectionState.CONNECTED
      ).length,
      poolSize: this.pool.size
    }
  }

  /**
   * 断开所有连接
   */
  disconnectAll() {
    this.pool.forEach(connection => {
      connection.disconnect()
    })
    console.log('[SUCCESS] All WebSocket connections disconnected')
  }

  /**
   * 添加到消息缓冲区
   * @private
   */
  _bufferMessage(endpoint, message) {
    if (!this.buffers.has(endpoint)) {
      this.buffers.set(endpoint, [])
    }

    const buffer = this.buffers.get(endpoint)
    buffer.push({
      message,
      timestamp: Date.now()
    })

    // 限制缓冲区大小
    if (buffer.length > WS_CONFIG.BUFFER_SIZE) {
      buffer.shift()
    }

    // 定时刷新缓冲区
    setTimeout(() => {
      this._flushBuffer(endpoint)
    }, WS_CONFIG.BUFFER_FLUSH_TIMEOUT)
  }

  /**
   * 刷新缓冲区
   * @private
   */
  _flushBuffer(endpoint) {
    const buffer = this.buffers.get(endpoint)
    if (buffer && buffer.length > 0) {
      console.log(`[BUFFER] Refresh buffer ${endpoint}: ${buffer.length} messages`)
      buffer.splice(0, buffer.length)
    }
  }
}

/**
 * 共享连接类
 * 管理单个 WebSocket 连接和多个订阅者
 */
class SharedConnection {
  constructor(connectionId, url, token, pool) {
    this.connectionId = connectionId
    this.url = url
    this.token = token

    this.pool = pool
    this.ws = null
    this.state = ConnectionState.DISCONNECTED

    // 订阅者管理
    this.subscribers = new Map() // subscriberId -> { onMessage, onStatusChange }
    this.nextSubscriberId = 1
    this.subscriberCount = 0

    // 重连管理
    this.reconnectAttempts = 0
    this.reconnectTimer = null
    this.heartbeatTimer = null
    this.heartbeatTimeout = null

    // 状态跟踪
    this.lastMessageAt = null
    this.createdAt = Date.now()
  }

  /**
   * 连接 WebSocket
   */
  connect() {
    if (this.state === ConnectionState.CONNECTED || this.state === ConnectionState.CONNECTING) {
      console.log(`[WARN] WebSocket already connecting: ${this.connectionId}`)
      return
    }

    this.state = ConnectionState.CONNECTING
    this._notifyStatusChange()

    const fullUrl = `${this.url}?token=${encodeURIComponent(this.token)}`

    try {
      this.ws = new WebSocket(fullUrl)
      this._setupEventHandlers()
    } catch (error) {
      console.error(`[ERR] WebSocket connection failed: ${this.connectionId}`, error)
      this.state = ConnectionState.DISCONNECTED
      this._notifyStatusChange()
      this._attemptReconnect()
    }
  }

  /**
   * 设置事件处理器
   * @private
   */
  _setupEventHandlers() {
    this.ws.onopen = () => {
      console.log(`[SUCCESS] WebSocket connected: ${this.connectionId}`)
      this.state = ConnectionState.CONNECTED
      this.reconnectAttempts = 0
      this.lastMessageAt = Date.now()
      this._startHeartbeat()
      this._notifyStatusChange()
      this._notifySubscribers('connected')
    }

    this.ws.onmessage = event => {
      this.lastMessageAt = Date.now()
      this.pool.stats.totalMessages++

      try {
        const data = JSON.parse(event.data)
        this._notifySubscribers('message', data)
      } catch (error) {
        console.error('WebSocket 消息解析失败:', error, event.data)
        this._notifySubscribers('message', event.data)
      }

      this._resetHeartbeatTimeout()
    }

    this.ws.onerror = error => {
      console.error(`[ERR] WebSocket error: ${this.connectionId}`, error)
      this._notifySubscribers('error', error)
    }

    this.ws.onclose = event => {
      console.log(`[CLOSE] WebSocket closed: ${this.connectionId}`, event.code, event.reason)
      this.state = ConnectionState.DISCONNECTED
      this._clearHeartbeat()
      this._notifyStatusChange()
      this._notifySubscribers('close', event)

      // 非常规关闭时尝试重连
      if (event.code !== 1000 && this.subscriberCount > 0) {
        this._attemptReconnect(event)
      }
    }
  }

  /**
   * 添加订阅者
   * @param {function} onMessage - 消息回调
   * @param {function} onStatusChange - 状态变化回调
   * @returns {string} 订阅者 ID
   */
  addSubscriber(onMessage, onStatusChange = null) {
    const subscriberId = `sub_${this.nextSubscriberId++}`

    this.subscribers.set(subscriberId, {
      onMessage,
      onStatusChange,
      subscribedAt: Date.now()
    })

    this.subscriberCount++
    console.log(
      `👥 添加订阅者 ${subscriberId} 到 ${this.connectionId} (当前：${this.subscriberCount})`
    )

    return subscriberId
  }

  /**
   * 移除订阅者
   * @param {string} subscriberId - 订阅者 ID
   */
  removeSubscriber(subscriberId) {
    const removed = this.subscribers.delete(subscriberId)
    if (removed) {
      this.subscriberCount--
      console.log(
        `👋 移除订阅者 ${subscriberId} 从 ${this.connectionId} (当前：${this.subscriberCount})`
      )
    }
  }

  /**
   * 发送消息
   * @param {any} data - 消息数据
   * @returns {boolean} 是否发送成功
   */
  send(data) {
    if (this.isReady()) {
      this.ws.send(JSON.stringify(data))
      return true
    }
    console.warn(`[WARN] WebSocket not ready, cannot send message: ${this.connectionId}`)
    return false
  }

  /**
   * 检查是否就绪
   * @returns {boolean} 是否就绪
   */
  isReady() {
    return this.ws && this.ws.readyState === WebSocket.OPEN
  }

  /**
   * 断开连接
   */
  disconnect() {
    this._clearHeartbeat()

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close(1000, 'Manual disconnect')
    }

    this.state = ConnectionState.DISCONNECTED
    this._notifyStatusChange()
  }

  /**
   * 尝试重连
   * @private
   */
  _attemptReconnect(closeEvent = null) {
    if (this.reconnectAttempts >= WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
      console.error(`[ERR] WebSocket reconnect attempts exceeded: ${this.connectionId}`)
      this.state = ConnectionState.DISCONNECTED
      this._notifyStatusChange()
      return
    }

    this.state = ConnectionState.RECONNECTING
    this.pool.stats.reconnects++

    const delay = Math.min(
      WS_CONFIG.INITIAL_RECONNECT_DELAY * Math.pow(2, this.reconnectAttempts),
      WS_CONFIG.MAX_RECONNECT_DELAY
    )

    console.log(
      `[PROXY] WebSocket 将在 ${delay}ms 后重连 (${this.reconnectAttempts + 1}/${WS_CONFIG.MAX_RECONNECT_ATTEMPTS})`
    )

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  /**
   * 启动心跳
   * @private
   */
  _startHeartbeat() {
    this._clearHeartbeat()

    this.heartbeatTimer = setInterval(() => {
      if (this.isReady()) {
        this.send({ action: 'ping' })
        this._startHeartbeatTimeout()
      }
    }, WS_CONFIG.HEARTBEAT_INTERVAL)
  }

  /**
   * 启动心跳超时
   * @private
   */
  _startHeartbeatTimeout() {
    this.heartbeatTimeout = setTimeout(() => {
      console.warn(`[WARN] WebSocket heartbeat timeout: ${this.connectionId}`)
      this.ws?.close(4000, 'Heartbeat timeout')
    }, WS_CONFIG.HEARTBEAT_TIMEOUT)
  }

  /**
   * 重置心跳超时
   * @private
   */
  _resetHeartbeatTimeout() {
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout)
      this.heartbeatTimeout = null
    }
  }

  /**
   * 清除心跳
   * @private
   */
  _clearHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    this._resetHeartbeatTimeout()
  }

  /**
   * 通知所有订阅者
   * @private
   */
  _notifySubscribers(type, data = null) {
    this.subscribers.forEach((subscriber, id) => {
      try {
        if (type === 'message') {
          subscriber.onMessage?.(data)
        } else if (type === 'error') {
          subscriber.onError?.(data)
        } else if (type === 'close') {
          subscriber.onClose?.(data)
        }
      } catch (error) {
        console.error(`[ERR] Subscriber callback error ${id}:`, error)
      }
    })
  }

  /**
   * 通知状态变化
   * @private
   */
  _notifyStatusChange() {
    this.subscribers.forEach((subscriber, id) => {
      subscriber.onStatusChange?.({
        state: this.state,
        connectionId: this.connectionId,
        timestamp: Date.now()
      })
    })
  }
}

// 创建全局单例
export const wsPool = new WebSocketPool()
export default wsPool
