import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useLogsStore = defineStore('logs', () => {
  // 日志数据
  const systemLogs = ref([])
  const filteredLogs = ref([])

  // 日志过滤器状态
  const logType = ref('app')
  const filterLevel = ref('')
  const filterKeyword = ref('')
  const enableDbMonitor = ref(false)
  const autoScroll = ref(true)
  const dbStatus = ref(null)

  // 显示状态
  const showHeader = ref(true)
  const showFilters = ref(true)

  // 连接状态
  const connected = ref(false)
  const loading = ref(false)
  const error = ref('')

  /**
   * 添加日志到列表
   */
  function addLog(logData) {
    systemLogs.value.unshift(logData)

    // 限制日志数量，最多保留500条
    if (systemLogs.value.length > 500) {
      systemLogs.value = systemLogs.value.slice(0, 500)
    }

    // 应用过滤器
    applyFilters()
  }

  /**
   * 应用日志过滤器
   */
  function applyFilters() {
    let filtered = systemLogs.value

    // 按级别过滤
    if (filterLevel.value) {
      const level = filterLevel.value.toUpperCase()
      filtered = filtered.filter(log => (log.level || '').toUpperCase() === level)
    }

    // 按关键词过滤
    if (filterKeyword.value.trim()) {
      const keyword = filterKeyword.value.toLowerCase()
      filtered = filtered.filter(
        log =>
          (log.message || '').toLowerCase().includes(keyword) ||
          (log.name || '').toLowerCase().includes(keyword)
      )
    }

    filteredLogs.value = filtered
  }

  /**
   * 清空日志
   */
  function clearLogs() {
    systemLogs.value = []
    filteredLogs.value = []
    dbStatus.value = null
  }

  /**
   * 重置日志（用于重新连接时）
   */
  function resetLogs() {
    systemLogs.value = []
    filteredLogs.value = []
    dbStatus.value = null
    error.value = ''
    connected.value = false
    loading.value = false
  }

  /**
   * 保存日志状态到 localStorage
   */
  function saveLogsToStorage() {
    try {
      const state = {
        systemLogs: systemLogs.value,
        logType: logType.value,
        filterLevel: filterLevel.value,
        filterKeyword: filterKeyword.value,
        enableDbMonitor: enableDbMonitor.value,
        autoScroll: autoScroll.value,
        showHeader: showHeader.value,
        showFilters: showFilters.value,
        timestamp: Date.now()
      }
      localStorage.setItem('systemLogsState', JSON.stringify(state))
    } catch (err) {
      console.warn('[WARN] Cannot save logs state to localStorage:', err)
    }
  }

  /**
   * 从 localStorage 恢复日志状态
   */
  function restoreLogsFromStorage() {
    try {
      const savedState = localStorage.getItem('systemLogsState')
      if (savedState) {
        const state = JSON.parse(savedState)

        // 恢复日志（最多保留最近100条以避免内存问题）
        if (state.systemLogs && Array.isArray(state.systemLogs)) {
          systemLogs.value = state.systemLogs.slice(0, 100)
        }

        // 恢复其他状态
        logType.value = state.logType || 'app'
        filterLevel.value = state.filterLevel || ''
        filterKeyword.value = state.filterKeyword || ''
        enableDbMonitor.value = state.enableDbMonitor || false
        autoScroll.value = state.autoScroll !== false
        showHeader.value = state.showHeader !== false
        showFilters.value = state.showFilters !== false

        // 应用过滤器
        applyFilters()

        return true
      }
    } catch (err) {
      console.error('[ERR] Restore logs state failed:', err)
      localStorage.removeItem('systemLogsState')
    }
    return false
  }

  /**
   * 清除 localStorage 中的日志状态
   */
  function clearLogsStorage() {
    localStorage.removeItem('systemLogsState')
  }

  // 监听状态变化，自动保存
  const watchLogsState = () => {
    // 这个函数需要在组件中使用 watch 来调用
    const stateKeys = [
      systemLogs,
      logType,
      filterLevel,
      filterKeyword,
      enableDbMonitor,
      autoScroll,
      showHeader,
      showFilters
    ]

    return stateKeys
  }

  return {
    // 状态
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
    error,

    // 方法
    addLog,
    clearLogs,
    resetLogs,
    applyFilters,
    saveLogsToStorage,
    restoreLogsFromStorage,
    clearLogsStorage,
    watchLogsState
  }
})
