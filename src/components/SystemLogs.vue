<template>
  <div class="content-section">
    <!-- 日志头部切换 -->
    <div class="logs-header-toggle">
      <button class="header-toggle-btn" @click="showHeader = !showHeader">
        <span class="toggle-icon">{{ showHeader ? '▼' : '▶' }}</span>
        <span>日志面板</span>
      </button>
      <div class="mini-actions">
        <span
          :class="['status-dot-compact', { connected: connected, disconnected: !connected }]"
        ></span>
      </div>
    </div>

    <div class="section-header" :class="{ collapsed: !showHeader }">
      <h3>
        <span class="icon">📋</span>
        系统日志
      </h3>
      <div class="header-actions">
        <button class="auto-scroll-btn" :class="{ active: autoScroll }" @click="toggleAutoScroll">
          <span class="icon">{{ autoScroll ? '[LOCK]' : '[UNLOCK]' }}</span>
          {{ autoScroll ? 'Auto scroll' : 'Stop scroll' }}
        </button>
        <button class="clear-btn" @click="clearLogs">
          <span class="icon">[DEL]</span>
          Clear
        </button>
        <span :class="['status-dot', { connected: connected, disconnected: !connected }]"></span>
        <span class="status-text">{{ connected ? 'Connected' : 'Disconnected' }}</span>
      </div>
    </div>

    <!-- 日志过滤器切换 -->
    <div v-if="showHeader" class="logs-filter-toggle-wrapper">
      <button class="filter-toggle-btn" @click="showFilters = !showFilters">
        <span :class="['toggle-icon', { active: showFilters }]">[FIND]</span>
        <span>Log Filter</span>
        <span :class="['arrow-icon', { open: showFilters }]">▼</span>
      </button>
    </div>

    <!-- 日志过滤器 -->
    <div v-if="showHeader" class="logs-filters" :class="{ collapsed: !showFilters }">
      <div class="filter-group">
        <label>日志类型：</label>
        <select v-model="logType" @change="reconnect">
          <option value="app">应用日志</option>
          <option value="error">错误日志</option>
          <option value="debug">调试日志</option>
        </select>
      </div>
      <div class="filter-group">
        <label>日志级别：</label>
        <select v-model="filterLevel" @change="applyFilters">
          <option value="">全部</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
      </div>
      <div class="filter-group">
        <label>关键词：</label>
        <input
          v-model="filterKeyword"
          type="text"
          placeholder="搜索日志关键词..."
          @input="applyFilters"
        />
      </div>
      <div class="filter-group toggle-group">
        <label>数据库监控：</label>
        <input v-model="enableDbMonitor" type="checkbox" @change="reconnect" />
      </div>
    </div>

    <!-- Database monitor panel -->
    <div v-if="enableDbMonitor && dbStatus" class="db-monitor">
      <h4>
        <span class="icon">[DATABASE]</span>
        Database Monitor
      </h4>
      <div class="db-stats-grid">
        <div class="db-stat-item">
          <span class="db-stat-label">活跃查询</span>
          <span class="db-stat-value">{{ dbStatus.active_queries }}</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">连接池大小</span>
          <span class="db-stat-value">{{ dbStatus.pool_stats?.pool_size }}</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">已检入</span>
          <span class="db-stat-value">{{ dbStatus.pool_stats?.checkedin }}</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">已检出</span>
          <span class="db-stat-value">{{ dbStatus.pool_stats?.checkedout }}</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">溢出连接</span>
          <span class="db-stat-value">{{ dbStatus.pool_stats?.overflow }}</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">无效连接</span>
          <span class="db-stat-value">{{ dbStatus.pool_stats?.invalidated }}</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">内存</span>
          <span class="db-stat-value">{{ (dbStatus.memory_mb || 0).toFixed(2) }} MB</span>
        </div>
        <div class="db-stat-item">
          <span class="db-stat-label">CPU</span>
          <span class="db-stat-value">{{ (dbStatus.cpu_percent || 0).toFixed(1) }}%</span>
        </div>
      </div>
    </div>

    <div class="logs-content">
      <div v-if="loading" class="loading-state">
        <p>连接日志服务中...</p>
      </div>
      <div v-else-if="error" class="error-state">
        <p>{{ error }}</p>
        <button class="retry-btn" @click="connect">重试连接</button>
      </div>
      <div v-else-if="filteredLogs.length === 0" class="empty-logs">
        <span class="icon">📋</span>
        <p>暂无日志</p>
      </div>
      <div v-else ref="logsListRef" class="logs-list">
        <div
          v-for="(log, index) in filteredLogs"
          :key="index"
          class="log-item"
          :class="'level-' + (log.level || 'info').toLowerCase()"
        >
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level }}</span>
          <span class="log-name">{{ log.name }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, onBeforeUnmount, onMounted, nextTick, watch, toRefs } from 'vue'
  import { useLogsStore } from '@/stores/logs'
  import { useUserStore } from '@/stores/user'
  import { WebSocketManager, API_CONFIG } from '../utils/api/index'

  // 使用日志 store
  const logsStore = useLogsStore()
  const userStore = useUserStore()

  // 日志 WebSocket 相关
  const logWsManager = ref(null)
  const logsListRef = ref(null)

  // 从 store 获取状态（使用 toRefs 保持响应式）
  const {
    systemLogs,
    filteredLogs,
    logType,
    filterLevel,
    filterKeyword,
    enableDbMonitor,
    autoScroll,
    dbStatus,
    showHeader,
    showFilters,
    connected,
    loading,
    error
  } = toRefs(logsStore)

  // 连接日志 WebSocket
  const connect = () => {
    if (logWsManager.value) {
      logWsManager.value.disconnect()
    }

    loading.value = true
    error.value = ''
    connected.value = false

    const apiUrl = API_CONFIG.WS_BASE_URL
    const wsUrl = `${apiUrl}/api/v2/Controller/logs?token={token}&log_type=${logType.value}&enable_db_monitor=${enableDbMonitor.value}`

    logWsManager.value = new WebSocketManager({
      wsUrl: wsUrl,
      userStore: userStore,
      onOpen: () => {
        connected.value = true
        loading.value = false
        error.value = ''

        // 应用初始过滤器
        applyFilters()
      },
      onMessage: event => {
        try {
          const data = JSON.parse(event.data)

          // 处理日志消息
          if (data.type === 'log' && data.data) {
            // data.data 可能是 JSON 字符串，需要解析
            let logData = data.data
            if (typeof logData === 'string') {
              try {
                logData = JSON.parse(logData)
              } catch (e) {
                logData = { message: logData }
              }
            }
            // 使用 store 添加日志
            logsStore.addLog(logData)

            // 自动滚动到顶部
            if (autoScroll.value) {
              scrollToTop()
            }
          }
          // 处理数据库监控消息
          else if (data.type === 'db_status' && data.data) {
            dbStatus.value = data.data
          }
          // 处理心跳
          else if (data.type === 'pong') {
            // 心跳响应，保持连接
          }
          // 处理错误
          else if (data.type === 'error') {
            error.value = data.data
          }
        } catch (error) {
          // 解析错误
        }
      },
      onError: err => {
        connected.value = false
        error.value = '连接日志服务失败'
        loading.value = false
      },
      onClose: event => {
        connected.value = false
        loading.value = false

        // 权限不足或认证失败，不自动重连
        if (event.code === 1008 || event.code === 1003) {
          error.value = event.reason || '权限不足'
          return
        }

        // 其他错误自动重连
        if (logWsManager.value) {
          logWsManager.value.scheduleReconnect()
        }
      },
      reconnectDelay: 5000
    })

    logWsManager.value.connect()
  }

  // 应用日志过滤器
  const applyFilters = () => {
    if (!logWsManager.value || !logWsManager.value.isReady()) {
      // 本地应用过滤器（即使 WebSocket 未连接）
      logsStore.applyFilters()
      return
    }

    const filters = {}
    if (filterLevel.value) {
      filters.level = filterLevel.value
    }
    if (filterKeyword.value.trim()) {
      filters.keyword = filterKeyword.value.trim()
    }

    // 发送过滤器到后端
    logWsManager.value.send({
      action: 'filter',
      level: filters.level,
      keyword: filters.keyword
    })

    // 使用 store 应用过滤器
    logsStore.applyFilters()
  }

  // 清空日志
  const clearLogs = () => {
    if (confirm('确定要清空所有日志吗？')) {
      logsStore.clearLogs()

      // 发送清除过滤器的消息到后端
      if (logWsManager.value && logWsManager.value.isReady()) {
        logWsManager.value.send({
          action: 'clear'
        })
      }
    }
  }

  // 重新连接日志服务
  const reconnect = () => {
    if (logWsManager.value) {
      logWsManager.value.disconnect()
    }
    // 使用 store 重置日志
    logsStore.resetLogs()
    connect()
  }

  // 格式化日志时间
  const formatTime = timestamp => {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    return date.toLocaleTimeString('zh-CN', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  // 切换自动滚动
  const toggleAutoScroll = () => {
    autoScroll.value = !autoScroll.value
    if (autoScroll.value) {
      scrollToTop()
    }
  }

  // 滚动到日志列表顶部
  const scrollToTop = () => {
    if (logsListRef.value) {
      nextTick(() => {
        logsListRef.value.scrollTop = 0
      })
    }
  }

  // 组件挂载时连接
  onMounted(() => {
    // 从 localStorage 恢复日志状态
    logsStore.restoreLogsFromStorage()

    // 连接日志服务
    connect()
  })

  // 组件卸载时清理
  onBeforeUnmount(() => {
    if (logWsManager.value) {
      logWsManager.value.disconnect()
    }

    // 保存日志状态到 localStorage
    logsStore.saveLogsToStorage()
  })

  // 监听状态变化，自动保存到 localStorage
  watch(
    [
      () => logsStore.systemLogs.value,
      () => logsStore.logType.value,
      () => logsStore.filterLevel.value,
      () => logsStore.filterKeyword.value,
      () => logsStore.enableDbMonitor.value,
      () => logsStore.autoScroll.value,
      () => logsStore.showHeader.value,
      () => logsStore.showFilters.value
    ],
    () => {
      logsStore.saveLogsToStorage()
    },
    { deep: true }
  )
</script>

<style scoped>
  .content-section {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding: 20px 24px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    border-radius: 16px;
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
    transition: all 0.3s ease;
  }

  .section-header.collapsed {
    display: none;
  }

  .section-header h3 {
    margin: 0;
    font-size: 22px;
    color: white;
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 600;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .section-header .icon {
    font-size: 26px;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .auto-scroll-btn,
  .clear-btn {
    padding: 8px 18px;
    background: rgba(255, 255, 255, 0.15);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 20px;
    cursor: pointer;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.3s ease;
    backdrop-filter: blur(10px);
    font-weight: 500;
  }

  .auto-scroll-btn:hover,
  .clear-btn:hover {
    background: rgba(255, 255, 255, 0.25);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .auto-scroll-btn.active {
    background: rgba(16, 185, 129, 0.3);
    border-color: rgba(16, 185, 129, 0.5);
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
    }
    50% {
      box-shadow: 0 0 0 8px rgba(16, 185, 129, 0);
    }
  }

  .status-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  .status-dot.connected {
    background: #4ade80;
    box-shadow: 0 0 10px #4ade80;
  }

  .status-dot.disconnected {
    background: #f87171;
    box-shadow: 0 0 10px #f87171;
  }

  .status-text {
    color: white;
    font-size: 14px;
  }

  /* 日志头部切换按钮 */
  .logs-header-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 24px;
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(3, 105, 161, 0.1);
    margin-bottom: 20px;
  }

  .logs-header-toggle:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(3, 105, 161, 0.2);
    border-color: #7dd3fc;
  }

  .header-toggle-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    font-size: 15px;
    font-weight: 600;
    color: #0369a1;
  }

  .logs-header-toggle .toggle-icon {
    font-size: 18px;
    transition: transform 0.3s ease;
    color: #0369a1;
  }

  .logs-header-toggle.collapsed .toggle-icon {
    transform: rotate(-90deg);
  }

  .mini-actions {
    margin-left: auto;
  }

  /* 日志过滤器切换按钮 */
  .logs-filter-toggle-wrapper {
    display: flex;
    justify-content: flex-start;
    align-items: center;
    margin-bottom: 16px;
  }

  .filter-toggle-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 20px;
    background: linear-gradient(135deg, rgba(167, 139, 250, 0.1) 0%, rgba(124, 58, 237, 0.15) 100%);
    border: 1px solid rgba(167, 139, 250, 0.3);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.3s ease;
    font-size: 14px;
    color: #0d9488;
    font-weight: 500;
  }

  .filter-toggle-btn:hover {
    background: linear-gradient(135deg, rgba(167, 139, 250, 0.15) 0%, rgba(124, 58, 237, 0.2) 100%);
    border-color: rgba(139, 92, 246, 0.4);
    transform: translateY(-1px);
  }

  .filter-toggle-btn .toggle-icon {
    font-size: 16px;
    transition: all 0.3s ease;
  }

  .filter-toggle-btn .toggle-icon.active {
    color: #7c3aed;
  }

  .filter-toggle-btn .arrow-icon {
    transition: transform 0.3s ease;
    font-size: 12px;
  }

  .filter-toggle-btn .arrow-icon.open {
    transform: rotate(180deg);
  }

  .status-dot-compact {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  .status-dot-compact.connected {
    background: #4ade80;
    box-shadow: 0 0 6px #4ade80;
  }

  .status-dot-compact.disconnected {
    background: #f87171;
    box-shadow: 0 0 6px #f87171;
  }

  /* 日志过滤器样式 */
  .logs-filters {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
    transition: all 0.3s ease;
  }

  .logs-filters.collapsed {
    max-height: 0;
    margin-bottom: 0;
    opacity: 0;
    padding: 0;
    overflow: hidden;
  }

  .logs-filters .filter-group {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 20px;
    background: linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.95) 0%,
      rgba(248, 250, 252, 0.98) 100%
    );
    border-radius: 12px;
    border: 1px solid rgba(229, 231, 235, 0.6);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    transition: all 0.3s ease;
  }

  .logs-filters .filter-group:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    border-color: rgba(167, 139, 250, 0.3);
  }

  .logs-filters .filter-group label {
    font-size: 14px;
    font-weight: 600;
    color: #4b5563;
    white-space: nowrap;
    min-width: 80px;
  }

  .logs-filters .filter-group select,
  .logs-filters .filter-group input {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    font-size: 14px;
    color: #1f2937;
    background: white;
    transition: all 0.3s ease;
    outline: none;
  }

  .logs-filters .filter-group select:hover,
  .logs-filters .filter-group input:hover {
    border-color: #a78bfa;
  }

  .logs-filters .filter-group select:focus,
  .logs-filters .filter-group input:focus {
    border-color: #7c3aed;
    box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.1);
  }

  .logs-filters .filter-group select {
    cursor: pointer;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    background-size: 16px;
    padding-right: 36px;
    appearance: none;
  }

  .logs-filters .filter-group.toggle-group input[type='checkbox'] {
    width: 18px;
    height: 18px;
    cursor: pointer;
    accent-color: #0d9488;
  }

  /* 数据库监控面板样式 */
  .db-monitor {
    padding: 16px;
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 2px solid #bae6fd;
    border-radius: 12px;
    margin-bottom: 16px;
    animation: slideIn 0.3s ease-out;
  }

  .db-monitor h4 {
    margin: 0 0 16px 0;
    font-size: 16px;
    color: #0369a1;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .db-stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
  }

  .db-stat-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px;
    background: white;
    border-radius: 8px;
    border: 1px solid #bae6fd;
    transition: all 0.2s;
  }

  .db-stat-item:hover {
    box-shadow: 0 4px 8px rgba(3, 105, 161, 0.1);
    transform: translateY(-2px);
  }

  .db-stat-label {
    font-size: 12px;
    color: #6b7280;
    font-weight: 500;
  }

  .db-stat-value {
    font-size: 20px;
    font-weight: 700;
    color: #0369a1;
  }

  /* 日志内容区域 */
  .logs-content {
    flex: 1;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-radius: 20px;
    border: 1px solid rgba(229, 231, 235, 0.5);
    padding: 24px;
    overflow-y: auto;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.03);
  }

  .logs-content::-webkit-scrollbar {
    width: 8px;
  }

  .logs-content::-webkit-scrollbar-track {
    background: rgba(229, 231, 235, 0.3);
    border-radius: 4px;
  }

  .logs-content::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #a78bfa 0%, #7c3aed 100%);
    border-radius: 4px;
  }

  .logs-content::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
  }

  .loading-state,
  .error-state {
    text-align: center;
    padding: 60px 40px;
    color: #6b7280;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
  }

  .loading-state p,
  .error-state p {
    margin: 0;
    font-size: 16px;
    color: #6b7280;
  }

  .retry-btn {
    padding: 12px 28px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 25px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .retry-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
  }

  .logs-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .log-item {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 16px 20px;
    background: white;
    border-radius: 12px;
    border: 1px solid rgba(229, 231, 235, 0.6);
    transition: all 0.3s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
    animation: slideIn 0.3s ease-out;
    align-items: center;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateX(-20px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .log-item:hover {
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    border-color: rgba(167, 139, 250, 0.4);
    transform: translateX(4px);
  }

  .log-item.level-info {
    border-left: 4px solid #3b82f6;
  }

  .log-item.level-warning {
    border-left: 4px solid #f59e0b;
  }

  .log-item.level-error {
    border-left: 4px solid #ef4444;
  }

  .log-item.level-critical {
    border-left: 4px solid #dc2626;
    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  }

  .log-item.level-debug {
    border-left: 4px solid #6b7280;
  }

  .log-time {
    font-size: 13px;
    color: #9ca3af;
    font-family: 'Consolas', 'Monaco', monospace;
    min-width: 100px;
    flex-shrink: 0;
  }

  .log-level {
    font-size: 11px;
    font-weight: 700;
    padding: 6px 12px;
    border-radius: 6px;
    min-width: 70px;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    flex-shrink: 0;
  }

  .log-name {
    font-size: 13px;
    color: #6b7280;
    font-weight: 500;
    font-family: 'Consolas', 'Monaco', monospace;
    min-width: 120px;
    flex-shrink: 0;
  }

  .log-message {
    flex: 1;
    font-size: 14px;
    color: #1f2937;
    line-height: 1.6;
    word-break: break-word;
    font-family: 'Consolas', 'Monaco', monospace;
    min-width: 200px;
  }

  .log-item.level-info .log-level {
    background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
    color: #1e40af;
    border: 1px solid rgba(59, 130, 246, 0.2);
  }

  .log-item.level-warning .log-level {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    color: #92400e;
    border: 1px solid rgba(245, 158, 11, 0.2);
  }

  .log-item.level-error .log-level {
    background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
    color: #991b1b;
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .log-item.level-critical .log-level {
    background: linear-gradient(135deg, #b91c1c 0%, #dc2626 100%);
    color: white;
    border: 1px solid rgba(220, 38, 38, 0.3);
    box-shadow: 0 2px 4px rgba(220, 38, 38, 0.3);
  }

  .log-item.level-debug .log-level {
    background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
    color: #4b5563;
    border: 1px solid rgba(107, 114, 128, 0.2);
  }

  .empty-logs {
    text-align: center;
    padding: 80px 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
  }

  .empty-logs .icon {
    font-size: 64px;
    opacity: 0.3;
  }

  .empty-logs p {
    margin: 0;
    font-size: 16px;
    color: #9ca3af;
    font-weight: 500;
  }
</style>
