<template>
  <div v-if="visible" class="system-monitor-overlay" @click.self="handleClose">
    <div class="system-monitor-container">
      <div class="monitor-header">
        <h2>
          <span class="icon">🔐</span>
          系统监控
        </h2>
        <button class="close-btn" @click="handleClose">×</button>
      </div>

      <div class="monitor-content">
        <!-- 连接状态 -->
        <div class="connection-status">
          <span
            :class="['status-dot', { connected: isConnected, disconnected: !isConnected }]"
          ></span>
          <span class="status-text">{{ isConnected ? '已连接' : '连接中...' }}</span>
          <span v-if="lastUpdate" class="last-update">更新时间: {{ lastUpdate }}</span>
        </div>

        <!-- CPU 信息 -->
        <div class="stat-card cpu-card">
          <div class="card-header">
            <span class="card-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
                <rect x="4" y="4" width="16" height="16" rx="2"></rect>
                <rect x="9" y="9" width="6" height="6"></rect>
                <line x1="9" y1="1" x2="9" y2="4"></line>
                <line x1="15" y1="1" x2="15" y2="4"></line>
                <line x1="9" y1="20" x2="9" y2="23"></line>
                <line x1="15" y1="20" x2="15" y2="23"></line>
                <line x1="20" y1="9" x2="23" y2="9"></line>
                <line x1="20" y1="14" x2="23" y2="14"></line>
                <line x1="1" y1="9" x2="4" y2="9"></line>
                <line x1="1" y1="14" x2="4" y2="14"></line>
              </svg>
            </span>
            <h3>CPU 使用率</h3>
          </div>
          <div class="cpu-content">
            <div class="cpu-main">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{ width: `${systemData.cpu?.total_percent || 0}%` }"
                  :class="{
                    warning: systemData.cpu?.total_percent > 70,
                    critical: systemData.cpu?.total_percent > 90
                  }"
                ></div>
              </div>
              <div class="cpu-percent">{{ systemData.cpu?.total_percent?.toFixed(1) || 0 }}%</div>
            </div>
            <div class="cpu-cores">
              <h4>各核心使用率</h4>
              <div class="core-bars">
                <div
                  v-for="(usage, index) in systemData.cpu?.per_cpu || []"
                  :key="index"
                  class="core-bar"
                  :title="`核心 ${index + 1}: ${usage.toFixed(1)}%`"
                >
                  <div
                    class="core-fill"
                    :style="{ width: `${usage}%` }"
                    :class="{ warning: usage > 70, critical: usage > 90 }"
                  ></div>
                </div>
              </div>
              <p class="core-count">核心数: {{ systemData.cpu?.core_count || 0 }}</p>
            </div>
          </div>
        </div>

        <!-- 内存信息 -->
        <div class="stat-card memory-card">
          <div class="card-header">
            <span class="card-icon">🧠</span>
            <h3>内存使用</h3>
          </div>
          <div class="memory-content">
            <div class="progress-bar large">
              <div
                class="progress-fill"
                :style="{ width: `${systemData.memory?.percent || 0}%` }"
                :class="{
                  warning: systemData.memory?.percent > 70,
                  critical: systemData.memory?.percent > 90
                }"
              ></div>
            </div>
            <div class="memory-stats">
              <div class="stat-item">
                <span class="label">已使用</span>
                <span class="value">{{ systemData.memory?.used_gb?.toFixed(2) || 0 }} GB</span>
              </div>
              <div class="stat-item">
                <span class="label">总计</span>
                <span class="value">{{ systemData.memory?.total_gb?.toFixed(2) || 0 }} GB</span>
              </div>
              <div class="stat-item">
                <span class="label">使用率</span>
                <span class="value highlight"
                  >{{ systemData.memory?.percent?.toFixed(1) || 0 }}%</span
                >
              </div>
            </div>
          </div>
        </div>

        <!-- 磁盘信息 -->
        <div class="stat-card disk-card">
          <div class="card-header">
            <span class="card-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
                <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
              </svg>
            </span>
            <h3>磁盘使用</h3>
          </div>
          <div class="disk-content">
            <div class="progress-bar large">
              <div
                class="progress-fill"
                :style="{ width: `${systemData.disk?.percent || 0}%` }"
                :class="{
                  warning: systemData.disk?.percent > 70,
                  critical: systemData.disk?.percent > 90
                }"
              ></div>
            </div>
            <div class="disk-stats">
              <div class="stat-item">
                <span class="label">已使用</span>
                <span class="value">{{ systemData.disk?.used_gb?.toFixed(2) || 0 }} GB</span>
              </div>
              <div class="stat-item">
                <span class="label">总计</span>
                <span class="value">{{ systemData.disk?.total_gb?.toFixed(2) || 0 }} GB</span>
              </div>
              <div class="stat-item">
                <span class="label">使用率</span>
                <span class="value highlight"
                  >{{ systemData.disk?.percent?.toFixed(1) || 0 }}%</span
                >
              </div>
            </div>
          </div>
        </div>

        <!-- 网络信息 -->
        <div class="stat-card network-card">
          <div class="card-header">
            <span class="card-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
                <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
                <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
                <path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path>
                <line x1="12" y1="20" x2="12.01" y2="20"></line>
              </svg>
            </span>
            <h3>网络统计</h3>
          </div>
          <div class="network-content">
            <div class="network-stats">
              <div class="net-item">
                <span class="net-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                    <line x1="12" y1="19" x2="12" y2="5"></line>
                    <polyline points="5 12 12 5 19 12"></polyline>
                  </svg>
                </span>
                <div class="net-info">
                  <span class="net-label">发送</span>
                  <span class="net-value">{{
                    formatBytes(systemData.network?.bytes_sent || 0)
                  }}</span>
                </div>
              </div>
              <div class="net-item">
                <span class="net-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <polyline points="19 12 12 19 5 12"></polyline>
                  </svg>
                </span>
                <div class="net-info">
                  <span class="net-label">接收</span>
                  <span class="net-value">{{
                    formatBytes(systemData.network?.bytes_recv || 0)
                  }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 时间戳 -->
        <div class="timestamp-info">
          <span>数据时间: {{ systemData.timestamp || 'N/A' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, watch, onBeforeUnmount } from 'vue'
  import { useUserStore } from '@/stores/user'
  import { WebSocketManager, API_CONFIG } from '../utils/api/index'

  const props = defineProps({
    visible: {
      type: Boolean,
      required: true
    }
  })

  const emit = defineEmits(['close'])

  const userStore = useUserStore()
  const isConnected = ref(false)
  const lastUpdate = ref('')
  const wsManager = ref(null)

  const systemData = ref({
    timestamp: '',
    cpu: {
      total_percent: 0,
      per_cpu: [],
      core_count: 0
    },
    memory: {
      total_gb: 0,
      used_gb: 0,
      percent: 0
    },
    disk: {
      total_gb: 0,
      used_gb: 0,
      percent: 0
    },
    network: {
      bytes_sent: 0,
      bytes_recv: 0
    }
  })

  // 格式化字节数
  const formatBytes = bytes => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i]
  }

  // 连接 WebSocket
  const connectWebSocket = () => {
    if (wsManager.value) {
      wsManager.value.disconnect()
    }

    const apiUrl = API_CONFIG.WS_BASE_URL
    const wsUrl = `${apiUrl}/api/v2/Controller/sys-status?token={token}`

    wsManager.value = new WebSocketManager({
      wsUrl: wsUrl,
      userStore: userStore,
      onOpen: () => {
        isConnected.value = true
        updateLastTime()
      },
      onMessage: event => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'system_stats' && data.data) {
            systemData.value = data.data
            updateLastTime()
          }
        } catch (error) {
          // 解析错误
        }
      },
      onError: error => {
        isConnected.value = false
      },
      onClose: event => {
        isConnected.value = false

        // 认证失败(code 1008)不重试
        if (wsManager.value && event && event.code !== 1008) {
          wsManager.value.scheduleReconnect()
        }
      },
      reconnectDelay: 3000
    })

    const token = userStore.getAccessToken() || localStorage.getItem('access_token')
    wsManager.value.connect(token)
  }

  // 断开 WebSocket
  const disconnectWebSocket = () => {
    if (wsManager.value) {
      wsManager.value.disconnect()
    }

    isConnected.value = false
  }

  // 更新最后更新时间
  const updateLastTime = () => {
    const now = new Date()
    lastUpdate.value = now.toLocaleTimeString('zh-CN', { hour12: false })
  }

  // 关闭弹窗
  const handleClose = () => {
    emit('close')
  }

  // 监听 visible 变化
  watch(
    () => props.visible,
    newVal => {
      if (newVal) {
        connectWebSocket()
      } else {
        disconnectWebSocket()
      }
    }
  )

  // 组件卸载时断开连接
  onBeforeUnmount(() => {
    disconnectWebSocket()
  })
</script>

<style scoped>
  .system-monitor-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    backdrop-filter: blur(4px);
  }

  .system-monitor-container {
    background: var(--bg-primary);
    border-radius: 16px;
    width: 90%;
    max-width: 800px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    animation: slideIn 0.3s ease-out;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .monitor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 24px;
    border-bottom: 1px solid var(--border-color);
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
  }

  .monitor-header h2 {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    font-size: 24px;
  }

  .close-btn {
    background: rgba(255, 255, 255, 0.2);
    border: none;
    color: white;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    font-size: 24px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-btn:hover {
    background: rgba(255, 255, 255, 0.3);
    transform: scale(1.1);
  }

  .monitor-content {
    padding: 24px;
  }

  .connection-status {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    margin-bottom: 24px;
  }

  .status-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--danger);
    animation: pulse 1.5s infinite;
  }

  .status-dot.connected {
    background: var(--success);
  }

  .status-dot.disconnected {
    background: var(--danger);
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

  .status-text {
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 14px;
  }

  .last-update {
    margin-left: auto;
    color: var(--text-tertiary);
    font-size: 12px;
  }

  .stat-card {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    transition:
      transform 0.2s,
      box-shadow 0.2s;
  }

  .stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 20px;
  }

  .card-icon {
    font-size: 24px;
  }

  .card-header h3 {
    margin: 0;
    font-size: 18px;
    color: var(--text-primary);
    font-weight: 600;
  }

  /* CPU 卡片 */
  .cpu-main {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 20px;
  }

  .progress-bar {
    flex: 1;
    height: 32px;
    background: var(--bg-tertiary);
    border-radius: 8px;
    overflow: hidden;
    position: relative;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--success) 0%, #34d399 100%);
    border-radius: 8px;
    transition: width 0.5s ease;
  }

  .progress-fill.warning {
    background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%);
  }

  .progress-fill.critical {
    background: linear-gradient(90deg, #ef4444 0%, #f87171 100%);
  }

  .cpu-percent {
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    min-width: 80px;
    text-align: right;
  }

  .cpu-cores h4 {
    margin: 0 0 12px 0;
    font-size: 14px;
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .core-bars {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(40px, 1fr));
    gap: 6px;
    margin-bottom: 8px;
  }

  .core-bar {
    height: 80px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    overflow: hidden;
    cursor: help;
  }

  .core-fill {
    width: 100%;
    height: 100%;
    background: linear-gradient(180deg, var(--success) 0%, #34d399 100%);
    border-radius: 4px;
    transition: height 0.3s ease;
  }

  .core-fill.warning {
    background: linear-gradient(180deg, #f59e0b 0%, #fbbf24 100%);
  }

  .core-fill.critical {
    background: linear-gradient(180deg, #ef4444 0%, #f87171 100%);
  }

  .core-count {
    margin: 0;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  /* 内存和磁盘 */
  .progress-bar.large {
    height: 24px;
    margin-bottom: 16px;
  }

  .memory-stats,
  .disk-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }

  .stat-item {
    text-align: center;
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .stat-item .label {
    display: block;
    font-size: 12px;
    color: var(--text-tertiary);
    margin-bottom: 4px;
  }

  .stat-item .value {
    display: block;
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .stat-item .value.highlight {
    color: #14b8a6;
  }

  /* 网络 */
  .network-content {
    padding: 16px;
  }

  .network-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .net-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .net-icon {
    font-size: 24px;
  }

  .net-info {
    flex: 1;
  }

  .net-label {
    display: block;
    font-size: 12px;
    color: var(--text-tertiary);
    margin-bottom: 4px;
  }

  .net-value {
    display: block;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  /* 时间戳 */
  .timestamp-info {
    text-align: center;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    color: var(--text-tertiary);
    font-size: 12px;
  }

  /* 滚动条美化 */
  .system-monitor-container::-webkit-scrollbar {
    width: 8px;
  }

  .system-monitor-container::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
  }

  .system-monitor-container::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 4px;
  }

  .system-monitor-container::-webkit-scrollbar-thumb:hover {
    background: #a1a1a1;
  }
</style>
